import json
from enum import Enum, auto
from typing import Any, Callable, Awaitable, cast, Type

from json_repair import repair_json
from loguru import logger
from fastmcp import Client
from fastmcp.tools import Tool
from fastmcp.client.transports import ClientTransportT

from .interface import IAgent
from .base import BaseAgent
from ..middleware import HumanInterfere
from ..state_machine.workflow import IWorkflow, BaseWorkflow
from ..state_machine.task import (
    ITask,
    ITreeTaskNode,
    TaskState,
    TaskEvent,
    RequirementTaskView,
    ProtocolTaskView,
)
from ...llm import ILLM, build_llm
from ...model import (
    TextBlock, ToolCallRequest, Message, Role, IQueue, CompletionConfig, get_settings
)
from ...model.message import TextBlock
from ...utils.io import read_markdown
from ...utils.string.extract import extract_by_label
from ...utils.content import extract_text_from_message


CREATE_DOC = """根据 JSON 字符串创建子任务列表，并将其添加到指定的父任务中。该函数不会返回值，而是直接修改传入的父任务实例。

    Args:
        json_str (str): 包含子任务信息的 JSON 字符串

    Raises:
        ValueError: 如果无法解析 JSON 字符串
        AssertionError: 如果子任务数据缺少必要字段
"""


def create_sub_tasks(json_str: str, kwargs: dict[str, Any] | None = None) -> None:
    """根据 JSON 字符串创建子任务列表，并将其添加到指定的父任务中。该函数不会返回值，而是直接修改传入的父任务实例。

    Args:
        valid_tasks (dict[str, Type[ITask]]): 有效任务类型映射，键为任务类型名称，值为任务类型
        task (ITreeTaskNode): 父任务实例
        json_str (str): 包含子任务信息的 JSON 字符串

    Raises:
        ValueError: 如果无法解析 JSON 字符串
        AssertionError: 如果子任务数据缺少必要字段
    """
    assert kwargs is not None, "kwargs 参数不能为空"
    valid_tasks: dict[str, Type[ITreeTaskNode[TaskState, TaskEvent]]] = kwargs["valid_tasks"]
    task: ITreeTaskNode[TaskState, TaskEvent] = kwargs["task"]

    repaired_json = repair_json(json_str)
    try:
        sub_tasks_data: dict[str, dict[str, Any]] = json.loads(repaired_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"无法解析子任务 JSON 字符串: {e}")

    for title, sub_task_data in sub_tasks_data.items():
        # 根据任务类型创建子任务实例
        assert "任务类型" in sub_task_data, "子任务数据必须包含 '任务类型' 字段"
        sub_task = valid_tasks[sub_task_data["任务类型"]]()
        # 设置子任务输入
        assert "任务输入" in sub_task_data, "子任务数据必须包含 '任务输入' 字段"
        sub_task.set_input([TextBlock(text=sub_task_data["任务输入"])])
        sub_task.set_title(title)
        # 将子任务添加到父任务
        task.add_sub_task(sub_task)


class OrchestrateStage(str, Enum):
    """Orchestrate 工作流阶段枚举"""
    THINKING = "thinking"
    ORCHESTRATING = "orchestrating"
    FINISHED = "finished"

    @classmethod
    def list_stages(cls) -> list['OrchestrateStage']:
        """列出所有工作流阶段

        Returns:
            工作流阶段列表
        """
        return [stage for stage in OrchestrateStage]


class OrchestrateEvent(Enum):
    """Orchestrate 工作流事件枚举"""
    THINK = auto()          # 触发思考
    ORCHESTRATE = auto()    # 触发编排
    FINISH = auto()         # 触发完成

    @property
    def name(self) -> str:
        """获取事件名称"""
        return self._name_.lower()


def get_orch_stages() -> set[OrchestrateStage]:
    """获取 Think - Orchestrate - Finish 工作流的阶段
    - THINKING, CHECKING, ORCHESTRATING, FINISHED

    Returns:
        orchestrate 工作流的阶段集合
    """
    return {
        OrchestrateStage.THINKING,
        OrchestrateStage.ORCHESTRATING,
        OrchestrateStage.FINISHED,
    }


def get_orch_event_chain() -> list[OrchestrateEvent]:
    """获取编排工作流事件链
    -  THINK, CHECK, ORCHESTRATE, FINISH

    Returns:
        orchestrate工作流事件链
    """
    return [
        OrchestrateEvent.THINK,
        OrchestrateEvent.ORCHESTRATE,
        OrchestrateEvent.FINISH,
    ]


