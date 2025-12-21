import asyncio
from abc import ABC, abstractmethod
from typing import Generic, TypeVar


T = TypeVar('T')


class IAsyncQueue(ABC, Generic[T]):
    """异步队列接口协议，用于限制Agent并发时对消息输出队列的控制"""

    @abstractmethod
    async def put(self, item: T, block: bool = True, timeout: float | None = None) -> None:
        """将项目添加到队列中

        Args:
            item: 要添加到队列的项目
            block: 是否阻塞等待，默认为True
            timeout: 超时时间，单位为秒，默认为None（无限等待）
        """

    @abstractmethod
    async def put_nowait(self, item: T) -> None:
        """将项目添加到队列中（非阻塞）

        Args:
            item: 要添加到队列的项目
        """

    @abstractmethod
    async def get(self, block: bool = True, timeout: float | None = None) -> T:
        """从队列中移除并返回项目
        
        Args:
            block: 是否阻塞等待，默认为True
            timeout: 超时时间，单位为秒，默认为None（无限等待）

        Returns:
            从队列中移除的项目
        """

    @abstractmethod
    async def get_nowait(self) -> T:
        """从队列中移除并返回项目（非阻塞）

        Returns:
            从队列中移除的项目
        """

    @abstractmethod
    def is_empty(self) -> bool:
        """检查队列是否为空

        Returns:
            如果队列为空则返回True，否则返回False
        """

    @abstractmethod
    def is_full(self) -> bool:
        """检查队列是否已满

        Returns:
            如果队列已满则返回True，否则返回False
        """
        
    @abstractmethod
    def qsize(self) -> int:
        """获取队列当前大小

        Returns:
            队列当前包含的项目数量
        """
        
    @abstractmethod
    def is_closed(self) -> bool:
        """检查队列是否已关闭

        Returns:
            如果队列已关闭则返回True，否则返回False
        """
        
    @abstractmethod
    async def close(self) -> None:
        """关闭队列，释放资源"""


class AsyncQueue(IAsyncQueue[T]):
    """基于 asyncio.Queue 的异步队列实现"""
    _queue: asyncio.Queue[T]
    _is_closed: bool = False

    def __init__(self, maxsize: int = 0) -> None:
        self._queue = asyncio.Queue[T](maxsize)

    async def put(self, item: T, block: bool = True, timeout: float | None = None) -> None:
        """将项目添加到队列中

        Args:
            item: 要添加到队列的项目
            block: 是否阻塞等待，默认为True
            timeout: 超时时间，单位为秒，默认为None（无限等待）
        """
        if not block:
            self._queue.put_nowait(item)
            return
        await asyncio.wait_for(self._queue.put(item), timeout)

    async def put_nowait(self, item: T) -> None:
        """将项目添加到队列中（非阻塞）

        Args:
            item: 要添加到队列的项目
        """
        self._queue.put_nowait(item)

    async def get(self, block: bool = True, timeout: float | None = None) -> T:
        """从队列中移除并返回项目
        
        Args:
            block: 是否阻塞等待，默认为True
            timeout: 超时时间，单位为秒，默认为None（无限等待）

        Returns:
            从队列中移除的项目
        """
        if not block:
            return self._queue.get_nowait()
        # 使用 asyncio.wait_for 来实现超时功能
        return await asyncio.wait_for(self._queue.get(), timeout)

    async def get_nowait(self) -> T:
        """从队列中移除并返回项目（非阻塞）

        Returns:
            从队列中移除的项目
        """
        return self._queue.get_nowait()

    def is_empty(self) -> bool:
        """检查队列是否为空

        Returns:
            如果队列为空则返回True，否则返回False
        """
        return self._queue.empty()

    def is_full(self) -> bool:
        """检查队列是否已满

        Returns:
            如果队列已满则返回True，否则返回False
        """
        return self._queue.full()
    
    def qsize(self) -> int:
        """获取队列当前大小

        Returns:
            队列当前包含的项目数量
        """
        return self._queue.qsize()
    
    def is_closed(self) -> bool:
        """检查队列是否已关闭

        Returns:
            如果队列已关闭则返回True，否则返回False
        """
        return self._is_closed
    
    async def close(self) -> None:
        """关闭队列，释放资源"""
        self._is_closed = True
        del self._queue
