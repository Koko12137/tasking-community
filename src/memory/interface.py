from abc import ABC, abstractmethod
from typing import Generic, Any

from .const import MemoryT
from ..llm import IEmbeddingLLM


class IMemoryBase(ABC, Generic[MemoryT]):
    """所有记忆存储的通用父接口，定义基础CRUD行为"""
    
    @abstractmethod
    async def add_memory(self, memory: MemoryT) -> None:
        """添加记忆（所有存储通用）"""
        pass

    @abstractmethod
    async def delete_memory(self, memory_id: str) -> None:
        """删除记忆（统一用memory_id定位，替代原MemoryT参数，更明确）"""
        pass

    @abstractmethod
    async def update_memory(self, memory: MemoryT) -> None:
        """更新记忆（通过memory.id定位）"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭资源（如数据库连接、连接池，原代码缺失，导致资源泄漏风险）"""
        pass


class IVectorMemory(IMemoryBase[MemoryT]):
    """向量记忆接口，定义了向量记忆的基本操作"""
    
    @abstractmethod
    def get_embedding_llm(self) -> IEmbeddingLLM:
        """获取用于记忆的嵌入式语言模型
        
        Returns:
            嵌入式语言模型实例
        """
        pass
    
    @abstractmethod
    async def search_memory(
        self, 
        query: str, 
        top_k: int, 
        threshold: float, 
        filter: str
    ) -> list[tuple[MemoryT, float]]:
        """在记忆中搜索与查询最相关的条目
        
        Args:
            query: 查询字符串
            top_k: 返回的最相关条目数量
            threshold: 相关性阈值
            filter: 过滤条件字符串
            
        Returns:
            相关记忆条目列表及其相关性分数
        """
        pass


class ISqlMemory(IMemoryBase[MemoryT]):
    """SQL记忆接口，定义了SQL记忆的基本操作"""
    
    @abstractmethod
    async def search_memory(self, field: str, limit: int, **kwargs: Any) -> list[MemoryT]:
        """在记忆中搜索与查询最相关的条目
        
        Args:
            field: 查询字段
            limit: 返回的最相关条目数量
            **kwargs: 其他过滤条件
            
        Returns:
            相关记忆条目列表
        """
        pass


class IKVMemory(ABC, Generic[MemoryT]):
    """键值记忆接口，定义了键值记忆的基本操作"""
    
    @abstractmethod
    async def add_memory(self, key: str, value: MemoryT) -> None:
        """添加新的记忆条目
        
        Args:
            key: 记忆的键
            value: 记忆对象，必须实现MemoryProtocol协议
            
        Raises:
            KeyError: 如果键已存在
        """
        pass
    
    @abstractmethod
    async def batch_add_memory(self, items: dict[str, MemoryT]) -> None:
        """批量添加记忆条目
        
        Args:
            items: 包含键值对的字典，键为记忆的键，值为记忆对象
            
        Raises:
            KeyError: 如果任何键已存在
        """
        pass
    
    @abstractmethod
    async def delete_memory(self, key: str) -> None:
        """删除指定的记忆条目
        
        Args:
            key: 记忆的键
        """
        pass
    
    @abstractmethod
    async def batch_delete_memory(self, keys: list[str]) -> None:
        """批量删除记忆条目
        
        Args:
            keys: 记忆键列表
        """
        pass
    
    @abstractmethod
    async def update_memory(self, key: str, value: MemoryT) -> None:
        """更新已有的记忆条目
        
        Args:
            key: 记忆的键
            value: 记忆对象，必须实现MemoryProtocol协议
        """
        pass
    
    @abstractmethod
    async def batch_update_memory(self, items: dict[str, MemoryT]) -> None:
        """批量更新记忆条目
        
        Args:
            items: 包含键值对的字典，键为记忆的键，值为记忆对象
        """
        pass
    
    @abstractmethod
    async def search_memory(self, key: str) -> MemoryT | None:
        """根据键获取记忆条目
        
        Args:
            key: 记忆的键
            
        Returns:
            记忆对象或None如果未找到
        """
        pass
    
    @abstractmethod
    async def batch_search_memory(self, keys: list[str]) -> dict[str, MemoryT | None]:
        """批量获取记忆条目
        
        Args:
            keys: 记忆键列表
            
        Returns:
            包含键值对的字典，键为记忆的键，值为记忆对象或None如果未找到
        """
        pass
