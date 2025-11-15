from enum import Enum
from typing import TypeVar, Protocol
        
        
class MemoryProtocol(Protocol):
    """记忆数据类型协议定义，可以根据需要扩展"""
    
    @property
    def name(self) -> str:
        """
        获取记忆名称
        
        Returns:
            记忆名称
        """
        ...

    @classmethod
    def list_types(cls) -> list[str]:
        """
        列出所有记忆类型

        Returns:
            记忆类型列表
        """
        ...

# 记忆数据类型，允许不同的记忆类型分类自定义
MemoryT = TypeVar('MemoryT', bound=MemoryProtocol)  


class DefaultMemory(str, Enum):
    """默认记忆类型枚举"""
    PROCEDURE = "procedure"
    # 程序性记忆, 如操作步骤、方法等
    
    SEMANTIC = "semantic"
    # 语义性记忆, 如事实性信息、知识点等
    
    EPISODIC = "episodic"
    # 事件性记忆, 如个人经历、特定事件等

    @classmethod
    def list_types(cls) -> list[str]:
        """列出所有记忆类型
        
        Returns:
            记忆类型列表
        """
        return [mem_type.value for mem_type in DefaultMemory]
