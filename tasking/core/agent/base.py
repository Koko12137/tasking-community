import asyncio
import inspect
from collections.abc import Callable, Awaitable
from typing import Any
from traceback import format_exc

from mcp.types import Tool as McpTool
from fastmcp import Client
from fastmcp.client.transports import ClientTransportT
from mcp.types import CallToolResult, TextContent
from asyncer import asyncify

from .interface import IAgent
from ..state_machine.const import EventT, StateT
from ..state_machine.task import ITask
from ..state_machine.workflow import WorkflowEventT, WorkflowStageT, IWorkflow
from ...model import CompletionConfig, Message, Role, ToolCallRequest
from ...model.queue import IAsyncQueue, AsyncQueue
from ...model.message import TextBlock, ImageBlock, VideoBlock


class BaseAgent(IAgent[WorkflowStageT, WorkflowEventT, StateT, EventT, ClientTransportT]):
    """基础Agent实现：提供IAgent接口的基础实现，供具体Agent继承与扩展"""
    _id: str
    _name: str
    _type: str
    # Workflow
    _workflow_factory: Callable[[], IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]] | None
    # Tool Service
    _tool_service: Client[ClientTransportT] | None

    # Run Hooks
    _pre_run_once_hooks: list[Callable[
        [dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]],
        Awaitable[None] | None
    ]]
    """单次执行前钩子函数列表，会按顺序执行。钩子函数的签名为:

    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        task (ITask[StateT, EventT]): 要运行的任务
    """
    _post_run_once_hooks: list[Callable[
        [dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]],
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
        [dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]],
        Awaitable[None] | None
    ]]
    """观察前钩子函数列表，会按顺序执行。钩子函数的签名为:

    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        task (ITask[StateT, EventT]): 要运行的任务
    """
    _post_observe_hooks: list[Callable[
        [dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]],
        Awaitable[None] | None
    ]]
    """观察后钩子函数列表，会按顺序执行。钩子函数的签名为:

    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        task (ITask[StateT, EventT]): 要运行的任务
    """

    # Think Hooks
    _pre_think_hooks: list[Callable[
        [dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]],
        Awaitable[None] | None
    ]]
    """思考前钩子函数列表，会按顺序执行。钩子函数的签名为:

    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        task (ITask[StateT, EventT]): 要运行的任务
    """
    _post_think_hooks: list[Callable[
        [dict[str, Any], IAsyncQueue[Message], IAsyncQueue[Message]  | None, ITask[StateT, EventT]],
        Awaitable[None] | None
    ]]
    """思考后钩子函数列表，会按顺序执行。钩子函数的签名为:

    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        task (ITask[StateT, EventT]): 要运行的任务
    """

    # Act Hooks
    _pre_act_hooks: list[Callable[
        [dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT], ToolCallRequest],
        Awaitable[None] | None
    ]]
    """行动前钩子函数列表，会按顺序执行。钩子函数的签名为:

    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        task (ITask[StateT, EventT]): 要运行的任务
        tool_call (ToolCallRequest): 工具调用请求
    """
    _post_act_hooks: list[Callable[
        [dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]],
        Awaitable[None] | None
    ]]
    """行动后钩子函数列表，会按顺序执行。钩子函数的签名为:

    Args:
        context (dict[str, Any]): 任务运行时的上下文信息
        queue (IQueue[Message]): 数据队列，用于输出任务运行过程中产生的数据
        task (ITask[StateT, EventT]): 要运行的任务
    """

    def __init__(
        self,
        name: str,
        agent_type: str,
        tool_service: Client[ClientTransportT] | None = None,
    ) -> None:
        """初始化基础Agent实例，钩子函数列表为空，等待后续注册

        Args:
            name (str): Agent的名称
            agent_type (str): Agent的类型
            tool_service (Client[ClientTransportT] | None): 工具服务客户端实例，默认为None
        """
        self._id = f"agent_{id(self)}"
        self._name = name
        self._type = agent_type
        self._workflow_factory = None
        self._tool_service = tool_service
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

    # ********** 工作流管理 **********

    def get_workflow(self) -> IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]:
        """获取Agent关联的工作流

        Returns:
            IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]:
                Agent关联的工作流实例

        Raises:
            RuntimeError: 如果工作流工厂函数未设置
        """
        if self._workflow_factory is None:
            raise RuntimeError("Workflow factory is not set for this agent.")
        return self._workflow_factory()

    def set_workflow(
        self,
        workflow_factory: Callable[[], IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]],
    ) -> None:
        """设置Agent关联的工作流工厂函数

        Args:
            workflow_factory:
                工作流工厂函数，用于创建工作流实例

        Raises:
            RuntimeError: 如果工作流工厂函数已设置
        """
        if self._workflow_factory is not None:
            raise RuntimeError("Workflow factory is already set for this agent.")
        self._workflow_factory = workflow_factory

    def get_tool_service(self) -> Client[ClientTransportT] | None:
        """获取Agent关联的工具服务

        Returns:
            Client[ClientTransportT] | None:
                Agent关联的工具服务，如果未设置则返回None
        """
        return self._tool_service
    
    async def get_tools_with_tags(self, tags: set[str]) -> dict[str, McpTool]:
        """从工具服务器获取具有指定标签集合的工具列表
        
        Args:
            tags (set[str]): 工具标签集合
            
        Returns:
            dict[str, Tool]: 符合标签要求的工具名称到工具实例的映射字典
        """
        all_tools_with_tags: dict[str, McpTool] = {}
        if self._tool_service is None:
            return all_tools_with_tags

        async with self._tool_service:
            all_tools = await self._tool_service.list_tools()
            
            # 过滤符合标签要求的工具
            for tool in all_tools:
                if hasattr(tool, "meta") and tool.meta:
                    fastmcp_meta = tool.meta.get("_fastmcp", {})
                    tool_tags = set(fastmcp_meta.get("tags", set[str]()))
                    if tool_tags.issubset(tags):
                        all_tools_with_tags[tool.name] = tool
                else:
                    # 没有 meta 信息，默认该工具可以被任意标签调用
                    all_tools_with_tags[tool.name] = tool
        return all_tools_with_tags

    async def call_tool(
        self,
        context: dict[str, Any],
        tool_call: ToolCallRequest,
        workflow: IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT],
        task: ITask[StateT, EventT],
        **inject: Any, # 注入工具的额外依赖参数
    ) -> Message:
        """调用指定名称的工具。如果是工作流的工具，则会注入 Task 和 Workflow 实例，如果是工具服务的工具，则不会主动注入。

        Args:
            context (dict[str, Any]): 任务运行时的上下文信息，包括用户ID/AccessToken/TraceID等
            workflow (IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]):
                要调用工具的工作流实例
            task (ITask[StateT, EventT]): 任务实例
            tool_call (ToolCallRequest): 工具调用请求
            **inject: Any: 注入工具的额外依赖参数

        Returns:
            Message: 工具调用结果

        Raises:
            RuntimeError: 如果工具标签错误
        """
        name = tool_call.name
        arguments = tool_call.args
        
        # 1. 优先从工作流获取工具（遵循"工作流优先"原则）
        workflow_tool_info = workflow.get_tool(name)

        if workflow_tool_info is not None:
            # 1.1 解析工作流返回的工具和标签集合
            _, required_tags = workflow_tool_info

            # 1.2 检查任务标签是否满足工具的标签要求（任务标签需包含所有工具必需标签）
            # 假设ITask接口有get_tags()方法获取任务标签集合，若实际接口名不同需调整
            task_tags = task.get_tags() if hasattr(task, "get_tags") else set[str]()
            is_tags_valid = required_tags.issubset(task_tags)

            if is_tags_valid:
                # 1.3 标签符合要求：直接调用工作流中的工具
                result = await workflow.call_tool(
                    name=name,
                    task=task,
                    inject=inject,
                    arguments=arguments
                )

                # 1.4 准备最终结果
                # Convert CallToolResult content to Message content blocks
                content_blocks: list[TextBlock | ImageBlock | VideoBlock] = []
                for block in result.content:
                    if block.type == "text":
                        content_blocks.append(TextBlock(text=block.text))
                    # TODO: Handle image and video blocks when CallToolResult supports them
                metadata = result.structuredContent if result.structuredContent else {}

                # 1.5 转换最终结果为 Message 并返回
                return Message(
                    role=Role.TOOL,
                    tool_call_id=tool_call.id,
                    content=content_blocks,
                    is_error=result.isError,
                    metadata=metadata,
                )
            else:
                # 标签不满足要求
                raise RuntimeError(
                    f"Tool `{name}` requires tags `{required_tags}`, but task has tags `{task_tags}`.",
                    format_exc(),
                )

        # 2. 工作流无该工具 或 标签不满足：从工具服务调用
        elif self._tool_service is not None:
            # 2.1 构造工具服务调用参数
            arguments.update(context=context)  # 注入上下文信息，如用户ID/TraceID等

            try:
                async with self._tool_service as client:
                    # 2.2 调用工具服务（假设Client有async_request方法，参数为工具名+参数，若实际接口不同需调整）
                    tool_call_result = await client.call_tool(
                        name=name,
                        arguments=arguments,
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
                result = CallToolResult(
                    content=[TextContent(type="text", text=str(e))],
                    isError=True,
                )

            # 2.4 准备最终结果
            # Convert CallToolResult content to Message content blocks
            content_blocks = []
            for block in result.content:
                if block.type == "text":
                    content_blocks.append(TextBlock(text=block.text))
                # TODO: Handle image and video blocks when CallToolResult supports them
            metadata = result.structuredContent if result.structuredContent else {}

            # 2.5. 转换最终结果为 Message 并返回
            return Message(
                role=Role.TOOL,
                tool_call_id=tool_call.id,
                content=content_blocks,
                is_error=result.isError,
                metadata=metadata,
            )

        else:
            raise RuntimeError(f"Tool `{name}` not found in workflow and tool service is not set.", format_exc())

    # ********** 执行任务接口 **********

    async def run_task_stream(
        self,
        context: dict[str, Any],
        queue: IAsyncQueue[Message],
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
        # 获取新的工作流实例
        workflow = self.get_workflow()

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
                await workflow.handle_event(event)

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
        hook: Callable[[dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]], Awaitable[None] | None],
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
        hook: Callable[[dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]], Awaitable[None] | None],
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
        queue: IAsyncQueue[Message],
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
                await hook(context, queue, task)
            else:
                await asyncify(hook)(context, queue, task)

        return observe_res

    def add_pre_observe_hook(
        self,
        hook: Callable[[dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]], Awaitable[None] | None],
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
        hook: Callable[[dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]], Awaitable[None] | None],
    ) -> None:
        """添加观察后钩子函数

        参数:
            hook (Callable):
                观察后钩子函数，接受上下文信息/输出队列/任务/观察格式/观察结果和额外关键字参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - task: ITask[StateT, EventT]
        """
        self._post_observe_hooks.append(hook)

    async def think(
        self,
        context: dict[str, Any],
        workflow: IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT],
        queue: IAsyncQueue[Message],
        task: ITask[StateT, EventT],
        valid_tools: dict[str, McpTool],
        completion_config: CompletionConfig,
        **kwargs: Any,
    ) -> Message:
        """思考任务或环境的观察结果

        参数:
            context (dict[str, Any]):
                任务运行时的上下文信息，包括用户ID/AccessToken/TraceID等
            workflow (IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]):
                要思考的工作流实例
            queue (IQueue[Message]):
                数据队列，用于输出任务运行过程中产生的数据
            task (ITask[StateT, EventT]):
                要思考的任务
            valid_tools (dict[str, McpTool):
                可用的工具名称到工具实例的映射字典
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
                await hook(context, queue, task)
            else:
                await asyncify(hook)(context, queue, task)
                
        llm = workflow.get_llm()
        if not completion_config.stream:
            # 非流式思考，输出按同步方式处理
            think_result = await llm.completion(
                messages=task.get_context().get_context_data(),
                tools=list(valid_tools.values()),
                stream_queue=None,
                completion_config=completion_config,
                **kwargs,
            )
            # 更新到任务上下文中
            task.append_context(think_result)

            # 调用 post think hooks
            for hook in self._post_think_hooks:
                if inspect.iscoroutinefunction(hook):
                    await hook(context, queue, None, task)
                else:
                    await asyncify(hook)(context, queue, None, task)
                    
        else:
            # 创建流式输出队列
            stream_queue: IAsyncQueue[Message] = AsyncQueue[Message]()
            # 处理流式输出
            async def process_stream() -> None:
                for hook in self._post_think_hooks:
                    if inspect.iscoroutinefunction(hook):
                        await hook(context, queue, stream_queue, task)
                    else:
                        await asyncify(hook)(context, queue, stream_queue, task)
            stream_task = asyncio.create_task(process_stream())

            # 创建思考任务
            think_task = asyncio.create_task(
                llm.completion(
                    messages=task.get_context().get_context_data(),
                    tools=list(valid_tools.values()),
                    stream_queue=stream_queue,
                    completion_config=completion_config,
                    **kwargs,
                )
            )

            # 等待思考任务完成（LLM流式输出完成）
            await think_task

            # 等待队列中所有数据都被消费完再关闭
            # 使用短暂的超时轮询来等待队列为空，避免无限阻塞
            while not stream_queue.is_empty():
                await asyncio.sleep(0.01)  # 短暂休眠，让stream_task有机会消费数据
            # 现在队列已空，可以安全关闭
            await stream_queue.close()
            # 等待流式处理任务完成
            await stream_task

            # 获取思考结果
            think_result = think_task.result()
            # 更新到任务上下文中
            task.append_context(think_result)

        return think_result

    def add_pre_think_hook(
        self,
        hook: Callable[
            [dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]], 
            Awaitable[None] | None
        ],
    ) -> None:
        """添加思考前钩子函数

        参数:
            hook (Callable):
                思考前钩子函数，接受上下文信息/输出队列/观察结果/生成配置和额外关键字参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - task: ITask[StateT, EventT]
        """
        self._pre_think_hooks.append(hook)

    def add_post_think_hook(
        self,
        hook: Callable[
            [dict[str, Any], IAsyncQueue[Message], IAsyncQueue[Message] | None, ITask[StateT, EventT]],
            Awaitable[None] | None
        ],
    ) -> None:
        """添加思考后钩子函数

        参数:
            hook (Callable):
                思考后钩子函数，接受上下文信息/输出队列/观察结果/思考结果/生成配置和额外关键字参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - stream_queue: IQueue[Message] | None
                - task: ITask[StateT, EventT]
        """
        self._post_think_hooks.append(hook)

    async def act(
        self,
        context: dict[str, Any],
        workflow: IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT],
        queue: IAsyncQueue[Message],
        tool_call: ToolCallRequest,
        task: ITask[StateT, EventT],
        **kwargs: Any
    ) -> Message:
        """根据工具调用采取行动。其他参数可以通过关键字参数提供给工具调用

        参数:
            context (dict[str, Any]):
                任务运行时的上下文信息，包括用户ID/AccessToken/TraceID等
            workflow (IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]):
                要采取行动的工作流实例
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
                await hook(context, queue, task, tool_call)
            else:
                await asyncify(hook)(context, queue, task, tool_call)

        # 执行工具调用
        act_result = await self.call_tool(
            context=context,
            workflow=workflow,
            tool_call=tool_call,
            task=task,
            **kwargs, # 注入工具的额外依赖参数
        )
        # 更新到任务上下文中
        task.append_context(act_result)

        # 调用 post act hooks
        for hook in self._post_act_hooks:
            if inspect.iscoroutinefunction(hook):
                await hook(context, queue, task)
            else:
                await asyncify(hook)(context, queue, task)

        return act_result

    def add_pre_act_hook(
        self,
        hook: Callable[
            [dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT], ToolCallRequest],
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
                - tool_call: ToolCallRequest
        """
        self._pre_act_hooks.append(hook)

    def add_post_act_hook(
        self,
        hook: Callable[
            [dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]],
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
        """
        self._post_act_hooks.append(hook)
