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


class ReActStage(str, Enum):
    """ReAct 工作流阶段枚举"""
    REASONING = "reasoning"
    REFLECTING = "reflecting"
    FINISHED = "finished"

    @classmethod
    def list_stages(cls) -> list['ReActStage']:
        """列出所有工作流阶段
        
        Returns:
            工作流阶段列表
        """
        return [stage for stage in ReActStage]


class ReActEvent(Enum):
    """ReAct 工作流事件枚举"""
    REASON = auto()     # 触发推理
    REFLECT = auto()    # 触发反思
    FINISH = auto()     # 触发完成


class SimpleStage(str, Enum):
    """Simple 工作流阶段枚举"""
    PROCESSING = "processing"
    COMPLETED = "completed"

    @classmethod
    def list_stages(cls) -> list['SimpleStage']:
        """列出所有工作流阶段
        
        Returns:
            工作流阶段列表
        """
        return [stage for stage in SimpleStage]
    

class SimpleEvent(Enum):
    """Simple 工作流事件枚举"""
    PROCESS = auto()    # 触发处理
    COMPLETE = auto()   # 触发完成
