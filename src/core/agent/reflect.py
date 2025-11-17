from typing import Any, Callable, Awaitable

from loguru import logger
from fastmcp import Client
from fastmcp.client.transports import ClientTransport
from fastmcp.tools import Tool as FastMcpTool

from src.core.agent.interface import IAgent
from src.core.agent.base import BaseAgent
from src.core.agent.react import end_workflow, END_WORKFLOW_DOC
from src.core.state_machine.workflow import ReflectStage, ReflectEvent, IWorkflow, BaseWorkflow
from src.core.state_machine.task import ITask, TaskState, TaskEvent, RequirementTaskView
from src.llm import OpenAiLLM, ILLM
from src.model import Message, StopReason, Role, get_settings, IQueue, CompletionConfig
from src.utils.io import read_markdown
from src.utils.string.extract import extract_by_label


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
    agent: IAgent[ReflectStage, ReflectEvent, TaskState, TaskEvent],
) -> dict[
    ReflectStage, 
    Callable[
        [
            IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent],
            dict[str, Any],
            IQueue[Message],
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
            IQueue[Message],
            ITask[TaskState, TaskEvent],
        ], 
        Awaitable[ReflectEvent]]
    ] = {}
    
    # REASONING 阶段动作定义
    async def reason(
        workflow: IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
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
        # === Thinking ===
        # 获取当前工作流的状态
        current_state = workflow.get_current_state()
        if current_state != ReflectStage.REASONING:
            raise RuntimeError(f"当前工作流状态错误，期望：{ReflectStage.REASONING}，实际：{current_state}")
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
        # 记录观察结果
        logger.debug(f"Observe: \n{observe[-1].content}")
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
        # 记录推理信息
        logger.debug(f"{str(agent)}: \n{message}")
        
        # === Act ===
        # 允许执行工具标志位
        allow_tool: bool = True
        # Get all the tool calls from the assistant message
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

                # 开始执行工具，如果是工具服务的工具，则 task/workflow 不会被注入到参数中
                result = await agent.act(
                    context=context,
                    queue=queue,
                    tool_call=tool_call,
                    task=task,
                    workflow=workflow,
                )
                # Log the tool call result
                logger.debug(f"Tool Call Result: \n{result}")
                # 工具调用结果反馈到任务
                task.get_context().append_context_data(result)
                # 检查调用错误状态
                if result.is_error:
                    # 将任务设置为错误状态
                    task.set_error(result.content)
                    # 停止执行剩余的工具
                    allow_tool = False
                    
        return ReflectEvent.REFLECT
    
    # 添加到动作定义字典
    actions[ReflectStage.REASONING] = reason
    
    # REFLECTION 阶段动作定义
    async def reflect(
        workflow: IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent],
        context: dict[str, Any],
        queue: IQueue[Message],
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
        # 获取任务的推理配置
        completion_config = workflow.get_completion_config()
        # 更新推理配置以适应反思阶段
        completion_config.update(
            tools=[workflow.get_end_workflow_tool()],
            stop_words=["</final_flag>", "</finish>", "</finish_flag>", "</end_flag>"],
        )
        
        # === Thinking ===
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
        # 记录观察结果
        logger.debug(f"Observe: \n{observe[-1].content}")
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
        # 记录推理信息
        logger.debug(f"{str(agent)}: \n{message}")

        # 从 Message 中获取结束工作流的标志内容
        finish_flag = extract_by_label(message.content, "finish", "finish_flag", "finish_workflow")

        # === Act ===
        # 允许执行工具标志位
        allow_tool: bool = True
        # Get all the tool calls from the assistant message
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

                # 注入 Task 和 Workflow，并开始执行工具
                result = await agent.act(
                    context=context,
                    queue=queue,
                    tool_call=tool_call,
                    task=task,
                    workflow=workflow,
                )
                # Log the tool call result
                logger.debug(f"Tool Call Result: \n{result}")
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
            end_workflow(kwargs={
                "task": task, 
                "message": task.get_context().get_context_data()[-3]
            })

        if task.is_error():
            return ReflectEvent.REASON
        else:
            return ReflectEvent.FINISH

    # 添加到动作定义字典
    actions[ReflectStage.REFLECTING] = reflect

    return actions


def build_reflect_agent(
    name: str,
    tool_service: Client[ClientTransport] | None = None,
    actions: dict[
        ReflectStage, 
        Callable[
            [
                IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent],
                dict[str, Any],
                IQueue[Message],
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
    custom_end_workflow: Callable[
        [ITask[TaskState, TaskEvent], IWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent]],
        None
    ] | None = None,
) -> IAgent[ReflectStage, ReflectEvent, TaskState, TaskEvent]:
    """构建一个 `Reason - Act - Reflection` 的智能体实例

    Args:
        name: 智能体名称，必填，用于在 settings 中读取对应的配置
        tool_service: 工具服务客户端，可选，如果未提供则不关联工具服务
        actions: 动作定义，可选，如果未提供则使用默认定义
        transitions: 状态转换规则，可选，如果未提供则使用默认定义
        prompts: 提示词，可选，如果未提供则使用默认定义
        observe_funcs: 观察函数，可选，如果未提供则使用默认定义
        custom_end_workflow: 结束工作流函数，可选，如果未提供则使用默认定义

    Returns:
        智能体实例
    """
    # 获取全局设置
    settings = get_settings()
    # 获取智能体的配置
    agent_cfg = settings.get_agent_config(name)
    if agent_cfg is None:
        raise ValueError(f"未找到名为 '{name}' 的智能体配置")
    
    llms: dict[ReflectStage, ILLM] = {}
    for stage in ReflectStage:
        # LLM 配置
        llm_cfg = agent_cfg.get_llm_config(stage.value)
        # 连接 LLM 服务端
        llms[stage] = OpenAiLLM(
            model=llm_cfg.model or "GLM-4.6",
            base_url=llm_cfg.base_url or "https://open.bigmodel.cn/api/coding/paas/v4",
            api_key=llm_cfg.api_key
        )
    
    # 构建基础 Agent 实例
    agent = BaseAgent[ReflectStage, ReflectEvent, TaskState, TaskEvent](
        name=name,
        agent_type=agent_cfg.agent_type,
        llms=llms,
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
        ReflectStage.REASONING: read_markdown("prompt/workflow/reflect/system.md"),
    }
    # 定义观察函数
    def observe_task_view(task: ITask[TaskState, TaskEvent], kwargs: dict[str, Any]) -> Message:
        """观察任务并生成消息"""    # TODO: 要根据状态组合观察方法
        view = RequirementTaskView[TaskState, TaskEvent]()
        content = view(task, **kwargs)
        return Message(role=Role.USER, content=content)

    observe_funcs = observe_funcs if observe_funcs is not None else {
        ReflectStage.REASONING: observe_task_view,
        ReflectStage.REFLECTING: observe_task_view,
    }
    
    # 构建结束工作流工具实例
    end_workflow_tool = FastMcpTool.from_function(
        fn= custom_end_workflow if custom_end_workflow is not None else end_workflow,
        name="end_workflow",
        description=END_WORKFLOW_DOC,
        exclude_args=["workflow", "task"],
    )
    
    # 构建 CompletionConfig 映射
    completion_configs: dict[ReflectStage, CompletionConfig] = {}
    for stage in ReflectStage:
        # LLM 配置
        llm_cfg = agent_cfg.get_llm_config(stage.value)
        completion_configs[stage] = CompletionConfig(
            temperature=llm_cfg.temperature,
            max_tokens=llm_cfg.max_tokens,
            tools=[],
        )
    
    # 构建工作流实例
    workflow = BaseWorkflow[ReflectStage, ReflectEvent, TaskState, TaskEvent](
        valid_states=valid_states,
        init_state=init_state,
        transitions=transitions,
        name="reflectWorkflow",
        completion_configs=completion_configs,
        actions=actions,
        prompts=prompts,
        observe_funcs=observe_funcs,
        event_chain=event_chain,
        end_workflow=end_workflow_tool,
    )
    # 关联工作流到智能体
    agent.set_workflow(workflow)
    return agent
