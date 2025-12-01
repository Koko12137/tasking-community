from typing import Any, Callable, Awaitable

from loguru import logger
from fastmcp import Client
from fastmcp.client.transports import ClientTransport
from fastmcp.tools import Tool as FastMcpTool

from .interface import IAgent, IHumanClient
from .base import BaseAgent
from ..state_machine.task import ITask, TaskState, TaskEvent, RequirementTaskView, DocumentTreeTaskView
from ..state_machine.workflow import ReActStage, ReActEvent, IWorkflow, BaseWorkflow
from ...llm import OpenAiLLM, ILLM
from ...model import Message, StopReason, Role, IQueue, CompletionConfig, HumanInterfere, get_settings
from ...utils.io import read_document
from ...utils.string.extract import extract_by_label


NO_OUTPUT_TEMPLATE = """没有从标签 '{label}' 中提取到任何内容，但工作流被请求结束，请确保输出内容被正确包裹在该标签内。

进入错误状态，开始错误次数计数。当前错误次数 {error_count}，超过最大错误次数 {max_error_count} 将强制结束工作流。
"""


def end_workflow(kwargs: dict[str, Any] = {}) -> None:
    """结束工作流，会检查最后一个 Message 中是否有最终输出。
    
    Args:
        kwargs (dict[str, Any], optional): 
            注入参数字典，必须包含 'task' 键对应的 ITask 实例. Defaults to {}.

    Raises:
        Exception: 如果输出提取失败，没有找到输出的内容，无法正确结束工作流。
    """
    if "task" not in kwargs:
        raise RuntimeError("结束工作流工具缺少必要的 'task' 注入参数")
    if "message" not in kwargs:
        raise RuntimeError("结束工作流工具缺少必要的 'message' 注入参数")
    
    # 获取注入的 Task
    task: ITask[TaskState, TaskEvent] = kwargs["task"]
    # 获取当前状态
    current_state = task.get_current_state()
    
    # 获取注入的 Message
    message: Message = kwargs['message']
    # 确认发送方是 ASSISTANT
    assert message.role == Role.ASSISTANT, "最后一个 Message 不是 Assistant Message"
    # 从 Message 中获取输出内容
    output_content = extract_by_label(message.content, "output")
    if output_content == "":
        # 进入错误处理逻辑
        raise Exception(NO_OUTPUT_TEMPLATE.format(
            label="<output>",
            error_count=task.get_state_visit_count(current_state),
            max_error_count=task.get_max_revisit_limit(),
        ))
    else:
        # 设置任务为完成状态，存储输出内容
        task.set_completed(output=output_content)


# 提供给 LLM 的文档
END_WORKFLOW_DOC = """结束工作流工具，用于结束当前工作流并提取最终输出结果。会检查倒数第三个 Message 中是否有最终输出。

Args:
    不需要参数输入

Raises:
    Exception: 如果输出提取失败，没有找到输出的内容，无法正确结束工作流。
"""


def get_react_stages() -> set[ReActStage]:
    """获取常用工作流阶段集合
    -  INIT, PROCESSING, COMPLETED

    Returns:
        常用工作流阶段集合
    """
    return {
        ReActStage.PROCESSING,
        ReActStage.COMPLETED,
    }


def get_react_event_chain() -> list[ReActEvent]:
    """获取常用工作流事件链
    -  PROCESS, COMPLETE

    Returns:
        常用工作流事件链
    """
    return [
        ReActEvent.PROCESS,
        ReActEvent.COMPLETE,
    ]


