import inspect
from copy import deepcopy
from typing import Any, Callable, Awaitable
from traceback import format_exc

from fastmcp import Client
from fastmcp.client.transports import ClientTransport
from mcp.types import CallToolResult, TextContent
from asyncer import asyncify

from .interface import IAgent, IHumanClient
from ..state_machine.const import EventT, StateT
from ..state_machine.task import ITask
from ..state_machine.workflow import WorkflowEventT, WorkflowStageT, IWorkflow
from ...model import CompletionConfig, Message, Role, ToolCallRequest, IQueue
from ...llm import ILLM


class BaseHumanClient(IHumanClient):
    """基础Human in the loop客户端实现：提供IHumanClient接口的基础实现，供具体HumanClient继承与扩展"""
    
    def __init__(self) -> None:
        pass

    async def ask_human(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        message: Message,
    ) -> Message:
        """发送消息给人类进行交互
        
        参数:
            context (dict[str, Any]): 当前请求的上下文信息, 包含用户信息、请求元数据等
            queue (IQueue[Message]): 向人类发送消息的队列
            message (Message): 发送给人类的消息内容
            
        返回:
            Message: 人类回复的消息
        """
        # 发送消息到队列
        await queue.put(message)
        
        # 等待人类回复
        return await self.retrieve_human_response(context, queue)
        

    async def retrieve_human_response(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        timeout: float | None = None,
    ) -> Message:
        """检索人类的回复消息
        
        参数:
            context (dict[str, Any]): 当前请求的上下文信息, 包含用户信息、请求元数据等
            queue (IQueue[Message]): 用于向人类发送消息的队列
            timeout (float | None): 等待人类回复的超时时间，单位为秒。默认为None，表示无限等待
            
        返回:
            Message: 人类回复的消息
            
        异常:
            TimeoutError: 如果在指定的超时时间内没有收到人类的回复
            HumanInterfere: 如果人类用户介入了流程
        """
        raise NotImplementedError("retrieve_human_response method must be implemented by subclasses.")


