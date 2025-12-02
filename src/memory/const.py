from enum import Enum
from typing import TypeVar, Protocol, Any
        
        
class MemoryProtocol(Protocol):
    """记忆对象必须实现的协议（如包含唯一标识、序列化方法等）"""
    
    @property
    def id(self) -> str:
        """唯一标识符"""
        ...
        
    @property
    def content(self) -> str:
        """记忆内容"""
        ...

    def to_dict(self) -> dict[str, Any]: 
        """将记忆对象转为字典形式"""
        ...
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'MemoryProtocol':
        """从字典形式创建记忆对象"""
        ...


# 记忆数据类型，允许不同的记忆类型分类自定义
MemoryT = TypeVar('MemoryT', bound=MemoryProtocol)  
"""记忆数据类型变量，必须实现MemoryProtocol协议，需要支持 `to_dict` 方法，并包含 `id` 和 `content` 属性"""


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
