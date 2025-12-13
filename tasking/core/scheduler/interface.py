from abc import ABC, abstractmethod
from typing import Generic, Callable, Awaitable, Any

from ..state_machine.const import EventT, StateT
from ..state_machine.task import ITask
from ...model import Message, IQueue


class IScheduler(ABC, Generic[StateT, EventT]):
    """调度器接口定义"""

    # ********** 调度器初始化 **********

    @abstractmethod
    def get_max_revisit_count(self) -> int:
        """获取状态最大可重复访问次数

        Returns:
            状态最大可重复访问次数
        """

    @abstractmethod
    def get_end_states(self) -> set[StateT]:
        """获取任务的结束状态

        Returns:
            任务结束状态集合，如果未设置则返回空集合
        """

    @abstractmethod
    def get_on_state_changed_fn(
        self,
        state_transition: tuple[StateT, StateT],
    ) -> Callable[
        ["IScheduler[StateT, EventT]", dict[str, Any], IQueue[Message], ITask[StateT, EventT]],
        Awaitable[None]
    ] | None:
        """获取指定状态转换的调度规则任务。

        Args:
            state_transition: 状态转换元组 (from_state, to_state)

        Returns:
            触发的任务函数，如果未设置则返回None。函数签名为
                - 参数1：调度器实例，允许递归调用调度器
                - 参数2：context，上下文字典，用于传递用户ID/AccessToken/TraceID等信息
                - 参数3：queue，数据队列，用于输出调度过程中产生的数据
                - 参数4：任务状态机实例
        """

    @abstractmethod
    def get_on_state_fn(self, state: StateT) -> Callable[
        ["IScheduler[StateT, EventT]", dict[str, Any], IQueue[Message], ITask[StateT, EventT]],
        Awaitable[EventT]
    ] | None:
        """获取指定状态的任务调用函数

        Args:
            state: 任务状态

        Returns:
            任务调用函数，如果未设置则返回None。函数签名为
                - 参数1：调度器实例，允许递归调用调度器
                - 参数2：context，上下文字典，用于传递用户ID/AccessToken/TraceID等信息
                - 参数3：queue，数据队列，用于输出调度过程中产生的数据
                - 参数4：任务状态机实例
        """

    # ********** 调度与事件处理 **********

    @abstractmethod
    async def on_state(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[StateT, EventT],
        current_state: StateT,
    ) -> None:
        """状态变更回调接口，状态机状态变化时被调用

        Args:
            context: 上下文字典，用于传递用户ID/AccessToken/TraceID等信息
            queue: 数据队列，用于输出调度过程中产生的数据
            task: 任务状态机实例
            current_state: 当前状态

        Raises:
            RuntimeError: 如果调度器未编译则抛出该异常
            ValueError: 如果状态转换不合法则抛出该异常
        """

    @abstractmethod
    async def on_state_changed(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        task: ITask[StateT, EventT],
        prev_state: StateT,
        current_state: StateT,
    ) -> None:
        """状态变更回调接口，状态机状态变化时被调用

        Args:
            context: 上下文字典，用于传递用户ID/AccessToken/TraceID等信息
            queue: 数据队列，用于输出调度过程中产生的数据
            task: 任务状态机实例
            prev_state: 变更前的状态
            current_state: 变更后的状态

        Raises:
            RuntimeError: 如果调度器未编译则抛出该异常
            ValueError: 如果状态转换不合法则抛出该异常
        """

    @abstractmethod
    async def schedule(self, context: dict[str, Any], queue: IQueue[Message], task: ITask[StateT, EventT]) -> None:
        """调度任务状态机，根据其当前状态执行相应任务，直到进入结束状态

        Args:
            context: 上下文字典，用于传递用户ID/AccessToken/TraceID等信息
            queue: 数据队列，用于输出调度过程中产生的数据
            task: 任务状态机实例

        Raises:
            RuntimeError: 如果调度器未编译则抛出该异常
            ValueError: 如果状态转换不合法则抛出该异常
        """

    # ********** 编译状态 **********

    @abstractmethod
    def compile(self) -> None:
        """编译调度器，支持用户指定状态最大可重复访问次数，防止无限循环。
        核心逻辑：允许状态重复访问（支持合法循环），但超过指定次数仍未到结束状态则判定为非法循环

        Raises:
            RuntimeError: 调度器已编译/无结束状态/无转换规则/存在超次数循环的不可达状态
            ValueError: 结束状态未参与转换 / max_revisit_count为负数
        """

    @abstractmethod
    def is_compiled(self) -> bool:
        """检查调度器是否已编译完成

        Returns:
            如果调度器已编译则返回True，否则返回False
        """
