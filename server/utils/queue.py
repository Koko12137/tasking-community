import asyncio

from src.model import IQueue, T


class AQueue(IQueue[T]):
    """基于 asyncio.Queue 的消息队列封装"""
    _queue: asyncio.Queue[T]
    
    def __init__(self, maxsize: int = 0) -> None:
        """
        初始化基于 asyncio.Queue 的消息队列封装

        Args:
            maxsize: 队列的最大大小，默认为0表示无限制
        """
        self._queue = asyncio.Queue(maxsize)
        
    async def is_empty(self) -> bool:
        """检查队列是否为空
        
        Returns:
            如果队列为空则返回True，否则返回False
        """
        return self._queue.empty()

    async def is_full(self) -> bool:
        """检查队列是否已满

        Returns:
            如果队列已满则返回True，否则返回False
        """
        return self._queue.full()
        
    async def put(self, item: T) -> None:
        """将元素放入队列中
        
        Args:
            item: 要放入队列的元素
        """
        await self._queue.put(item)
            
    async def put_nowait(self, item: T) -> None:
        """不阻塞地将元素放入队列中
        
        Args:
            item: 要放入队列的元素
            
        Raises:
            asyncio.QueueFull: 如果队列已满则抛出该异常
        """
        self._queue.put_nowait(item)
        
    async def get(self) -> T:
        """从队列中获取一个元素
        
        Returns:
            队列中的元素
        """
        return await self._queue.get()
        
    async def get_nowait(self) -> T:
        """不阻塞地从队列中获取一个元素
        
        Returns:
            队列中的元素
            
        Raises:
            asyncio.QueueEmpty: 如果队列为空则抛出该异常
        """
        return self._queue.get_nowait()