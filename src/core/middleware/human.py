from abc import abstractmethod, ABC
from typing import Any

from ...model import  Message, IQueue, AsyncQueue


class HumanInterfere(Exception):
    """HumanInterfere 异常，表示人类用户介入了流程"""
    _message: str

    def __init__(self, message: str = "Human user rejected the request") -> None:
        self._message = message
        super().__init__(message)

    def __str__(self) -> str:
        return f"HumanInterfere: {self._message}"


class IHumanClient(ABC):
    """Human in the loop接口定义"""

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


class BaseHumanClient(IHumanClient):
    """基础Human in the loop客户端实现：提供IHumanClient接口的基础实现，供具体HumanClient继承与扩展"""
    _response_queues: dict[str, AsyncQueue[Message]]
    
    def __init__(self) -> None:
        # 初始化响应队列字典
        self._response_queues = {}

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