def get_react_actions(
    agent: IAgent[ReActStage, ReActEvent, TaskState, TaskEvent],
) -> dict[
    ReActStage,
    Callable[
        [
            IWorkflow[ReActStage, ReActEvent, TaskState, TaskEvent],
            dict[str, Any],
            IQueue[Message],
            ITask[TaskState, TaskEvent],
        ],
        Awaitable[ReActEvent]
    ]
]:
    """获取常用工作流动作定义

    Args:
        agent (IAgent): 关联的智能体实例

    Returns:
        常用工作流动作定义
    """
    actions: dict[ReActStage, Callable[
        [
            IWorkflow[ReActStage, ReActEvent, TaskState, TaskEvent],
            dict[str, Any],
            IQueue[Message],
            ITask[TaskState, TaskEvent],
        ],
        Awaitable[ReActEvent]]
    ] = {}

    # REASONING 阶段动作定义
    async def reason(
        workflow: IWorkflow[ReActStage, ReActEvent, TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[TaskState, TaskEvent],
    ) -> ReActEvent:
        """REASONING 阶段动作函数

        Args:
            workflow (IWorkflow[reactStage, reactEvent, TaskState, TaskEvent]): 工作流实例
            context (dict[str, Any]): 上下文字典，用于传递用户ID/AccessToken/TraceID等信息
            queue (IQueue[Message]): 数据队列，用于输出数据
            task (ITask[TaskState, TaskEvent]): 任务实例

        Returns:
            reactEvent: 触发的事件类型
        """
        # 获取任务的推理配置信息
        completion_config = workflow.get_completion_config()
        # 获取推理配置中的工具信息
        tools = completion_config.tools
        # 更新工具信息
        workflow_tools = workflow.get_tools()
        # 更新工具信息
        for _, (tool, _) in workflow_tools.items():
            tools.append(tool)
        completion_config.update(tools=tools)

        # 获取当前工作流的状态
        current_state = workflow.get_current_state()
        if current_state != ReActStage.PROCESSING:
            raise RuntimeError(f"当前工作流状态错误，期望：{ReActStage.PROCESSING}，实际：{current_state}")
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
                completion_config=completion_config,
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
            return ReActEvent.PROCESS

        # 从 Message 中获取结束工作流的标志内容
        finish_flag = extract_by_label(message.content, "finish", "finish_flag", "finish_workflow")

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
                        content="由于前置工具调用出错，后续工具调用被禁止继续执行"
                    )
                    continue

                try:
                    # 注入 Task 和 Workflow，并开始执行工具
                    result = await agent.act(
                        context=context,
                        queue=queue,
                        tool_call=tool_call,
                        task=task,
                        message=message,
                    )
                except HumanInterfere as e:
                    # 将人类介入信息反馈到任务
                    result = Message(
                        role=Role.USER,
                        content=str(e),
                        is_error=True,
                    )
                    # 禁止后续工具调用执行
                    allow_tool = False
                    
                # 工具调用结果反馈到任务
                task.get_context().append_context_data(result)
                # 检查调用错误状态
                if result.is_error:
                    # 将任务设置为错误状态
                    task.set_error(result.content)
                    # 停止执行剩余的工具
                    allow_tool = False

        # 没有调用工具，手动检查结束标志位
        elif finish_flag.upper() == "TRUE":
            # 手动调用结束工作流
            end_workflow({"task": task, "message": message})

        if task.is_completed():
            return ReActEvent.COMPLETE

        return ReActEvent.PROCESS

    # 添加到动作定义字典
    actions[ReActStage.PROCESSING] = reason

    return actions


def get_react_transition() -> dict[
    tuple[ReActStage, ReActEvent],
    tuple[
        ReActStage,
        Callable[[IWorkflow[ReActStage, ReActEvent, TaskState, TaskEvent]], Awaitable[None] | None] | None
    ]
]:
    """获取常用工作流转换规则   # BUG: 规则会造成死循环
    -  PROCESSING + PROCESS -> PROCESSING
    -  PROCESSING + COMPLETE -> COMPLETED

    Returns:
        常用工作流转换规则
    """
    transition: dict[
        tuple[ReActStage, ReActEvent],
        tuple[
            ReActStage,
            Callable[[IWorkflow[ReActStage, ReActEvent, TaskState, TaskEvent]], Awaitable[None] | None] | None
        ]
    ] = {}

    # 1. PROCESSING -> PROCESSING (事件： PROCESS)
    def on_processing_to_processing(
        workflow: IWorkflow[ReActStage, ReActEvent, TaskState, TaskEvent],
    ) -> None:
        """从 PROCESSING 到 PROCESSING 的转换回调函数"""
        logger.debug(
            f"Transitioning from PROCESSING to PROCESSING for workflow {workflow.get_id()}"
        )

    # 添加转换规则
    transition[(ReActStage.PROCESSING, ReActEvent.PROCESS)] = (
        ReActStage.PROCESSING, on_processing_to_processing
    )

    # 2. PROCESSING -> COMPLETED (事件： COMPLETE)
    def on_processing_to_completed(
        workflow: IWorkflow[ReActStage, ReActEvent, TaskState, TaskEvent],
    ) -> None:
        """从 PROCESSING 到 COMPLETED 的转换回调函数"""
        logger.debug(f"Transitioning from PROCESSING to COMPLETED for workflow {workflow.get_id()}")

    # 添加转换规则
    transition[(ReActStage.PROCESSING, ReActEvent.COMPLETE)] = (
        ReActStage.COMPLETED, on_processing_to_completed
    )

    return transition


