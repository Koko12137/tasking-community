from enum import Enum, auto
from typing import TypeVar, Protocol, Any


class WorkflowStageProtocol(Protocol):
    """工作流阶段协议"""
    
    @property
    def name(self) -> str:
        """"""
        ...
        
    @classmethod
    def list_stages(cls) -> list[Any]:
        """"""
        ...


WorkflowStageT = TypeVar("WorkflowStageT", bound=WorkflowStageProtocol)


class WorkflowEventProtocol(Protocol):
    """工作流事件协议"""
    
    @property
    def name(self) -> str:
        """"""
        ...

        
WorkflowEventT = TypeVar("WorkflowEventT", bound=WorkflowEventProtocol)


class ReflectStage(str, Enum):
    """ReAct - Reflect 工作流阶段枚举"""
    REASONING = "reasoning"
    REFLECTING = "reflecting"
    FINISHED = "finished"

    @classmethod
    def list_stages(cls) -> list['ReflectStage']:
        """列出所有工作流阶段
        
        Returns:
            工作流阶段列表
        """
        return [stage for stage in ReflectStage]


class ReflectEvent(Enum):
    """ReAct - Reflect 工作流事件枚举"""
    REASON = auto()     # 触发推理
    REFLECT = auto()    # 触发反思
    FINISH = auto()     # 触发完成

    @property
    def name(self) -> str:
        """获取事件名称"""
        return self._name_.lower()


class ReActStage(str, Enum):
    """Simple 工作流阶段枚举"""
    PROCESSING = "processing"
    COMPLETED = "completed"

    @classmethod
    def list_stages(cls) -> list['ReActStage']:
        """列出所有工作流阶段
        
        Returns:
            工作流阶段列表
        """
        return [stage for stage in ReActStage]
    

class ReActEvent(Enum):
    """Simple 工作流事件枚举"""
    PROCESS = auto()    # 触发处理
    COMPLETE = auto()   # 触发完成

    @property
    def name(self) -> str:
        """获取事件名称"""
        return self._name_.lower()
