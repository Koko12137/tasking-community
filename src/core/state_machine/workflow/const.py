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
