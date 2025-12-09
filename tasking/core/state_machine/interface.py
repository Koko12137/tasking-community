from abc import ABC, abstractmethod
from typing import Generic, Callable, Awaitable

from .const import StateT, EventT


class IStateMachine(ABC, Generic[StateT, EventT]):
    """扩展后的状态机接口，支持合法状态管控和重置"""

    # ********** 状态机初始化 **********

    @abstractmethod
    def get_id(self) -> str:
        """获取状态机唯一标识

        Returns:
            状态机ID字符串
        """
        pass

    @abstractmethod
    def get_valid_states(self) -> set[StateT]:
        """获取所有有效状态

        Returns:
            有效状态的集合视图的副本
        """
        pass

    @abstractmethod
    def get_current_state(self) -> StateT:
        """获取当前状态

        Returns:
            当前状态
        """
        pass

    @abstractmethod
    def get_transitions(
        self
    ) -> dict[
        tuple[StateT, EventT],
        tuple[StateT, Callable[["IStateMachine[StateT, EventT]"], Awaitable[None] | None] | None]
    ]:
        """获取所有状态转换规则的集合视图的副本

        Returns:
            状态转换规则的字典，键为(from_state, event)，值为(to_state, action)
        """
        pass

    # ********** 编译状态 **********

    @abstractmethod
    def compile(self) -> None:
        """编译状态机，完成初始化及全状态可达性检查

        编译时必须满足以下所有条件：
        1. 已设置有效状态集合（非空）
        2. 已设置初始状态（且在有效状态集合中）
        3. 已设置至少一个转换规则
        4. 所有有效状态均可从初始状态出发到达（允许有环）

        Raises:
            ValueError: 若上述条件不满足则抛出对应异常
        """
        pass

    @abstractmethod
    def is_compiled(self) -> bool:
        """检查状态机是否已编译完毕

        Returns:
            如果已编译则返回True，否则返回False
        """
        pass

    # ********** 事件处理 **********

    @abstractmethod
    async def handle_event(self, event: EventT) -> None:
        """处理事件并触发状态转换（事件必须是合法事件）

        Args:
            event: 触发事件

        Raises:
            ValueError: 如果当前状态未设置或没有定义对应的转换规则则抛出该异常
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """重置状态机到初始状态
        """
        pass
