from enum import Enum, auto
from typing import Any
from collections.abc import Callable, Awaitable

from loguru import logger
from mcp.types import Tool as McpTool
from fastmcp import Client
from fastmcp.client.transports import ClientTransportT
from fastmcp.tools import Tool as FastMcpTool

from .interface import IAgent
from .base import BaseAgent
from .react import end_workflow, END_WORKFLOW_DOC
from ..state_machine.workflow import IWorkflow, BaseWorkflow
from ..state_machine.task import ITask, TaskState, TaskEvent, RequirementTaskView
from ...hook.human import HumanInterfere
from ...llm import ILLM, build_llm
from ...model import Message, StopReason, Role, IAsyncQueue, CompletionConfig, get_settings
from ...model.message import TextBlock
from ...utils.io import read_markdown
from ...utils.string.xml import extract_by_label
from ...utils.string.message import extract_text_from_message


class ReflectStage(str, Enum):
    """ReAct - Reflect 工作流阶段枚举"""
    REASONING = "reasoning"
    REFLECTING = "reflecting"
    FINISHED = "finished"

    @classmethod
    def list_stages(cls) -> list['ReflectStage']:
        """列出所有工作流阶段

        Returns:
            工作流阶段列表
        """
        return [stage for stage in ReflectStage]


class ReflectEvent(Enum):
    """ReAct - Reflect 工作流事件枚举"""
    REASON = auto()     # 触发推理
    REFLECT = auto()    # 触发反思
    FINISH = auto()     # 触发完成

    @property
    def name(self) -> str:
        """获取事件名称"""
        return self._name_.lower()


def get_reflect_transition() -> dict[
    tuple[ReflectStage, ReflectEvent],
    tuple[
        ReflectStage,
        Callable[[IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent]], Awaitable[None] | None] | None
    ]
]:
    """获取常用工作流转换规则
    -  INIT + REASON -> REASONING
    -  REASONING + REFLECT -> REFLECTION
    -  REFLECTION + FINISH -> FINISHED

    Returns:
        常用工作流转换规则
    """
    transition: dict[
        tuple[ReflectStage, ReflectEvent],
        tuple[
            ReflectStage,
            Callable[[IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent]], Awaitable[None] | None] | None
        ]
    ] = {}

    # 1. REASONING -> REFLECTION (事件： REFLECT)
    async def on_reasoning_to_reflection(
        workflow: IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent],
    ) -> None:
        """从 REASONING 到 REFLECTION 的转换回调函数"""
        logger.debug(f"Workflow {workflow.get_id()} Transition: {ReflectStage.REASONING} -> {ReflectStage.REFLECTING}.")

    # 添加转换规则
    transition[(ReflectStage.REASONING, ReflectEvent.REFLECT)] = (ReflectStage.REFLECTING, on_reasoning_to_reflection)

    # 2. REFLECTION -> FINISHED (事件： FINISH)
    async def on_reflection_to_finished(
        workflow: IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent],
    ) -> None:
        """从 REFLECTION 到 FINISHED 的转换回调函数"""
        logger.debug(f"Workflow {workflow.get_id()} Transition: {ReflectStage.REFLECTING} -> {ReflectStage.FINISHED}.")

    # 添加转换规则
    transition[(ReflectStage.REFLECTING, ReflectEvent.FINISH)] = (ReflectStage.FINISHED, on_reflection_to_finished)

    # 3. REFLECTION -> REASONING (事件： REASON)
    async def on_reflection_to_reasoning(
        workflow: IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent],
    ) -> None:
        """从 REFLECTION 到 REASONING 的转换回调函数"""
        logger.debug(f"Workflow {workflow.get_id()} Transition: {ReflectStage.REFLECTING} -> {ReflectStage.REASONING}.")

    # 添加转换规则
    transition[(ReflectStage.REFLECTING, ReflectEvent.REASON)] = (ReflectStage.REASONING, on_reflection_to_reasoning)

    return transition