def get_orch_actions(
    agent: IAgent[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent, ClientTransportT],
    valid_tasks: dict[str, Type[ITreeTaskNode[TaskState, TaskEvent]]],
) -> dict[
    OrchestrateStage,
    Callable[
        [
            IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent],
            dict[str, Any],
            IQueue[Message],
            ITask[TaskState, TaskEvent],
        ],
        Awaitable[OrchestrateEvent]
    ]
]:
    """获取 Orchestrate 工作流动作定义
    -  THINKING: thinking_action
    -  CHECKING: checking_action
    -  ORCHESTRATING: orchestrating_action

    Args:
        agent (IAgent): 关联的智能体实例
        valid_tasks (dict[str, Type[ITreeTaskNode]]): 有效任务类型映射，键为任务类型名称，值为任务类型

    Returns:
        常用工作流动作定义
    """
    actions: dict[OrchestrateStage, Callable[
        [
            IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent],
            dict[str, Any],
            IQueue[Message],
            ITask[TaskState, TaskEvent],
        ],
        Awaitable[OrchestrateEvent]]
    ] = {}

    # THINKING 阶段动作定义
    async def think(
        workflow: IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[TaskState, TaskEvent],
    ) -> OrchestrateEvent:
        """THINKING 阶段动作函数

        Args:
            context (dict[str, Any]): 上下文字典，用于传递用户ID/AccessToken/TraceID等信息
            queue (IQueue[Message]): 数据队列，用于输出数据
            workflow (IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent]): 工作流实例
            task (ITask[TaskState, TaskEvent]): 任务实例

        Returns:
            OrchestrateEvent: 触发的事件类型
        """
        # 获取当前工作流的状态
        current_state = workflow.get_current_state()
        if current_state != OrchestrateStage.THINKING:
            raise RuntimeError(f"当前工作流状态错误，期望：{OrchestrateStage.THINKING}，实际：{current_state}")

        # 获取当前工作流的提示词
        prompt = workflow.get_prompt()
        # 创建新的任务消息
        message = Message(role=Role.USER, content=[TextBlock(text=prompt)])
        # 添加 message 到当前任务上下文
        task.get_context().append_context_data(message)
        # 观察 Task
        await agent.observe(
            context=context,
            queue=queue,
            task=task,
            observe_fn=workflow.get_observe_fn(),
        )
        try:
            # 开始 LLM 推理
            message = await agent.think(
                context=context,
                queue=queue,
                task=task,
                completion_config=workflow.get_completion_config(),
            )
        except HumanInterfere as e:
            # 将人类介入信息反馈到任务
            result = Message(
                role=Role.USER,
                content=e.get_messages(),
                is_error=True,
            )
            # 记录到任务上下文
            task.get_context().append_context_data(result)
            # 返回 THINK 事件重新思考
            return OrchestrateEvent.THINK
        
        # 从消息中提取 orchestration 输出
        orchestration = extract_by_label(
            extract_text_from_message(message),
            "orchestration", "orchestrate"
        )

        if orchestration == "":
            # 编排结果为空，进入错误处理流程
            task.set_error("编排结果为空，无法创建子任务")
            # 直接完成当前思考，返回 FINISH 事件结束工作流
            return OrchestrateEvent.FINISH

        # 正常完成思考，开始编排
        return OrchestrateEvent.ORCHESTRATE

    # 添加到动作定义字典
    actions[OrchestrateStage.THINKING] = think

    # ORCHESTRATING 阶段动作定义
    async def orchestrate(
        workflow: IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[TaskState, TaskEvent],
    ) -> OrchestrateEvent:
        """ORCHESTRATING 阶段动作函数

        Args:
            context (dict[str, Any]): 上下文字典，用于传递用户ID/AccessToken/TraceID等信息
            queue (IQueue[Message]): 数据队列，用于输出数据
            workflow (IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent]): 工作流实例
            task (ITask[TaskState, TaskEvent]): 任务实例

        Returns:
            OrchestrateEvent: 触发的事件类型
        """
        # 检查工作流当前状态
        current_state = workflow.get_current_state()
        if current_state != OrchestrateStage.ORCHESTRATING:
            raise RuntimeError(f"当前工作流状态错误，期望：{OrchestrateStage.ORCHESTRATING}，实际：{current_state}")

        # 获取任务的推理配置
        completion_config = workflow.get_completion_config()
        # 要求输出必须格式化为JSON
        completion_config.update(format_json=True)

        # 获取当前工作流的提示词
        prompt = workflow.get_prompt()
        # 创建新的任务消息
        message = Message(role=Role.USER, content=[TextBlock(text=prompt)])
        # 添加 message 到当前任务上下文
        task.get_context().append_context_data(message)
        # 观察 Task
        await agent.observe(
            context=context,
            queue=queue,
            task=task,
            observe_fn=workflow.get_observe_fn(),
        )
        # 开始 LLM 推理
        message = await agent.think(
            context=context,
            queue=queue,
            task=task,
            completion_config=completion_config,
        )

        # 构造 ToolCallRequest
        tool_call = ToolCallRequest(
            id="auto_create_sub_tasks",
            name="create_sub_tasks",
            args={
                "json_str": extract_text_from_message(message),
            },
        )
        # 调用 act 执行子任务创建
        result = await agent.act(
            context=context, 
            queue=queue, 
            task=task, 
            tool_call=tool_call,
            valid_tasks=valid_tasks, 
        )
        if result.is_error:
            # 设置任务错误状态
            task.set_error(extract_text_from_message(message))
            return OrchestrateEvent.THINK

        return OrchestrateEvent.FINISH

    # 添加到动作定义字典
    actions[OrchestrateStage.ORCHESTRATING] = orchestrate

    return actions


