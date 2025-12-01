from enum import Enum
from typing import Any, Callable, Awaitable

from loguru import logger
from fastmcp import Client
from fastmcp.client.transports import ClientTransport
from fastmcp.tools import Tool as FastMcpTool

from .interface import IAgent, IHumanClient
from .base import BaseAgent
from .react import end_workflow, END_WORKFLOW_DOC
from ..state_machine.workflow import IWorkflow, BaseWorkflow
from ..state_machine.task import ITask, TaskState, TaskEvent, RequirementTaskView
from ...llm import OpenAiLLM, ILLM
from ...model import Message, Role, IQueue, CompletionConfig, HumanInterfere, get_settings
from ...utils.io import read_markdown


class SuperviseStage(str, Enum):
    """supervise 工作流阶段枚举"""
    CLARIFYING = "CLARIFYING"
    FINISHED = "FINISHED"
    
    @classmethod
    def list_stages(cls) -> list[str]:
        """列出所有阶段名称"""
        return [stage.name for stage in cls]
    
    
class SuperviseEvent(str, Enum):
    """supervise 工作流事件枚举"""
    CLARIFY = "CLARIFY"
    FINISH = "FINISH"


def get_supervise_stages() -> set[SuperviseStage]:
    """获取 Supervise 工作流的阶段
    - CLARIFYING, FINISHED
    
    Returns:
        supervise 工作流的阶段集合
    """
    return {
        SuperviseStage.CLARIFYING,
        SuperviseStage.FINISHED,
    }
    

def get_supervise_event_chain() -> list[SuperviseEvent]:
    """获取常用工作流事件链
    -  CLARIFY
    -  FINISH

    Returns:
        supervise工作流事件链
    """
    return [
        SuperviseEvent.CLARIFY,
        SuperviseEvent.FINISH,
    ]


def get_supervise_transition() -> dict[
    tuple[SuperviseStage, SuperviseEvent],
    tuple[
        SuperviseStage,
        Callable[[IWorkflow[SuperviseStage, SuperviseEvent, TaskState, TaskEvent]], Awaitable[None] | None] | None
    ]
]:
    """获取常用工作流转换规则
    -  CLARIFYING -> CLARIFYING (事件： CLARIFY)
    -  CLARIFYING -> FINISHED (事件： FINISH)

    Returns:
        常用工作流转换规则
    """
    transition: dict[
        tuple[SuperviseStage, SuperviseEvent],
        tuple[
            SuperviseStage,
            Callable[[IWorkflow[SuperviseStage, SuperviseEvent, TaskState, TaskEvent]], Awaitable[None] | None] | None
        ]
    ] = {}
    
    # 1. CLARIFYING -> CLARIFYING (事件： CLARIFY)
    async def on_clarifying_to_clarifying(
        workflow: IWorkflow[SuperviseStage, SuperviseEvent, TaskState, TaskEvent],
    ) -> None:
        """从 CLARIFYING 到 CLARIFYING 的转换回调函数"""
        logger.debug(f"Workflow {workflow.get_id()} Transition: {SuperviseStage.CLARIFYING} -> {SuperviseStage.CLARIFYING}.")
        
    # 添加转换规则
    transition[(SuperviseStage.CLARIFYING, SuperviseEvent.CLARIFY)] = (SuperviseStage.CLARIFYING, on_clarifying_to_clarifying)

    # 2. CLARIFYING -> FINISHED (事件： FINISH)
    async def on_clarify_to_finished(
        workflow: IWorkflow[SuperviseStage, SuperviseEvent, TaskState, TaskEvent],
    ) -> None:
        """从 CLARIFYING 到 FINISHED 的转换回调函数"""
        logger.debug(f"Workflow {workflow.get_id()} Transition: {SuperviseStage.CLARIFYING} -> {SuperviseStage.FINISHED}.")
        
    # 添加转换规则
    transition[(SuperviseStage.CLARIFYING, SuperviseEvent.FINISH)] = (SuperviseStage.FINISHED, on_clarify_to_finished)

    return transition


