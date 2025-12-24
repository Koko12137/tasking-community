from abc import abstractmethod, ABC
from typing import Generic, Any
from collections.abc import Callable, Awaitable

from mcp.types import Tool as McpTool
from fastmcp import Client
from fastmcp.client.transports import ClientTransportT

from ..state_machine.const import StateT, EventT
from ..state_machine.workflow import IWorkflow, WorkflowStageT, WorkflowEventT
from ..state_machine.task import ITask
from ...model import CompletionConfig, Message, ToolCallRequest, IAsyncQueue
from ...llm import ILLM


class IAgent(ABC, Generic[WorkflowStageT, WorkflowEventT, StateT, EventT, ClientTransportT]):
    """Agent接口定义"""

    # ********** 基础信息 **********

    @abstractmethod
    def get_id(self) -> str:
        """获取Agent的唯一标识"""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """获取Agent的名称"""
        pass

    @abstractmethod
    def get_type(self) -> str:
        """获取Agent的类型"""
        pass

    # ********** 语言模型信息 **********

    @abstractmethod
    def get_llm(self) -> ILLM:
        """获取智能体工作流当前状态的语言模型

        返回:
            ILLM: 智能体的语言模型
        """
        pass

    @abstractmethod
    def get_llms(self) -> dict[WorkflowStageT, ILLM]:
        """获取智能体的语言模型

        返回:
            dict[WorkflowStageT, ILLM]: 智能体的语言模型
        """
        pass

    # ********** 工作流与工具管理 **********

    @abstractmethod
    def get_workflow(self) -> IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]:
        """获取Agent关联的工作流

        Returns:
            IWorkflow:
                Agent关联的工作流
        """
        pass

    @abstractmethod
    def set_workflow(self, workflow: IWorkflow[WorkflowStageT, WorkflowEventT, StateT, EventT]) -> None:
        """设置Agent关联的工作流

        Args:
            workflow (IWorkflow):
                要设置的工作流实例
        """
        pass

    @abstractmethod
    def get_tool_service(self) -> Client[ClientTransportT] | None:
        """获取工具服务,用于调用注册到工具服务的工具

        Returns:
            Client[ClientTransportT] | None:
                工具服务客户端实例，如果未设置则返回 None
        """
        pass
    
    @abstractmethod
    async def get_tools_with_tags(self, tags: set[str]) -> dict[str, McpTool]:
        """获取工具服务中注册的所有工具及其标签
        
        Args:
            tags (set[str]):
                需要获取的工具标签集合，返回包含这些标签的工具。

        Returns:
            dict[str, Tool]:
                工具名称到工具实例的映射字典
        """
        pass

    @abstractmethod
    async def call_tool(
        self,
        context: dict[str, Any],
        name: str,
        task: ITask[StateT, EventT],
        inject: dict[str, Any],
        kwargs: dict[str, Any],
    ) -> Message:
        """调用指定名称的工具

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
        pass

    # ********** 执行任务接口 **********

    @abstractmethod
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
        pass

    @abstractmethod
    def add_pre_run_once_hook(
        self,
        hook: Callable[[dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]], Awaitable[None] | None],
    ) -> None:
        """添加单次执行前钩子函数

        Args:
            单次执行前钩子函数，接受上下文信息/输出队列/任务参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - task: ITask[StateT, EventT]
        """
        pass

    @abstractmethod
    def add_post_run_once_hook(
        self,
        hook: Callable[[dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]], Awaitable[None] | None],
    ) -> None:
        """添加单次执行后钩子函数

        Args:
            单次执行后钩子函数，接受上下文信息/输出队列/任务参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - task: ITask[StateT, EventT]
        """
        pass

    # ********** 运行时能力 **********

    @abstractmethod
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
            observe_fn (Callable[[ITask[StateT, EventT], dict[str, Any]], Message]):
                观察函数，用于从任务中提取观察信息
            **kwargs:
                观察目标的额外关键字参数

        返回:
            list[Message]:
                从目标观察到的最新信息
        """
        pass

    @abstractmethod
    def add_pre_observe_hook(
        self,
        hook: Callable[[dict[str, Any], IAsyncQueue[Message], ITask[StateT, EventT]], Awaitable[None] | None],
    ) -> None:
        """添加观察前钩子函数

        参数:
            hook (Callable):
                观察前钩子函数，接受上下文信息/输出队列/任务参数，函数签名如下：
                - context: dict[str, Any]
                - queue: IQueue[Message]
                - task: ITask[StateT, EventT]
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def think(
        self,
        context: dict[str, Any],
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
            queue (IQueue[Message]):
                数据队列，用于输出任务运行过程中产生的数据
            task (ITask[StateT, EventT]):
                要思考的任务
            valid_tools (dict[str, McpTool]):
                可用的工具名称到工具实例的映射字典
            completion_config (CompletionConfig):
                Agent的生成配置
            **kwargs:
                思考任务或环境的额外关键字参数

        返回:
            Message:
                语言模型思考的完成消息
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def act(
        self,
        context: dict[str, Any],
        queue: IAsyncQueue[Message],
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass
