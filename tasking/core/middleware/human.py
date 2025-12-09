from abc import abstractmethod, ABC
from typing import Any, cast

from ...model import Message, Role, IQueue, AsyncQueue, TextBlock, MultimodalContent
from ...core.state_machine.task import ITask, TaskState, TaskEvent
from ...utils.io import read_markdown
from ...utils.string.extract import extract_by_label


class HumanInterfere(Exception):
    """HumanInterfere 异常，表示人类用户介入了流程"""
    _messages: list[MultimodalContent]
    _message: str

    def __init__(self, messages: list[MultimodalContent]) -> None:
        self._messages = messages
        self._message = "".join([
            block.text for block in messages if isinstance(block, TextBlock)
        ])
        super().__init__(self._message)

    def __str__(self) -> str:
        return f"HumanInterfere: {self._message}"
    
    def get_messages(self) -> list[MultimodalContent]:
        return self._messages


class IHumanClient(ABC):
    """Human in the loop接口定义"""
    
    @abstractmethod
    def is_valid(self, context: dict[str, Any]) -> bool:
        """检查当前上下文是否适用于Human in the loop交互

        参数:
            context (dict[str, Any]): 当前请求的上下文信息, 包含用户信息、请求元数据等

        返回:
            bool: 如果适用于Human in the loop交互则返回True，否则返回False
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def handle_human_response(self, context: dict[str, Any], message: Message) -> None:
        """检索人类的回复消息

        参数:
            context (dict[str, Any]): 当前请求的上下文信息, 包含用户信息、请求元数据等
            message (Message): 人类回复的消息内容
        """
        pass


class IHumanInterfereHooks(ABC):
    """人类介入钩子接口定义"""

    @abstractmethod
    async def on_pre_human_interfere(self, context: dict[str, Any], queue: IQueue[Message], task: ITask[TaskState, TaskEvent]) -> None:
        """当 HumanClient 注入到 Agent 时调用的钩子方法，用于支持 Agent 请求人类介入

        参数:
            context (dict[str, Any]): 当前请求的上下文信息, 包含用户信息、请求元数据等
            queue (IQueue[Message]): 向人类发送消息的队列
            task (ITask[TaskState, TaskEvent]): 当前任务实例
        """
        pass
    
    @abstractmethod
    async def on_post_human_interfere(self, context: dict[str, Any], queue: IQueue[Message], task: ITask[TaskState, TaskEvent]) -> None:
        """当 HumanClient 注入到 Agent 并且 Agent 认为需要人类介入处理后调用的钩子方法

        参数:
            context (dict[str, Any]): 当前请求的上下文信息, 包含用户信息、请求元数据等
            queue (IQueue[Message]): 向人类发送消息的队列
            task (ITask[TaskState, TaskEvent]): 当前任务实例
            
        异常:
            HumanInterfere: 如果人类介入了正在执行的任务，则抛出该异常
        """
        pass


class BaseHumanClient(IHumanClient):
    """基础Human in the loop客户端实现：提供IHumanClient接口的基础实现，供具体HumanClient继承与扩展"""
    _response_queues: dict[str, AsyncQueue[Message]]

    def __init__(self) -> None:
        # 初始化响应队列字典
        self._response_queues = {}
        
    def is_valid(self, context: dict[str, Any]) -> bool:
        """检查当前上下文是否适用于Human in the loop交互

        参数:
            context (dict[str, Any]): 当前请求的上下文信息, 包含用户信息、请求元数据等

        返回:
            bool: 如果适用于Human in the loop交互则返回True，否则返回False
        """
        # 默认实现总是返回True，表示适用于Human in the loop交互
        return True

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
        # 根据 UserID 和 TraceID 生成唯一请求 ID
        request_id = f"{context['user_id']}:{context['trace_id']}"
        # 创建一个新的响应队列用于接收人类回复
        self._response_queues[request_id] = AsyncQueue[Message]()
        # 等待人类回复
        resp = await self._response_queues[request_id].get()
        # 删除响应队列
        del self._response_queues[request_id]
        return resp

    async def handle_human_response(self, context: dict[str, Any], message: Message) -> None:
        """处理人类的回复消息

        参数:
            context (dict[str, Any]): 当前请求的上下文信息, 包含用户信息、请求元数据等
            message (Message): 人类回复的消息内容
        """
        # 根据 UserID 和 TraceID 生成唯一请求 ID
        request_id = f"{context['user_id']}:{context['trace_id']}"
        # 将人类回复放入对应的响应队列
        await self._response_queues[request_id].put(message)


class BaseHumanInterfereHooks(IHumanInterfereHooks):
    """基础人类介入钩子实现：提供IHumanInterfereHooks接口的基础实现，供具体钩子继承与扩展"""
    _human_client: IHumanClient
    _approve_resp: set[str]     # 经批准的不会抛出 HumanInterfere 异常的人类回复集合
    
    def __init__(self, human_client: IHumanClient, approve_resp: set[str] | None = None) -> None:
        """初始化 BaseHumanInterfereHooks 实例
        
        Args:
            human_client (IHumanClient): 用于处理人类交互的 HumanClient 实例
            approve_resp (set[str] | None): 经批准的不会抛出 HumanInterfere 异常的人类回复集合
        """
        self._human_client = human_client
        self._approve_resp = approve_resp or set()

    async def on_pre_human_interfere(self, context: dict[str, Any], queue: IQueue[Message], task: ITask[TaskState, TaskEvent]) -> None:
        """当 HumanClient 注入到 Agent 时调用的钩子方法，用于支持 Agent 请求人类介入

        参数:
            context (dict[str, Any]): 当前请求的上下文信息, 包含用户信息、请求元数据等
            queue (IQueue[Message]): 向人类发送消息的队列
            task (ITask[TaskState, TaskEvent]): 当前任务实例
        """
        # 检查当前上下文的 human_client 是否有效
        if not self._human_client.is_valid(context):
            return
        
        # 读取人类介入请求模板
        prompt = read_markdown("tool/human_interfere.md")
        # 注入人类交互方法到任务上下文
        message = Message(
            role=Role.USER,
            content=[cast(MultimodalContent, TextBlock(text=prompt))],
        )
        task.append_context(message)

    async def on_post_human_interfere(self, context: dict[str, Any], queue: IQueue[Message], task: ITask[TaskState, TaskEvent]) -> None:
        """当 HumanClient 注入到 Agent 并且人类介入处理后调用的钩子方法

        参数:
            context (dict[str, Any]): 当前请求的上下文信息, 包含用户信息、请求元数据等
            queue (IQueue[Message]): 向人类发送消息的队列
            task (ITask[TaskState, TaskEvent]): 当前任务实例
            
        异常:
            HumanInterfere: 如果人类介入了正在执行的任务，则抛出该异常
        """
        # 检查当前上下文的 human_client 是否有效
        if not self._human_client.is_valid(context):
            return

        # 检测任务上下文中是否有需要人类介入的标志
        last_message = task.get_context().get_context_data()[-1]
        if not last_message.role == Role.ASSISTANT:
            raise ValueError("The last message in context must be from ASSISTANT role")
        human_interfere_content = extract_by_label(
            "".join([
                block.text for block in last_message.content if isinstance(block, TextBlock)
            ]),
            "human_interfere",
        )
        if human_interfere_content.strip().lower() == "":
            # 无需人类介入，直接返回
            return
        # 构造人类介入消息
        message = Message(
            role=Role.ASSISTANT,
            content=[cast(MultimodalContent, TextBlock(text=human_interfere_content))],
        )
        # 发送消息给人类进行交互
        human_response = await self._human_client.ask_human(context, queue, message)
        # 处理人类的回复
        if human_response.content:
            # 检查人类回复是否为空，如果为空则默认人类不干预任务执行
            if len(human_response.content) == 1 and isinstance(human_response.content[0], TextBlock):
                text_block = human_response.content[0]
                if text_block.text.strip().lower() == "":
                    return
                
                elif text_block.text.strip() in self._approve_resp:
                    # 人类回复在批准列表中，继续任务执行
                    return

            # 转为 HumanInterfere 异常，通知上层任务处理人类介入
            raise HumanInterfere(human_response.content)