def build_react_agent(
    name: str, 
    tool_service: Client[ClientTransport] | None = None,
    human_client: IHumanClient | None = None,
    actions: dict[
        ReActStage, 
        Callable[
            [
                IWorkflow[ReActStage, ReActEvent, TaskState, TaskEvent],
                dict[str, Any],
                IQueue[Message],
                ITask[TaskState, TaskEvent],
            ], 
            Awaitable[ReActEvent]
        ]
    ] | None = None,
    transitions: dict[
        tuple[ReActStage, ReActEvent],
        tuple[
            ReActStage,
            Callable[[IWorkflow[ReActStage, ReActEvent, TaskState, TaskEvent]], Awaitable[None] | None] | None
        ]
    ] | None = None,
    prompts: dict[ReActStage, str] | None = None,
    observe_funcs: dict[
        ReActStage,
        Callable[[ITask[TaskState, TaskEvent], dict[str, Any]], Message]
    ] | None = None,
) -> IAgent[ReActStage, ReActEvent, TaskState, TaskEvent]:
    """构建一个简单的智能体实例

    Args:
        name: 智能体名称，必填，用于在 settings 中读取对应的配置
        tool_service: 工具服务客户端，可选，如果未提供则不关联工具服务
        human_client: 人类客户端接口，可选，如果未提供则不关联人类客户端
        actions: 动作定义，可选，如果未提供则使用默认定义
        transitions: 状态转换规则，可选，如果未提供则使用默认定义
        prompts: 提示词，可选，如果未提供则使用默认定义
        observe_funcs: 观察函数，可选，如果未提供则使用默认定义

    Returns:
        IAgent[reactStage, reactEvent, TaskState, TaskEvent]: 智能体实例
    """
    # 获取全局设置
    settings = get_settings()
    # 获取智能体的配置
    agent_cfg = settings.get_agent_config(name)
    if agent_cfg is None:
        raise ValueError(f"未找到名为 '{name}' 的智能体配置")
    
    llms: dict[ReActStage, ILLM] = {}
    for stage in ReActStage:
        # LLM 配置
        llm_cfg = agent_cfg.get_llm_config(stage.value)
        # 连接 LLM 服务端
        llms[stage] = OpenAiLLM(
            model=llm_cfg.model or "GLM-4.6",
            base_url=llm_cfg.base_url or "https://open.bigmodel.cn/api/coding/paas/v4",
            api_key=llm_cfg.api_key
        )
    
    # 构建基础 Agent 实例
    agent = BaseAgent[ReActStage, ReActEvent, TaskState, TaskEvent](
        name=name,
        agent_type=agent_cfg.agent_type,
        llms=llms,
        tool_service=tool_service,
        human_client=human_client,
    )
    # 获取 event chain
    event_chain = get_react_event_chain()
    # 获取 valid states
    valid_states = get_react_stages()
    # 获取初始状态
    init_state = ReActStage.PROCESSING
    # 获取转换规则
    transitions = transitions if transitions is not None else get_react_transition()
    # 获取动作定义
    actions = actions if actions is not None else get_react_actions(agent)
    # 定义提示词
    prompts = prompts if prompts is not None else {
        ReActStage.PROCESSING: read_document("workflow/react/processing.md"),
    }
    # 定义观察函数
    def observe_task_view(task: ITask[TaskState, TaskEvent], kwargs: dict[str, Any]) -> Message:
        """观察任务并生成消息"""    # TODO: 要根据状态组合观察方法
        view = RequirementTaskView[TaskState, TaskEvent]()
        content = view(task, **kwargs)
        
        # 如果任务已完成，则添加文档树视图，因为没有记忆机制
        if task.is_completed():
            add_content = DocumentTreeTaskView[TaskState, TaskEvent]()(task, **kwargs)
            # 新建 Message
            message = Message(
                role=Role.USER,
                multimodal_content=[
                    {"type": "text", "text": content},
                    {"type": "text", "text": "\n\n--- 任务已完成，以下是任务文档结果 ---\n\n"},
                    {"type": "text", "text": add_content},
                ]
            )
            return message

        return Message(role=Role.USER, content=content)

    observe_funcs = observe_funcs if observe_funcs is not None else {
        ReActStage.PROCESSING: observe_task_view,
    }
    
    # 构建结束工作流工具实例
    end_workflow_tool = FastMcpTool.from_function(
        fn= end_workflow,
        name="end_workflow",
        description=END_WORKFLOW_DOC,
        exclude_args=["kwargs"],
    )
    
    # 构建 CompletionConfig 映射
    completion_configs: dict[ReActStage, CompletionConfig] = {}
    for stage in ReActStage:
        # LLM 配置
        llm_cfg = agent_cfg.get_llm_config(stage.value)
        completion_configs[stage] = CompletionConfig(
            temperature=llm_cfg.temperature,
            max_tokens=llm_cfg.max_tokens,
            tools=[],
        )
    
    # 构建工作流实例
    workflow = BaseWorkflow[ReActStage, ReActEvent, TaskState, TaskEvent](
        valid_states=valid_states,
        init_state=init_state,
        transitions=transitions,
        name="reactWorkflow",
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
