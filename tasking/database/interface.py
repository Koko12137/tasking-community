from abc import ABC, abstractmethod
from typing import Generic, Any

from .const import ClientT
from ..llm import IEmbedModel
from ..model import MemoryT, TextBlock, ImageBlock, VideoBlock


class IDatabase(ABC, Generic[MemoryT]):
    """所有数据库存储的通用父接口，定义基础CRUD行为"""

    @abstractmethod
    async def add(self, context: dict[str, Any], memory: MemoryT, timeout: float = 1800.0) -> None:
        """添加记忆

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            memory: 记忆对象，必须实现MemoryProtocol协议
            timeout: 超时时间（秒），默认1800秒
        """
        pass

    @abstractmethod
    async def delete(self, context: dict[str, Any], memory_id: str) -> None:
        """删除记忆
        
        Args:
            context: 上下文信息，用于配置或选择数据库实例
            memory_id: 记忆对象的唯一标识符
        """
        pass

    @abstractmethod
    async def update(self, context: dict[str, Any], memory: MemoryT) -> None:
        """更新记忆（通过memory.id定位）
        
        Args:
            context: 上下文信息，用于配置或选择数据库实例
            memory: 记忆对象，必须实现MemoryProtocol协议
        """
        pass
    

class IDBResourceManager(ABC, Generic[ClientT]):
    """数据库资源管理器接口，定义了数据库资源的管理操作"""

    @abstractmethod
    async def close(self, context: dict[str, Any]) -> None:
        """关闭资源（如数据库连接、连接池，原代码缺失，导致资源泄漏风险）
        
        Args:
            context: 上下文信息，用于配置或选择数据库实例
        """
        pass


class IVectorDatabase(IDatabase[MemoryT]):
    """向量数据库接口，定义了向量数据库的基本操作"""

    @abstractmethod
    def get_embedding_llm(self, model_name: str) -> IEmbedModel:
        """获取用于数据库的嵌入式语言模型

        Args:
            model_name: 嵌入式语言模型名称

        Returns:
            嵌入式语言模型实例
        """
        pass

    @abstractmethod
    async def search(
        self,
        context: dict[str, Any],
        query: list[TextBlock | ImageBlock | VideoBlock],
        top_k: int,
        threshold: float,
        filter_expr: str
    ) -> list[tuple[MemoryT, float]]:
        """在数据库中搜索与查询最相关的条目

        Args:
            query: 查询内容（文本或多模态内容）
            top_k: 返回的最相关条目数量
            threshold: 相关性阈值
            filter_expr: 过滤条件表达式字符串

        Returns:
            相关记忆条目列表及其相关性分数
        """
        pass
    
    @abstractmethod
    async def query(
        self,
        context: dict[str, Any],
        filter_expr: str,
        output_fields: list[str] | None = None,
        limit: int | None = None,
    ) -> list[MemoryT]:
        """在数据库中根据过滤条件查询记忆条目

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            filter_expr: 过滤条件表达式字符串
            output_fields: 要查询的字段列表，如果为None则查询所有字段(*)
            limit: 返回的最大条目数量

        Returns:
            相关记忆条目列表
        """
        pass


class IVectorDBManager(IDBResourceManager[ClientT]):
    """向量数据库管理器接口，定义了向量数据库的管理操作"""
    
    @abstractmethod
    async def get_vector_database(self, context: dict[str, Any]) -> ClientT:
        """获取向量数据库实例
 
        Args:
            context: 上下文信息，用于配置或选择数据库实例
            
        Returns:
            向量数据库实例
        """
        pass


class ISqlDatabase(IDatabase[MemoryT]):
    """SQL数据库接口，定义了SQL数据库的基本操作"""

    @abstractmethod
    async def search(
        self,
        context: dict[str, Any],
        fields: list[str] | None = None,
        where: list[str] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        **kwargs: Any
    ) -> list[MemoryT]:
        """在数据库中搜索与查询最相关的条目

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            fields: 要查询的字段列表，如果为None则查询所有字段(*)
            where: WHERE过滤条件列表，每个条件为完整的SQL表达式，如 ["status = 'active'", "created_at > '2024-01-01'"]
            order_by: 排序字段，支持ASC/DESC，如 "id DESC"
            limit: 返回的最大条目数量
            **kwargs: 其他SQL参数（具体支持取决于实现类，如果不支持应抛出错误）

        Returns:
            相关记忆条目列表
        """
        pass


class ISqlDBManager(IDBResourceManager[ClientT]):
    """SQL数据库管理器接口，定义了SQL数据库的管理操作"""
    
    @abstractmethod
    async def get_sql_database(self, context: dict[str, Any]) -> ClientT:
        """获取SQL数据库实例
 
        Args:
            context: 上下文信息，用于配置或选择数据库实例
            
        Returns:
            SQL数据库实例
        """
        pass


class IKVDatabase(ABC, Generic[MemoryT]):
    """键值数据库接口，定义了键值数据库的基本操作"""

    @abstractmethod
    async def add(self, context: dict[str, Any], key: str, value: MemoryT, timeout: float = 1800.0) -> None:
        """添加新的记忆条目

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            key: 记忆的键
            value: 记忆对象，必须实现MemoryProtocol协议
            timeout: 超时时间（秒），默认1800秒

        Raises:
            KeyError: 如果键已存在
        """
        pass

    @abstractmethod
    async def batch_add(self, context: dict[str, Any], items: dict[str, MemoryT]) -> None:
        """批量添加记忆条目

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            items: 包含键值对的字典，键为记忆的键，值为记忆对象

        Raises:
            KeyError: 如果任何键已存在
        """
        pass

    @abstractmethod
    async def delete(self, context: dict[str, Any], key: str) -> None:
        """删除指定的记忆条目

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            key: 记忆的键
        """
        pass

    @abstractmethod
    async def batch_delete(self, context: dict[str, Any], keys: list[str]) -> None:
        """批量删除记忆条目

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            keys: 记忆键列表
        """
        pass

    @abstractmethod
    async def update(self, context: dict[str, Any], key: str, value: MemoryT) -> None:
        """更新已有的记忆条目

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            key: 记忆的键
            value: 记忆对象，必须实现MemoryProtocol协议
        """
        pass

    @abstractmethod
    async def batch_update(self, context: dict[str, Any], items: dict[str, MemoryT]) -> None:
        """批量更新记忆条目

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            items: 包含键值对的字典，键为记忆的键，值为记忆对象
        """
        pass

    @abstractmethod
    async def search(self, context: dict[str, Any], key: str) -> MemoryT | None:
        """根据键获取记忆条目

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            key: 记忆的键

        Returns:
            记忆对象或None如果未找到
        """
        pass

    @abstractmethod
    async def batch_search(self, context: dict[str, Any], keys: list[str]) -> dict[str, MemoryT | None]:
        """批量获取记忆条目

        Args:
            context: 上下文信息，用于配置或选择数据库实例
            keys: 记忆键列表

        Returns:
            包含键值对的字典，键为记忆的键，值为记忆对象或None如果未找到
        """
        pass


class IKVDBManager(IDBResourceManager[ClientT]):
    """键值数据库管理器接口，定义了键值数据库的管理操作"""
    
    @abstractmethod
    async def get_kv_database(self, context: dict[str, Any]) -> ClientT:
        """获取键值数据库实例
 
        Args:
            context: 上下文信息，用于配置或选择数据库实例
            
        Returns:
            键值数据库实例
        """
        pass
