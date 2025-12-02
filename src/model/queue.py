import asyncio
from abc import ABC, abstractmethod
from typing import Generic, TypeVar


T = TypeVar('T')


class IQueue(ABC, Generic[T]):
    """队列接口协议，用于限制Agent并发时对消息输出队列的控制"""

    @abstractmethod
    async def put(self, item: T) -> None:
        """将项目添加到队列中

        Args:
            item: 要添加到队列的项目
        """
        
    @abstractmethod
    async def put_nowait(self, item: T) -> None:
        """将项目添加到队列中（非阻塞）

        Args:
            item: 要添加到队列的项目
        """

    @abstractmethod
    async def get(self) -> T:
        """从队列中移除并返回项目

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
    async def is_empty(self) -> bool:
        """检查队列是否为空

        Returns:
            如果队列为空则返回True，否则返回False
        """

    @abstractmethod
    async def is_full(self) -> bool:
        """检查队列是否已满

        Returns:
            如果队列已满则返回True，否则返回False
        """


class AsyncQueue(IQueue[T]):
    """基于 asyncio.Queue 的异步队列实现"""

    def __init__(self, maxsize: int = 0) -> None:
        self._queue = asyncio.Queue[T](maxsize)

    async def put(self, item: T) -> None:
        await self._queue.put(item)

    async def put_nowait(self, item: T) -> None:
        self._queue.put_nowait(item)

    async def get(self) -> T:
        return await self._queue.get()

    async def get_nowait(self) -> T:
        return self._queue.get_nowait()

    async def is_empty(self) -> bool:
        return self._queue.empty()

    async def is_full(self) -> bool:
        return self._queue.full()