def get_orch_transition() -> dict[
    tuple[OrchestrateStage, OrchestrateEvent],
    tuple[
        OrchestrateStage,
        Callable[[IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent]], Awaitable[None] | None] | None
    ]
]:
    """获取常用工作流转换规则
    -  INIT + REASON -> THINKING
    -  THINKING + orch -> orchION
    -  orchION + FINISH -> FINISHED

    Returns:
        常用工作流转换规则
    """
    transition: dict[
        tuple[OrchestrateStage, OrchestrateEvent],
        tuple[
            OrchestrateStage,
            Callable[[IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent]], Awaitable[None] | None] | None
        ]
    ] = {}

    # 1. THINKING -> THINKING (事件： THINK)
    async def on_thinking_to_thinking(
        workflow: IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent],
    ) -> None:
        """从 THINKING 到 THINKING 的转换回调函数"""
        logger.debug(f"Workflow {workflow.get_id()} Transition: {OrchestrateStage.THINKING} -> {OrchestrateStage.THINKING}.")

    # 添加转换规则
    transition[(OrchestrateStage.THINKING, OrchestrateEvent.THINK)] = (OrchestrateStage.THINKING, on_thinking_to_thinking)

    # 2. THINKING -> ORCHESTRATING (事件： ORCHESTRATE)
    async def on_thinking_to_orchestrating(
        workflow: IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent],
    ) -> None:
        """从 THINKING 到 ORCHESTRATING 的转换回调函数"""
        logger.debug(f"Workflow {workflow.get_id()} Transition: {OrchestrateStage.THINKING} -> {OrchestrateStage.ORCHESTRATING}.")

    # 添加转换规则
    transition[(OrchestrateStage.THINKING, OrchestrateEvent.ORCHESTRATE)] = (OrchestrateStage.ORCHESTRATING, on_thinking_to_orchestrating)

    # 3. ORCHESTRATING -> THINKING (事件： THINK)
    async def on_orchestrating_to_THINKING(
        workflow: IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent],
    ) -> None:
        """从 ORCHESTRATING 到 THINKING 的转换回调函数"""
        logger.debug(f"Workflow {workflow.get_id()} Transition: {OrchestrateStage.ORCHESTRATING} -> {OrchestrateStage.THINKING}.")

    # 添加转换规则
    transition[(OrchestrateStage.ORCHESTRATING, OrchestrateEvent.THINK)] = (OrchestrateStage.THINKING, on_orchestrating_to_THINKING)

    # 4. ORCHESTRATING -> FINISHED (事件： FINISH)
    async def on_orchestrating_to_finished(
        workflow: IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent],
    ) -> None:
        """从 ORCHESTRATING 到 FINISHED 的转换回调函数"""
        logger.debug(f"Workflow {workflow.get_id()} Transition: {OrchestrateStage.ORCHESTRATING} -> {OrchestrateStage.FINISHED}.")

    # 添加转换规则
    transition[(OrchestrateStage.ORCHESTRATING, OrchestrateEvent.FINISH)] = (OrchestrateStage.FINISHED, on_orchestrating_to_finished)

    return transition