class BaseAgent(IAgent[WorkflowStageT, WorkflowEventT, StateT, EventT]):
    """基础Agent实现：提供IAgent接口的基础实现，供具体Agent继承与扩展"""
    _id: str
    _name: str
    _type: str
    # Large Language Models
    _llms: dict[WorkflowStageT, ILLM]
    # Workflow
    _workflow: IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT] | None
    # Tool Service
    _tool_service: Client[ClientTransport] | None
    # Human in the loop client
    _human_client: IHumanClient | None
    
    # Run Hooks
    _pre_run_once_hooks: list[Callable[
        [dict[str, Any], IQueue[Message], ITask[StateT, EventT]], 
        Awaitable[None] | None
    ]]
    """单次执行前钩子函数列表，会按顺序执行。钩子函数的签名为:
    
    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        task (ITask[StateT, EventT]): 要运行的任务
    """
    _post_run_once_hooks: list[Callable[
        [dict[str, Any], IQueue[Message], ITask[StateT, EventT]], 
        Awaitable[None] | None
    ]]
    """单次执行后钩子函数列表，会按顺序执行。钩子函数的签名为:

    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        task (ITask[StateT, EventT]): 要运行的任务
    """

    # Observe Hooks
    _pre_observe_hooks: list[Callable[
        [dict[str, Any], IQueue[Message], ITask[StateT, EventT]], 
        Awaitable[None] | None
    ]]
    """观察前钩子函数列表，会按顺序执行。钩子函数的签名为:

    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        task (ITask[StateT, EventT]): 要运行的任务
    """
    _post_observe_hooks: list[Callable[
        [dict[str, Any], IQueue[Message], ITask[StateT, EventT], list[Message]], 
        Awaitable[None] | None
    ]]
    """观察后钩子函数列表，会按顺序执行。钩子函数的签名为:
    
    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        task (ITask[StateT, EventT]): 要运行的任务
        observe_res (list[Message]): 观察结果
    """

    # Think Hooks
    _pre_think_hooks: list[Callable[
        [dict[str, Any], IQueue[Message], list[Message]], 
        Awaitable[None] | None
    ]]
    """思考前钩子函数列表，会按顺序执行。钩子函数的签名为:
    
    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        observe_res (list[Message]): 观察结果
    """
    _post_think_hooks: list[Callable[
        [dict[str, Any], IQueue[Message], Message], 
        Awaitable[None] | None
    ]]
    """思考后钩子函数列表，会按顺序执行。钩子函数的签名为:
    
    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        think_result (Message): 思考结果
    """
    
    # Act Hooks
    
    _pre_act_hooks: list[Callable[
        [dict[str, Any], IQueue[Message], ITask[StateT, EventT]], 
        Awaitable[None] | None
    ]]
    """行动前钩子函数列表，会按顺序执行。钩子函数的签名为:
    
    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        task (ITask[StateT, EventT]): 要运行的任务
    """
    _post_act_hooks: list[Callable[
        [dict[str, Any], IQueue[Message], ITask[StateT, EventT], Message], 
        Awaitable[None] | None
    ]]
    """行动后钩子函数列表，会按顺序执行。钩子函数的签名为:
    
    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        task (ITask[StateT, EventT]): 要运行的任务
        act_result (Message): 行动结果
    """

    def __init__(
        self,
        name: str,
        agent_type: str,
        llms: dict[WorkflowStageT, ILLM],
        tool_service: Client[ClientTransport] | None = None,
        human_client: IHumanClient | None = None,
    ) -> None:
        """初始化基础Agent实例，钩子函数列表为空，等待后续注册
        
        Args:
            name (str): Agent的名称
            agent_type (str): Agent的类型
            llms (dict[WorkflowStageT, ILLM]): 智能体的语言模型集合，按工作流阶段映射
            tool_service (Client[ClientTransport] | None): 工具服务客户端实例，默认为None
            human_client (IHumanClient | None): Human in the loop客户端实例，默认为None
        """
        self._id = f"agent_{id(self)}"
        self._name = name
        self._type = agent_type
        self._llms = llms
        self._workflow = None
        self._tool_service = tool_service
        # Human in the loop client
        self._human_client = human_client
        # Hooks container
        self._pre_run_once_hooks = []
        self._post_run_once_hooks = []
        self._pre_observe_hooks = []
        self._post_observe_hooks = []
        self._pre_think_hooks = []
        self._post_think_hooks = []
        self._pre_act_hooks = []
        self._post_act_hooks = []

    # ********** 基础信息 **********
    
    def get_id(self) -> str:
        """获取Agent的唯一标识"""
        return self._id
    
    def get_name(self) -> str:
        """获取Agent的名称"""
        return self._name

    def get_type(self) -> str:
        """获取Agent的类型"""
        return self._type

    # ********** 语言模型信息 **********

    def get_llm(self) -> ILLM:
        """获取智能体的语言模型
                
        返回:
            ILLM: 智能体的语言模型
        """
        # 获取智能体工作流当前状态
        stage = self.get_workflow().get_current_state()
        return self._llms[stage]

    def get_llms(self) -> dict[WorkflowStageT, ILLM]:
        """获取智能体的语言模型
        
        返回:
            dict[WorkflowStageT, ILLM]: 智能体的语言模型
        """
        return self._llms.copy()
    
    # ********** Human in the loop **********
    
    def get_human_client(self) -> IHumanClient | None:
        """获取Human in the loop客户端
        
        Returns:
            IHumanClient | None:
                Human in the loop客户端实例，如果未设置则返回None
        """
        return self._human_client
    
    # ********** 工作流管理 **********
    
    def get_workflow(self) -> IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]:
        """获取Agent关联的工作流
        
        Returns:
            IWorkflow:
                Agent关联的工作流
        """
        if self._workflow is None:
            raise RuntimeError("Workflow is not set for this agent.")
        return self._workflow

    def set_workflow(self, workflow: IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]) -> None:
        """设置Agent关联的工作流

        Args:
            workflow (IWorkflow):
                要设置的工作流实例
        """
        self._workflow = workflow
        
    def get_tool_service(self) -> Client[ClientTransport]:
        if self._tool_service is None:
            raise RuntimeError("Tool service is not set for this agent.")
        return self._tool_service

    async def call_tool(
        self,
        context: dict[str, Any],
        name: str, 
        task: ITask[StateT, EventT], 
        inject: dict[str, Any],
        kwargs: dict[str, Any]
    ) -> Message:
        """调用指定名称的工具。如果是工作流的工具，则会注入 Task 和 Workflow 实例，如果是工具服务的工具，则不会主动注入。

        Args:
            context (dict[str, Any]): 任务运行时的上下文信息，包括用户ID/AccessToken/TraceID等
            name (str): 工具名称
            task (ITask[StateT, EventT]): 任务实例
            inject (dict[str, Any]): 注入工具的额外依赖参数
            kwargs (dict[str, Any]): 工具调用的参数

        Returns:
            Message: 工具调用结果

        Raises:
            RuntimeError: 如果工作流未设置，或者工具标签错误
        """
        if self._workflow is None:
            raise RuntimeError("Workflow is not set for this agent.")
        
        # 1. 优先从工作流获取工具（遵循"工作流优先"原则）
        workflow_tool_info = self._workflow.get_tool(name)

        if workflow_tool_info is not None:
            # 1.1 解析工作流返回的工具和标签集合
            tool, required_tags = workflow_tool_info
            
            # 1.2 检查任务标签是否满足工具的标签要求（任务标签需包含所有工具必需标签）
            # 假设ITask接口有get_tags()方法获取任务标签集合，若实际接口名不同需调整
            task_tags = task.get_tags() if hasattr(task, "get_tags") else set[str]()
            is_tags_valid = required_tags.issubset(task_tags)

            if is_tags_valid:
                # 1.3 标签符合要求：直接调用工作流中的工具
                result = await self._workflow.call_tool(
                    name=name,
                    task=task,
                    inject=inject,
                    kwargs=kwargs
                )
                
                # 1.4 准备最终结果
                content: list[dict[str, Any]] = []
                for block in result.content:
                    content.append(block.model_dump())
                metadata = result.structuredContent if result.structuredContent else {}
                message: dict[str, Any] = {
                    "role": Role.TOOL,
                    "content": "",
                    "multimodal_content": content,
                    "is_error": result.isError,
                    "metadata": metadata,
                }
                
                # 1.5 转换最终结果为 Message 并返回
                return Message.model_validate(message)
            else:
                # 标签不满足要求
                raise RuntimeError(f"Tool `{tool.name}` requires tags `{required_tags}`, but task has tags `{task_tags}`.", format_exc())

        # 2. 工作流无该工具 或 标签不满足：从工具服务调用
        elif self._tool_service is not None:
            # 2.1 构造工具服务调用参数
            kwargs.update(context=context)  # 注入上下文信息，如用户ID/TraceID等
            
            try:
                # 2.2 调用工具服务（假设Client有async_request方法，参数为工具名+参数，若实际接口不同需调整）
                tool_call_result = await self._tool_service.call_tool(
                    name=name,
                    arguments=kwargs,
                )
                # 2.3. 转换最终结果
                result = CallToolResult(
                    content=tool_call_result.content,
                    structuredContent=tool_call_result.structured_content,
                    isError=tool_call_result.is_error,
                )
            except RuntimeError as e:
                # 遇到 FastMcp 客户端抛出的运行时错误，继续向外抛出
                raise e
            except Exception as e:
                result = CallToolResult(content=[TextContent(type="text", text=str(e))], isError=True)

            # 2.4 准备最终结果
            content = []
            for block in result.content:
                content.append(block.model_dump())
            metadata = result.structuredContent if result.structuredContent else {}
            message = {
                "role": Role.TOOL,
                "content": "",
                "multimodal_content": content,
                "is_error": result.isError,
                "metadata": metadata,
            }
            # 2.5. 转换最终结果为 Message 并返回
            return Message.model_validate(message)
        
        else:
            raise RuntimeError(f"Tool `{name}` not found in workflow and tool service is not set.", format_exc())

    # ********** 执行任务接口 **********
    
    async def run_task_stream(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[StateT, EventT],
    ) -> ITask[StateT, EventT]:
        """以流式方式运行一个任务指定给Agent。
        
        Args:
            context (dict[str, Any]):
                任务运行时的上下文信息
            queue (IQueue[Message]):
                数据队列，用于输出任务运行过程中产生的数据
            task (ITask):
                要运行的任务
        
        Returns:
            ITask:
                包含任务运行结果的任务
        """
        if self._workflow is None:
            raise RuntimeError("Workflow is not set for this agent.")
        # 深度复制一份工作流，避免并发时工作流状态干扰
        workflow = deepcopy(self._workflow)

        # 获取第一个事件
        event_chain = workflow.get_event_chain()
        event = event_chain[0]
        
        # 循环标志位
        condition: bool = True
        
        # 循环直到结束
        while condition:
                
            # 执行单次执行前钩子
            for hook in self._pre_run_once_hooks:
                if inspect.iscoroutinefunction(hook):
                    await hook(context, queue, task)
                else:
                    await asyncify(hook)(context, queue, task)
            
            while True:
                # 触发事件，进行状态转换
                workflow.handle_event(event)
                
                # 检查是否为最后一个事件
                if event == event_chain[-1]:
                    # 结束循环
                    condition = False
                    break
                
                # 执行动作
                action = workflow.get_action()
                event = await action(workflow, context, queue, task)
                
                # 检查是否重新回到第一个事件
                if event == event_chain[0]:
                    # 结束一轮循环
                    break

            # 执行单次执行后钩子
            for hook in self._post_run_once_hooks:
                if inspect.iscoroutinefunction(hook):
                    await hook(context, queue, task)
                else:
                    await asyncify(hook)(context, queue, task)

        return task

    def add_pre_run_once_hook(
        self,
        hook: Callable[[dict[str, Any], IQueue[Message], ITask[StateT, EventT]], Awaitable[None] | None],
    ) -> None:
        """添加单次执行前钩子函数
        
        Args:
            单次执行前钩子函数，接受上下文信息/输出队列/任务和额外关键字参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - task: ITask[StateT, EventT]
        """
        self._pre_run_once_hooks.append(hook)

    def add_post_run_once_hook(
        self,
        hook: Callable[[dict[str, Any], IQueue[Message], ITask[StateT, EventT]], Awaitable[None] | None],
    ) -> None:
        """添加单次执行后钩子函数
        
        Args:
            单次执行后钩子函数，接受上下文信息/输出队列/任务和额外关键字参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - task: ITask[StateT, EventT]
        """
        self._post_run_once_hooks.append(hook)

    # ********** 运行时能力 **********

    async def observe(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[StateT, EventT],
        observe_fn: Callable[[ITask[StateT, EventT], dict[str, Any]], Message],
        **kwargs: Any,
    ) -> list[Message]:
        """观察目标
        
        参数:
            context (dict[str, Any]):
                任务运行时的上下文信息，包括用户ID/AccessToken/TraceID等信息
            queue (IQueue[Message]):
                数据队列，用于输出任务运行过程中产生的数据
            task (ITask):
                要观察的任务
            observe_fn (Callable[[ITask[StateT, EventT]], Message]):
                观察函数，用于从任务中提取观察信息
            **kwargs:
                观察目标的额外关键字参数

        返回:
            list[Message]:
                从目标观察到的最新信息
        """
        # 调用 pre observe hooks
        for hook in self._pre_observe_hooks:
            if inspect.iscoroutinefunction(hook):
                await hook(context, queue, task)
            else:
                await asyncify(hook)(context, queue, task)

        # 根据 observe_format 格式化当前的 Task 为 Message
        new_observe = observe_fn(task, kwargs)
        # 更新到 Task 上下文中
        task.append_context(new_observe)
        # 获取历史数据
        observe_res = task.get_context().get_context_data()
        
        # 调用 post observe hooks
        for hook in self._post_observe_hooks:
            if inspect.iscoroutinefunction(hook):
                await hook(context, queue, task, observe_res)
            else:
                await asyncify(hook)(context, queue, task, observe_res)

        return observe_res

    def add_pre_observe_hook(
        self,
        hook: Callable[[dict[str, Any], IQueue[Message], ITask[StateT, EventT]], Awaitable[None] | None],
    ) -> None:
        """添加观察前钩子函数
        
        参数:
            hook (Callable):
                观察前钩子函数，接受上下文信息/输出队列/任务/观察格式和额外关键字参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - task: ITask[StateT, EventT]
        """
        self._pre_observe_hooks.append(hook)

    def add_post_observe_hook(
        self, 
        hook: Callable[[dict[str, Any], IQueue[Message], ITask[StateT, EventT], list[Message]], Awaitable[None] | None], 
    ) -> None:
        """添加观察后钩子函数
        
        参数:
            hook (Callable):
                观察后钩子函数，接受上下文信息/输出队列/任务/观察格式/观察结果和额外关键字参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - task: ITask[StateT, EventT]
                - observe_res: list[Message]
        """
        self._post_observe_hooks.append(hook)

    async def think(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        observe: list[Message],
        completion_config: CompletionConfig,
        **kwargs: Any, 
    ) -> Message:
        """思考任务或环境的观察结果
        
        参数:
            context (dict[str, Any]):
                任务运行时的上下文信息，包括用户ID/AccessToken/TraceID等
            queue (IQueue[Message]):
                数据队列，用于输出任务运行过程中产生的数据
            observe (list[Message]):
                从任务或环境观察到的消息
            completion_config (CompletionConfig):
                Agent的生成配置
            **kwargs:
                思考任务或环境的额外关键字参数
                
        返回:
            Message:
                语言模型思考的完成消息
        """
        # 调用 pre think hooks
        for hook in self._pre_think_hooks:
            if inspect.iscoroutinefunction(hook):
                await hook(context, queue, observe)
            else:
                await asyncify(hook)(context, queue, observe)

        llm = self.get_llm()
        think_result = await llm.completion(
            messages=observe,
            completion_config=completion_config,
            **kwargs,
        )
        
        # 调用 post think hooks
        for hook in self._post_think_hooks:
            if inspect.iscoroutinefunction(hook):
                await hook(context, queue, think_result)
            else:
                await asyncify(hook)(context, queue, think_result)

        return think_result

    def add_pre_think_hook(
        self, 
        hook: Callable[[dict[str, Any], IQueue[Message], list[Message]], Awaitable[None] | None], 
    ) -> None:
        """添加思考前钩子函数
        
        参数:
            hook (Callable):
                思考前钩子函数，接受上下文信息/输出队列/观察结果/生成配置和额外关键字参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - observe_res: list[Message]
        """
        self._pre_think_hooks.append(hook)

    def add_post_think_hook(
        self, 
        hook: Callable[
            [dict[str, Any], IQueue[Message], Message], 
            Awaitable[None] | None
        ], 
    ) -> None:
        """添加思考后钩子函数
        
        参数:
            hook (Callable):
                思考后钩子函数，接受上下文信息/输出队列/观察结果/思考结果/生成配置和额外关键字参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - think_result: Message
        """
        self._post_think_hooks.append(hook)

    async def act(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        tool_call: ToolCallRequest,
        task: ITask[StateT, EventT], 
        **kwargs: Any
    ) -> Message:
        """根据工具调用采取行动。其他参数可以通过关键字参数提供给工具调用
        
        参数:
            context (dict[str, Any]):
                任务运行时的上下文信息，包括用户ID/AccessToken/TraceID等
            queue (IQueue[Message]):
                数据队列，用于输出任务运行过程中产生的数据
            tool_call (ToolCallRequest):
                工具调用请求，包括工具调用ID和工具调用参数
            task (ITask):
                工具调用任务
            **kwargs:
                调用工具的额外关键字参数
                
        返回:
            Message:
                Agent在任务上行动后返回的工具调用结果
            
        异常:
            ValueError:
                如果工具调用名称未注册到工作流/任务/智能体
        """
        # 调用 pre act hooks
        for hook in self._pre_act_hooks:
            if inspect.iscoroutinefunction(hook):
                await hook(context, queue, task)
            else:
                await asyncify(hook)(context, queue, task)

        # 执行工具调用
        act_result = await self.call_tool(
            context=context,
            name=tool_call.name,
            task=task,
            inject=kwargs,
            kwargs=tool_call.args,
        )
        
        # 调用 post act hooks
        for hook in self._post_act_hooks:
            if inspect.iscoroutinefunction(hook):
                await hook(context, queue, task, act_result)
            else:
                await asyncify(hook)(context, queue, task, act_result)

        return act_result

    def add_pre_act_hook(
        self, 
        hook: Callable[
            [dict[str, Any], IQueue[Message], ITask[StateT, EventT]], 
            Awaitable[None] | None
        ],
    ) -> None:
        """添加行动前钩子函数
        
        参数:
            hook (Callable):
                行动前钩子函数，接受上下文信息/输出队列/任务/工具调用消息和额外关键字参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - task: ITask[StateT, EventT]
        """
        self._pre_act_hooks.append(hook)
    
    def add_post_act_hook(
        self,
        hook: Callable[
            [dict[str, Any], IQueue[Message], ITask[StateT, EventT], Message],
            Awaitable[None] | None
        ],
    ) -> None:
        """添加行动后钩子函数
        
        参数:
            hook (Callable):
                行动后钩子函数，接受上下文信息/输出队列/任务/工具调用消息/行动结果和额外关键字参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - task: ITask[StateT, EventT]
                - act_result: Message
        """
        self._post_act_hooks.append(hook)