def get_reflect_stages() -> set[ReflectStage]:
    """获取 Reason - Act -Reflect 工作流的阶段
    - REASONING, REFLECTING, FINISHED

    Returns:
        reflect 工作流的阶段集合
    """
    return {
        ReflectStage.REASONING,
        ReflectStage.REFLECTING,
        ReflectStage.FINISHED,
    }


def get_reflect_event_chain() -> list[ReflectEvent]:
    """获取常用工作流事件链
    -  REASON, REFLECT, FINISH

    Returns:
        reflect工作流事件链
    """
    return [
        ReflectEvent.REASON,
        ReflectEvent.REFLECT,
        ReflectEvent.FINISH,
    ]


def get_reflect_actions(
    agent: IAgent[ReflectStage, ReflectEvent, TaskState, TaskEvent, ClientTransportT],
) -> dict[
    ReflectStage,
    Callable[
        [
            IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent],
            dict[str, Any],
            IAsyncQueue[Message],
            ITask[TaskState, TaskEvent],
        ],
        Awaitable[ReflectEvent]
    ]
]:
    """获取常用工作流动作定义
    -  REASONING: (reason_action, reason_stream_action)
    -  ACTION: (action_action, action_stream_action)
    -  REFLECTION: (reflection_action, reflection_stream_action)

    Args:
        agent (IAgent): 关联的智能体实例

    Returns:
        常用工作流动作定义
    """
    actions: dict[ReflectStage, Callable[
        [
            IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent],
            dict[str, Any],
            IAsyncQueue[Message],
            ITask[TaskState, TaskEvent],
        ],
        Awaitable[ReflectEvent]]
    ] = {}

    # REASONING 阶段动作定义
    async def reason(
        workflow: IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IAsyncQueue[Message],
        task: ITask[TaskState, TaskEvent],
    ) -> ReflectEvent:
        """REASONING 阶段动作函数

        Args:
            context (dict[str, Any]): 上下文字典，用于传递用户ID/AccessToken/TraceID等信息
            queue (IQueue[Message]): 数据队列，用于输出数据
            workflow (IWorkflow[reflectStage, reflectEvent, TaskState, TaskEvent]): 工作流实例
            task (ITask[TaskState, TaskEvent]): 任务实例

        Returns:
            reflectEvent: 触发的事件类型
        """
        # 获取当前工作流的状态
        current_state = workflow.get_current_state()
        if current_state != ReflectStage.REASONING:
            raise RuntimeError(f"当前工作流状态错误，期望：{ReflectStage.REASONING}，实际：{current_state}")

        # 获取任务的推理配置信息
        completion_config = workflow.get_completion_config()
        # 更新工具服务器工具信息
        service_tools = await agent.get_tools_with_tags(
            task.get_tags(),
        )
        # 更新推理配置中的工具列表
        completion_config.update(
            stop_words=["</final_flag>", "</finish>", "</finish_flag>", "</end_flag>"],
        )

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
                workflow=workflow,
                queue=queue,
                task=task,
                valid_tools=service_tools,
                completion_config=workflow.get_completion_config(),
            )
        except HumanInterfere as e:
            # 将人类介入信息反馈到任务
            task.get_context().append_context_data(Message(
                role=Role.USER,
                content=e.get_messages(),
                is_error=True,
            ))
            # 重新进入处理流程
            return ReflectEvent.REASON

        # 允许执行工具标志位
        allow_tool: bool = True

        if message.stop_reason == StopReason.TOOL_CALL:
            # Act on the task or environment
            for tool_call in message.tool_calls:
                # 检查工具执行许可
                if not allow_tool:
                    # 生成错误信息
                    result = Message(
                        role=Role.TOOL,
                        tool_call_id=tool_call.id,
                        is_error=True,
                        content=[TextBlock(text="由于前置工具调用出错，后续工具调用被禁止继续执行")]
                    )
                    # 更新到任务上下文
                    task.get_context().append_context_data(result)
                    continue

                try:
                    # 开始执行工具，如果是工具服务的工具，则 task/workflow 不会被注入到参数中
                    result = await agent.act(
                        context=context,
                        queue=queue,
                        tool_call=tool_call,
                        task=task,
                        workflow=workflow,
                    )
                except HumanInterfere as e:
                    # 将人类介入信息反馈到任务
                    result = Message(
                        role=Role.USER,
                        content=e.get_messages(),
                        is_error=True,
                    )
                    # 禁止后续工具调用执行
                    allow_tool = False

                # 检查调用错误状态
                if result.is_error:
                    # 将任务设置为错误状态
                    task.set_error(extract_text_from_message(result))
                    # 停止执行剩余的工具
                    allow_tool = False
                    # 返回 FINISH 事件，结束工作流
                    return ReflectEvent.FINISH

        # 正常进入下一个工作流阶段
        return ReflectEvent.REFLECT

    # 添加到动作定义字典
    actions[ReflectStage.REASONING] = reason

    # REFLECTION 阶段动作定义
    async def reflect(
        workflow: IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IAsyncQueue[Message],
        task: ITask[TaskState, TaskEvent],
    ) -> ReflectEvent:
        """REFLECTION 阶段动作函数

        Args:
            context (dict[str, Any]): 上下文字典，用于传递用户ID/AccessToken/TraceID等信息
            queue (IQueue[Message]): 数据队列，用于输出数据
            workflow (IWorkflow[reflectStage, reflectEvent, TaskState, TaskEvent]): 工作流实例
            task (ITask[TaskState, TaskEvent]): 任务实例

        Returns:
            reflectEvent: 触发的事件类型
        """
        # 检查工作流当前状态
        current_state = workflow.get_current_state()
        if current_state != ReflectStage.REFLECTING:
            raise RuntimeError(f"当前工作流状态错误，期望：{ReflectStage.REFLECTING}，实际：{current_state}")
        
        # 获取任务的推理配置信息
        completion_config = workflow.get_completion_config()
        # 获取推理配置中的工具信息
        tools: dict[str, McpTool] = {}
        # 更新工作流工具信息
        workflow_tools = workflow.get_tools()
        for _, (tool, _) in workflow_tools.items():
            tools[tool.name] = tool.to_mcp_tool()
        completion_config.update(
            stop_words=["</final_flag>", "</finish>", "</finish_flag>", "</end_flag>"],
        )

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
            workflow=workflow,
            queue=queue,
            task=task,
            valid_tools=tools,
            completion_config=completion_config,
        )
        # 推理结果反馈到任务
        task.get_context().append_context_data(message)
        # 从 Message 中获取结束工作流的标志内容
        finish_flag = extract_by_label(extract_text_from_message(message), "finish", "finish_flag", "finish_workflow")

        # 允许执行工具标志位
        allow_tool: bool = True

        if message.stop_reason == StopReason.TOOL_CALL:
            # Act on the task or environment
            for tool_call in message.tool_calls:
                # 检查工具执行许可
                if not allow_tool:
                    # 生成错误信息
                    result = Message(
                        role=Role.TOOL,
                        tool_call_id=tool_call.id,
                        is_error=True,
                        content=[TextBlock(text="由于前置工具调用出错，后续工具调用被禁止继续执行")]
                    )
                    # 更新到任务上下文
                    task.get_context().append_context_data(result)
                    continue

                # 注入 Task 和 Workflow，并开始执行工具
                result = await agent.act(
                    context=context,
                    queue=queue,
                    tool_call=tool_call,
                    task=task,
                    workflow=workflow,
                )
                # 检查调用错误状态
                if result.is_error:
                    # 将任务设置为错误状态
                    task.set_error(extract_text_from_message(result))
                    # 停止执行剩余的工具
                    allow_tool = False

        # 没有调用工具，手动检查结束标志位
        elif finish_flag.upper() == "TRUE":
            # 手动调用结束工作流
            end_workflow(kwargs={"task": task})

        if task.is_error():
            return ReflectEvent.REASON
        else:
            return ReflectEvent.FINISH

    # 添加到动作定义字典
    actions[ReflectStage.REFLECTING] = reflect

    return actions