def get_supervise_actions(
    agent: IAgent[SuperviseStage, SuperviseEvent, TaskState, TaskEvent],
) -> dict[
    SuperviseStage, 
    Callable[
        [
            IWorkflow[SuperviseStage, SuperviseEvent, TaskState, TaskEvent],
            dict[str, Any],
            IQueue[Message],
            ITask[TaskState, TaskEvent],
        ], 
        Awaitable[SuperviseEvent]
    ]
]:
    """获取常用工作流动作定义
    -  CLARIFYING 阶段动作定义
    -  FINISHED 阶段动作定义

    Args:
        agent (IAgent): 关联的智能体实例

    Returns:
        常用工作流动作定义
    """
    actions: dict[SuperviseStage, Callable[
        [
            IWorkflow[SuperviseStage, SuperviseEvent, TaskState, TaskEvent],
            dict[str, Any],
            IQueue[Message],
            ITask[TaskState, TaskEvent],
        ], 
        Awaitable[SuperviseEvent]]
    ] = {}
    
    # CLARIFYING 阶段动作定义
    async def clarify(
        workflow: IWorkflow[SuperviseStage, SuperviseEvent, TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[TaskState, TaskEvent],
    ) -> SuperviseEvent:
        """CLARIFYING 阶段动作函数
        
        Args:
            context (dict[str, Any]): 上下文字典，用于传递用户ID/AccessToken/TraceID等信息
            queue (IQueue[Message]): 数据队列，用于输出数据
            workflow (IWorkflow[SuperviseStage, SuperviseEvent, TaskState, TaskEvent]): 工作流实例
            task (ITask[TaskState, TaskEvent]): 任务实例

        Returns:
            SuperviseEvent: 触发的事件类型
        """
        # 获取当前工作流的状态
        current_state = workflow.get_current_state()
        if current_state != SuperviseStage.CLARIFYING:
            raise RuntimeError(f"当前工作流状态错误，期望：{SuperviseStage.CLARIFYING}，实际：{current_state}")

        # 获取当前工作流的提示词
        prompt = workflow.get_prompt()
        # 创建新的任务消息
        message = Message(role=Role.USER, content=prompt)
        # 添加 message 到当前任务上下文
        task.get_context().append_context_data(message)
        # 观察 Task
        observe = await agent.observe(
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
                llm_name=current_state.name, 
                observe=observe, 
                completion_config=workflow.get_completion_config(),
            )
            # 推理结果反馈到任务
            task.get_context().append_context_data(message)
        except HumanInterfere as e:
            # 将人类介入信息反馈到任务
            task.get_context().append_context_data(Message(
                role=Role.USER,
                content=str(e)
            ))
            # 重新进入处理流程
            return SuperviseEvent.CLARIFY
                    
        return SuperviseEvent.FINISH
    
    # 添加到动作定义字典
    actions[SuperviseStage.CLARIFYING] = clarify

    return actions


def build_supervise_agent(
    name: str,
    tool_service: Client[ClientTransport] | None = None,
    human_client: IHumanClient | None = None,
    actions: dict[
        SuperviseStage, 
        Callable[
            [
                IWorkflow[SuperviseStage, SuperviseEvent, TaskState, TaskEvent],
                dict[str, Any],
                IQueue[Message],
                ITask[TaskState, TaskEvent],
            ], 
            Awaitable[SuperviseEvent]
        ]
    ] | None = None,
    transitions: dict[
        tuple[SuperviseStage, SuperviseEvent],
        tuple[
            SuperviseStage,
            Callable[[IWorkflow[SuperviseStage, SuperviseEvent, TaskState, TaskEvent]], Awaitable[None] | None] | None
        ]
    ] | None = None,
    prompts: dict[SuperviseStage, str] | None = None,
    observe_funcs: dict[
        SuperviseStage,
        Callable[[ITask[TaskState, TaskEvent], dict[str, Any]], Message]
    ] | None = None,
) -> IAgent[SuperviseStage, SuperviseEvent, TaskState, TaskEvent]:
    """构建一个 `Supervise` 的智能体实例

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
    
    llms: dict[SuperviseStage, ILLM] = {}
    for stage in SuperviseStage:
        # LLM 配置
        llm_cfg = agent_cfg.get_llm_config(stage.value)
        # 连接 LLM 服务端
        llms[stage] = OpenAiLLM(
            model=llm_cfg.model or "GLM-4.6",
            base_url=llm_cfg.base_url or "https://open.bigmodel.cn/api/coding/paas/v4",
            api_key=llm_cfg.api_key
        )
    
    # 构建基础 Agent 实例
    agent = BaseAgent[SuperviseStage, SuperviseEvent, TaskState, TaskEvent](
        name=name,
        agent_type=agent_cfg.agent_type,
        llms=llms,
        tool_service=tool_service,
        human_client=human_client,
    )
    # 获取 event chain
    event_chain = get_supervise_event_chain()
    # 获取 valid states
    valid_states = get_supervise_stages()
    # 获取初始状态
    init_state = SuperviseStage.CLARIFYING
    # 获取动作定义
    actions = actions if actions is not None else get_supervise_actions(agent)
    # 获取转换规则
    transitions = transitions if transitions is not None else get_supervise_transition()
    # 定义提示词
    prompts = prompts if prompts is not None else {
        SuperviseStage.CLARIFYING: read_markdown("workflow/supervise/system.md"),
    }
    # 定义观察函数
    def observe_task_view(task: ITask[TaskState, TaskEvent], kwargs: dict[str, Any]) -> Message:
        """观察任务并生成消息"""    # TODO: 要根据状态组合观察方法
        view = RequirementTaskView[TaskState, TaskEvent]()
        content = view(task, **kwargs)
        return Message(role=Role.USER, content=content)

    observe_funcs = observe_funcs if observe_funcs is not None else {
        SuperviseStage.CLARIFYING: observe_task_view,
    }
    
    # 构建结束工作流工具实例
    end_workflow_tool = FastMcpTool.from_function(
        fn= end_workflow,
        name="end_workflow",
        description=END_WORKFLOW_DOC,
        exclude_args=["workflow", "task"],
    )
    
    # 构建 CompletionConfig 映射
    completion_configs: dict[SuperviseStage, CompletionConfig] = {}
    for stage in SuperviseStage:
        # LLM 配置
        llm_cfg = agent_cfg.get_llm_config(stage.value)
        completion_configs[stage] = CompletionConfig(
            temperature=llm_cfg.temperature,
            max_tokens=llm_cfg.max_tokens,
            tools=[],
        )
    
    # 构建工作流实例
    workflow = BaseWorkflow[SuperviseStage, SuperviseEvent, TaskState, TaskEvent](
        valid_states=valid_states,
        init_state=init_state,
        transitions=transitions,
        name="superviseWorkflow",
        completion_configs=completion_configs,
        actions=actions,
        prompts=prompts,
        observe_funcs=observe_funcs,
        event_chain=event_chain,
        tools={end_workflow_tool.name: (end_workflow_tool, set())},
    )
    # 关联工作流到智能体
    agent.set_workflow(workflow)
    return agent