def build_orch_agent(
    name: str,
    valid_tasks: dict[str, Type[ITreeTaskNode[TaskState, TaskEvent]]],
    tool_service: Client[ClientTransportT] | None = None,
    actions: dict[
        OrchestrateStage,
        Callable[
            [
                IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent],
                dict[str, Any],
                IQueue[Message],
                ITask[TaskState, TaskEvent],
            ],
            Awaitable[OrchestrateEvent]
        ]
    ] | None = None,
    transitions: dict[
        tuple[OrchestrateStage, OrchestrateEvent],
        tuple[
            OrchestrateStage,
            Callable[[IWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent]], Awaitable[None] | None] | None
        ]
    ] | None = None,
    prompts: dict[OrchestrateStage, str] | None = None,
    observe_funcs: dict[
        OrchestrateStage,
        Callable[[ITask[TaskState, TaskEvent], dict[str, Any]], Message]
    ] | None = None,
) -> IAgent[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent, ClientTransportT]:
    """构建一个 `Orchestrate` 的智能体实例

    Args:
        name: 智能体名称，必填，用于在 settings 中读取对应的配置
        valid_tasks: 有效任务类型映射，必填，用于智能体管理和调度
        tool_service: 工具服务客户端，可选，如果未提供则不关联工具服务
        actions: 动作定义，可选，如果未提供则使用默认定义
        transitions: 状态转换规则，可选，如果未提供则使用默认定义
        prompts: 提示词，可选，如果未提供则使用默认定义
        observe_funcs: 观察函数，可选，如果未提供则使用默认定义

    Returns:
        智能体实例
    """
    # 获取全局设置
    settings = get_settings()
    # 获取智能体的配置
    agent_cfg = settings.get_agent_config(name)
    if agent_cfg is None:
        raise ValueError(f"未找到名为 '{name}' 的智能体配置")

    llms: dict[OrchestrateStage, ILLM] = {}
    for stage in OrchestrateStage:
        if stage == OrchestrateStage.FINISHED:
            continue  # FINISHED 阶段不需要 LLM
        # LLM 配置
        llm_cfg = agent_cfg.get_llm_config(stage.value)
        # 连接 LLM 服务端
        llms[stage] = build_llm(llm_cfg)

    # 构建基础 Agent 实例
    agent = BaseAgent[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent, ClientTransportT](
        name=name,
        agent_type=agent_cfg.agent_type,
        llms=llms,
        tool_service=tool_service,
    )
    # 获取 event chain
    event_chain = get_orch_event_chain()
    # 获取 valid states
    valid_states = get_orch_stages()
    # 获取初始状态
    init_state = OrchestrateStage.THINKING
    # 获取动作定义
    actions = actions if actions is not None else get_orch_actions(agent, valid_tasks)
    # 获取转换规则
    transitions = transitions if transitions is not None else get_orch_transition()
    # 定义提示词
    prompts = prompts if prompts is not None else {
        OrchestrateStage.THINKING: read_markdown("workflow/orchestrate/thinking.md").format(
            task_types="\n\n".join([
                f"<option>\n<name>\n{option_name}\n</name>\n<description>\n{ProtocolTaskView()(cast(ITask[TaskState, TaskEvent], option_desc))}\n</description>\n</option>" 
                for option_name, option_desc in valid_tasks.items()]),
        ),
        OrchestrateStage.ORCHESTRATING: read_markdown("workflow/orchestrate/orchestrating.md"),
    }
    # 定义观察函数
    def observe_task_view(task: ITask[TaskState, TaskEvent], kwargs: dict[str, Any]) -> Message:
        """观察任务并生成消息"""    # TODO: 要根据状态组合观察方法
        view = RequirementTaskView[TaskState, TaskEvent]()
        content = view(task, **kwargs)
        return Message(role=Role.USER, content=[TextBlock(text=content)])

    observe_funcs = observe_funcs if observe_funcs is not None else {
        OrchestrateStage.THINKING: observe_task_view,
        OrchestrateStage.ORCHESTRATING: observe_task_view,
    }

    # 构建 CompletionConfig 映射
    completion_configs: dict[OrchestrateStage, CompletionConfig] = {}
    for stage in OrchestrateStage:
        # LLM 配置
        llm_cfg = agent_cfg.get_llm_config(stage.value)
        completion_configs[stage] = CompletionConfig(
            max_tokens=llm_cfg.max_tokens,
            tools=[],
        )
        
    # 构建创建子任务工具
    tool = Tool.from_function(
        fn=create_sub_tasks,
        name="create_sub_tasks",
        description=CREATE_DOC,
        exclude_args=['kwargs'],
    )

    # 构建工作流实例
    workflow = BaseWorkflow[OrchestrateStage, OrchestrateEvent, TaskState, TaskEvent](
        valid_states=valid_states,
        init_state=init_state,
        transitions=transitions,
        name="orchWorkflow",
        completion_configs=completion_configs,
        actions=actions,
        prompts=prompts,
        observe_funcs=observe_funcs,
        event_chain=event_chain,
        tools={"create_sub_tasks": (tool, set[str]())},
    )
    # 关联工作流到智能体
    agent.set_workflow(workflow)
    return agent