def build_reflect_agent(
    name: str,
    tool_service: Client[ClientTransportT] | None = None,
    actions: dict[
        ReflectStage,
        Callable[
            [
                IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent],
                dict[str, Any],
                IAsyncQueue[Message],
                ITask[TaskState, TaskEvent],
            ],
            Awaitable[ReflectEvent]
        ]
    ] | None = None,
    transitions: dict[
        tuple[ReflectStage, ReflectEvent],
        tuple[
            ReflectStage,
            Callable[[IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent]], Awaitable[None] | None] | None
        ]
    ] | None = None,
    prompts: dict[ReflectStage, str] | None = None,
    observe_funcs: dict[
        ReflectStage,
        Callable[[ITask[TaskState, TaskEvent], dict[str, Any]], Message]
    ] | None = None,
) -> IAgent[ReflectStage, ReflectEvent, TaskState, TaskEvent, ClientTransportT]:
    """构建一个 `Reason - Act - Reflection` 的智能体实例

    Args:
        name: 智能体名称，必填，用于在 settings 中读取对应的配置
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

    # 构建基础 Agent 实例
    agent = BaseAgent[ReflectStage, ReflectEvent, TaskState, TaskEvent, ClientTransportT](
        name=name,
        agent_type=agent_cfg.agent_type,
        tool_service=tool_service,
    )
    # 获取 event chain
    event_chain = get_reflect_event_chain()
    # 获取 valid states
    valid_states = get_reflect_stages()
    # 获取初始状态
    init_state = ReflectStage.REASONING
    # 获取动作定义
    actions = actions if actions is not None else get_reflect_actions(agent)
    # 获取转换规则
    transitions = transitions if transitions is not None else get_reflect_transition()
    # 定义提示词
    prompts = prompts if prompts is not None else {
        ReflectStage.REASONING: read_markdown("workflow/reflect/system.md"),
    }
    # 定义观察函数
    def observe_task_view(task: ITask[TaskState, TaskEvent], kwargs: dict[str, Any]) -> Message:
        """观察任务并生成消息"""    # TODO: 要根据状态组合观察方法
        view = RequirementTaskView[TaskState, TaskEvent]()
        content = view(task, **kwargs)
        return Message(role=Role.USER, content=[TextBlock(text=content)])

    observe_funcs = observe_funcs if observe_funcs is not None else {
        ReflectStage.REASONING: observe_task_view,
        ReflectStage.REFLECTING: observe_task_view,
    }

    # 构建结束工作流工具实例
    end_workflow_tool = FastMcpTool.from_function(
        fn= end_workflow,
        name="end_workflow",
        description=END_WORKFLOW_DOC,
        exclude_args=["kwargs"],
    )

    llms: dict[ReflectStage, ILLM] = {}
    for stage in ReflectStage:
        if stage == ReflectStage.FINISHED:
            continue  # FINISHED 阶段不需要 LLM
        # LLM 配置
        llm_cfg = agent_cfg.get_llm_config(stage.value)
        # 连接 LLM 服务端
        llms[stage] = build_llm(llm_cfg)

    # 构建 CompletionConfig 映射
    completion_configs: dict[ReflectStage, CompletionConfig] = {}
    for stage in ReflectStage:
        # LLM 配置
        llm_cfg = agent_cfg.get_llm_config(stage.value)
        completion_configs[stage] = CompletionConfig(
            max_tokens=llm_cfg.max_tokens,
            stream=llm_cfg.stream,
        )

    def workflow_factory() -> IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent]:
        # 构建工作流实例
        workflow = BaseWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent](
            valid_states=valid_states,
            init_state=init_state,
            transitions=transitions,
            name="reflect_workflow",
            completion_configs=completion_configs,
            llms=llms,
            actions=actions,
            prompts=prompts,
            observe_funcs=observe_funcs,
            event_chain=event_chain,
            tools={end_workflow_tool.name: (end_workflow_tool, set())},
        )
        return workflow
    # 关联工作流到智能体
    agent.set_workflow(workflow_factory)
    return agent
