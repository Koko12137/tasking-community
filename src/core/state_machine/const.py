from typing import TypeVar, Protocol


class StateProtocol(Protocol):
    """状态类型协议定义，要求实现名称属性"""
    
    @property
    def name(self) -> str:
        ...
        

class EventProtocol(Protocol):
    """事件类型协议定义, 可根据需要扩展"""

    @property
    def name(self) -> str:
        ...


# 定义泛型类型变量
StateT = TypeVar('StateT', bound=StateProtocol)  # 状态类型
EventT = TypeVar('EventT', bound=EventProtocol)  # 事件类型
