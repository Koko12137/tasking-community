import inspect
from collections import defaultdict
from typing import Any, Callable, Awaitable, cast

from loguru import logger
from asyncer import asyncify

from src.core.scheduler.interface import IScheduler
from src.core.state_machine.const import StateT, EventT
from src.core.state_machine.task import ITask
from src.model import Message, IQueue


class BaseScheduler(IScheduler[StateT, EventT]):
    """基础调度器：感知状态变化、保障可靠性、触发业务任务"""
    # 最大重访次数
    _max_revisit_count: int
    # 结束状态集合
    _end_states: set[StateT] = set()
    # 状态调用函数
    _on_state_fn: dict[StateT, Callable[
        [IScheduler[StateT, EventT], 
         dict[str, Any], IQueue[Message], ITask[StateT, EventT]], Awaitable[EventT]
    ]] = {}
    # 状态转换到任务的映射表
    _on_state_changed_fn: dict[tuple[StateT, StateT], Callable[
        [IScheduler[StateT, EventT], 
         dict[str, Any], IQueue[Message], ITask[StateT, EventT]], Awaitable[EventT]
    ]] = {}
    # 编译状态
    _compiled: bool = False

    def __init__(
        self,
        end_states: set[StateT],
        on_state_fn: dict[StateT, Callable[
            [IScheduler[StateT, EventT], dict[str, Any], IQueue[Message], ITask[StateT, EventT]],
            Awaitable[EventT]
        ]],
        on_state_changed_fn: dict[tuple[StateT, StateT], Callable[
            [IScheduler[StateT, EventT], dict[str, Any], IQueue[Message], ITask[StateT, EventT]],
            Awaitable[EventT]
        ]],
        max_revisit_count: int = 0,
        **kwargs: Any,
    ) -> None:
        """
        初始化基础调度器实例

        Args:
            end_states: 任务结束状态集合
            on_state_fn: 状态调用函数映射表
            on_state_changed_fn: 状态转换到任务的映射表
            max_revisit_count: 状态最大可重复访问次数，默认值为0（无环模式）
            **kwargs: 其他参数
        """
        super().__init__(**kwargs)

        # 最大重访次数
        self._max_revisit_count = max_revisit_count
        # 编译状态
        self._compiled = False
        # 结束状态集合
        self._end_states = end_states
        # 状态调用函数
        self._on_state_fn = on_state_fn
        # 状态转换到任务的映射表
        self._on_state_changed_fn = on_state_changed_fn

        # 编译调度器
        self.compile()

    # ********** 调度器初始化 **********

    def get_max_revisit_count(self) -> int:
        """获取状态最大可重复访问次数

        Returns:
            状态最大可重复访问次数
        """
        return self._max_revisit_count

    def get_end_states(self) -> set[StateT]:
        """获取任务的结束状态

        Returns:
            任务结束状态集合，如果未设置则返回空集合
        """
        return self._end_states.copy()

    def get_on_state_changed_fn(
        self,
        state_transition: tuple[StateT, StateT],
    ) -> Callable[
        [IScheduler[StateT, EventT], dict[str, Any], IQueue[Message], ITask[StateT, EventT]],
        Awaitable[EventT]
    ] | None:
        """获取指定状态转换的调度规则任务，允许"编译"和"未编译"状态调用。

        Args:
            state_transition: 状态转换元组 (from_state, to_state)

        Returns:
            触发的任务函数，如果未设置则返回None。函数签名为
                - 参数1：调度器实例，允许递归调用调度器
                - 参数2：context，上下文字典，用于传递用户ID/AccessToken/TraceID等信息
                - 参数3：queue，数据队列，用于输出调度过程中产生的数据
                - 参数4：任务状态机实例
        """
        return self._on_state_changed_fn.get(state_transition, None)

    def get_on_state_fn(self, state: StateT) -> Callable[
        [IScheduler[StateT, EventT], dict[str, Any], IQueue[Message], ITask[StateT, EventT]],
        Awaitable[EventT]
    ] | None:
        """获取指定状态变更触发的任务函数

        Args:
            state: 任务状态（可选，如果未提供则返回默认状态函数）

        Returns:
            触发的任务函数，如果未设置则返回None。函数签名为
                - 参数1：调度器实例，允许递归调用调度器
                - 参数2：context，上下文字典，用于传递用户ID/AccessToken/TraceID等信息
                - 参数3：queue，数据队列，用于输出调度过程中产生的数据
                - 参数4：任务状态机实例
        """
        return self._on_state_fn.get(state, None)

    # ********** 调度与事件处理 **********

    async def _call_wrapper(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        task: Callable[
            [IScheduler[StateT, EventT], dict[str, Any], IQueue[Message], ITask[StateT, EventT]],
            Awaitable[EventT]
        ] | None,
        fsm: ITask[StateT, EventT],
    ) -> EventT | None:
        """调用任务包装器，支持同步和异步任务调用

        Args:
            context: 上下文字典，用于传递用户ID/AccessToken/TraceID等信息
            queue: 数据队列，用于输出调度过程中产生的数据
            task: 触发的任务函数，函数签名为
                - 参数1：调度器实例，允许递归调用调度器
                - 参数2：context，上下文字典，用于传递用户ID/AccessToken/TraceID等信息
                - 参数3：queue，数据队列，用于输出调度过程中产生的数据
                - 参数4：任务状态机实例
            fsm: 任务状态机实例
        """
        if task is None:
            logger.warning("调度任务未定义，跳过执行")
            return

        if inspect.iscoroutinefunction(task):
            event = await task(self, context, queue, fsm)
        else:
            event = await asyncify(task)(self, context, queue, fsm)
        return cast(EventT, event)

    async def on_state(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[StateT, EventT],
        current_state: StateT,
    ) -> None:
        """状态变更回调接口，状态机状态变化时被调用

        Args:
            context: 上下文字典，用于传递用户ID/AccessToken/TraceID等信息
            queue: 数据队列，用于输出调度过程中产生的数据
            fsm: 任务状态机实例
            current_state: 当前状态

        Raises:
            RuntimeError: 如果调度器未编译则抛出该异常
            ValueError: 如果状态转换不合法则抛出该异常
        """
        if not self._compiled:
            raise RuntimeError("调度器未编译，无法执行状态回调")

        # 匹配业务任务
        task = self._on_state_fn.get(current_state)
        # 执行业务任务
        event = await self._call_wrapper(context, queue, task, fsm)
        if event is None:
            return # 无事件返回，直接结束
        else:
            # 处理事件
            fsm.handle_event(event)

    async def on_state_changed(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        fsm: ITask[StateT, EventT],
        prev_state: StateT,
        current_state: StateT,
    ) -> None:
        """状态变更回调接口，状态机状态变化时被调用

        Args:
            context: 上下文字典，用于传递用户ID/AccessToken/TraceID等信息
            queue: 数据队列，用于输出调度过程中产生的数据
            fsm: 任务状态机实例
            prev_state: 变更前的状态
            current_state: 变更后的状态

        Raises:
            RuntimeError: 如果调度器未编译则抛出该异常
            ValueError: 如果状态转换不合法则抛出该异常
        """
        if not self._compiled:
            raise RuntimeError("调度器未编译，无法执行状态变更回调")

        logger.info(f"\n[调度器] 收到状态变更：{fsm.get_id()[:8]} | {prev_state.name}→{current_state.name}")

        # 匹配业务任务
        task = self._on_state_changed_fn.get((prev_state, current_state))
        # 执行业务任务
        event = await self._call_wrapper(context, queue, task, fsm)
        if event is None:
            return # 无事件返回，直接结束
        logger.info(f"[调度器] 回调任务完成：{prev_state.name}→{current_state.name}")

    async def schedule(self, context: dict[str, Any], queue: IQueue[Message], fsm: ITask[StateT, EventT]) -> Any:
        """调度任务状态机，根据其当前状态执行相应任务，直到进入结束状态

        Args:
            context: 上下文字典，用于传递用户ID/AccessToken/TraceID等信息
            queue: 数据队列，用于输出调度过程中产生的数据
            fsm: 任务状态机实例

        Raises:
            RuntimeError: 如果调度器未编译则抛出该异常
            ValueError: 如果状态转换不合法则抛出该异常
        """
        if not self._compiled:
            raise RuntimeError("调度器未编译，无法调度任务")

        current_state = fsm.get_current_state() # pyright: ignore[reportAssignmentType]
        if current_state is None: # pyright: ignore[reportUnnecessaryComparison]
            raise ValueError("任务状态机当前状态未知，无法调度任务")
        logger.info(f"\n[调度器] 调度任务：{fsm.get_id()[:8]} | 当前状态：{current_state.name}")

        # 检查是否为结束状态
        if current_state in self._end_states:
            logger.info(f"[调度器] 任务已处于结束状态：{current_state.name}，无需调度")
            return None
        
        # 设置任务的最大重访次数
        fsm.set_max_revisit_count(self._max_revisit_count)

        # 查找可用的状态任务
        while current_state not in self._end_states:
            current_state: StateT
            logger.info(f"\n[调度器] 调度任务：{fsm.get_id()[:8]} | 当前状态：{current_state.name}")
            # 执行当前状态任务
            await self.on_state(context, queue, fsm, current_state)
            # 获取下一个状态
            next_state = fsm.get_current_state()
            # 执行状态变更回调
            await self.on_state_changed(context, queue, fsm, current_state, next_state)
            # 更新当前状态
            current_state = next_state
            logger.info(f"\n[调度器] 调度任务：{fsm.get_id()[:8]} | 任务状态更新为：{current_state.name}")

        return None

    # ********** 编译状态 **********

    def compile(self) -> None:
        """编译调度器：基础校验 + 分模式状态校验
        - max_revisit_count ≤ 0：检测「无环 + 所有状态可达终态」
        - max_revisit_count > 0：检测「状态重访不超限 + 所有状态可达终态」

        Args:
            max_revisit_count: 状态最大可重复访问次数（≥0时为可达模式，≤0时为无环模式）

        Raises:
            RuntimeError: 重复编译/无结束状态/无转换规则/状态不可达/有环（无环模式）
            ValueError: 结束状态未参与转换/max_revisit_count逻辑冲突（如-1且要求无环）
        """
        # -------------------------- 基础校验（保留，无冗余） --------------------------
        # 1. 禁止重复编译
        if self._compiled:
            raise RuntimeError("调度器已编译，无法重复编译")

        # 2. 校验max_revisit_count逻辑（避免非法值，如-2无意义，统一≤0为无环模式）
        if self._max_revisit_count < 0:
            logger.warning(f"max_revisit_count={self._max_revisit_count}≤0，自动切换为「无环模式」")
            check_mode = "acyclic"  # 无环模式
        else:
            check_mode = "reachable"  # 可达模式（允许环）
        logger.info(f"[调度器] 开始编译检查（{check_mode}模式，max_revisit_count={self._max_revisit_count}）")

        # 3. 必须配置结束状态
        if not self._end_states:
            raise RuntimeError("编译失败：未配置结束状态（_end_states为空），无法判断任务终止条件")

        # 4. 必须配置转换规则
        all_states: set[StateT] = set()
        for from_state, to_state in self._on_state_changed_fn.keys():
            all_states.add(from_state)
            all_states.add(to_state)
        if not all_states:
            raise RuntimeError("编译失败：未配置任何状态转换规则（_state_change_fn为空）")

        # 5. 结束状态必须参与转换（否则永远无法到达）
        for end_state in self._end_states:
            if end_state not in all_states:
                raise ValueError(
                    f"编译失败：结束状态「{end_state.name}」未参与任何转换，永远无法到达"
                )

        # -------------------------- 构建状态转换邻接表（必要，无冗余） --------------------------
        state_adj: dict[StateT, set[StateT]] = defaultdict(set)
        for from_state, to_state in self._on_state_changed_fn.keys():
            state_adj[from_state].add(to_state)
        logger.debug(
            f"[调度器] 状态转换邻接表：{ {s.name: [t.name for t in ts] for s, ts in state_adj.items()} }"
        )

        # -------------------------- 分模式实现状态校验（核心修改） --------------------------
        def is_valid_state(start_state: StateT) -> bool:
            """
            分模式校验状态合法性：
            - 无环模式：无环 + 可达终态
            - 可达模式：重访不超限 + 可达终态
            """
            if check_mode == "acyclic":
                # 无环模式：用visited集合，每个状态只能访问一次（重复访问即有环）
                visited: set[StateT] = set()
                queue: list[StateT] = [start_state]
                visited.add(start_state)

                while queue:
                    current_state = queue.pop(0)

                    # 先判断是否到达终态
                    if current_state in self._end_states:
                        logger.debug(f"[无环校验] 状态「{current_state.name}」可达终态，且无环")
                        return True

                    # 遍历下一个状态：若已访问则判定为有环（非法）
                    for next_state in state_adj.get(current_state, set()):
                        if next_state in visited:
                            logger.debug(
                                f"[无环校验] 状态「{next_state.name}」重复访问（有环），判定非法"
                            )
                            return False
                        visited.add(next_state)
                        queue.append(next_state)

                # 遍历完未到终态（不可达）
                logger.debug(f"[无环校验] 状态「{start_state.name}」不可达终态")
                return False

            else:
                # 可达模式：用visit_count，允许重访但不超限，且需可达终态
                visit_count: dict[StateT, int] = defaultdict(int)
                queue: list[StateT] = [start_state]
                visit_count[start_state] = 1  # 初始状态访问次数=1

                while queue:
                    current_state = queue.pop(0)

                    # 先判断是否到达终态
                    if current_state in self._end_states:
                        logger.debug(f"[可达校验] 状态「{current_state.name}」可达终态，重访次数合规")
                        return True

                    # 访问次数超限：跳过该路径
                    if visit_count[current_state] > self._max_revisit_count:
                        logger.debug(
                            f"[可达校验] 状态「{current_state.name}」访问次数（{visit_count[current_state]}）超限，跳过"
                        )
                        continue

                    # 遍历下一个状态：更新访问次数并加入队列
                    for next_state in state_adj.get(current_state, set()):
                        next_count = visit_count[next_state] + 1
                        if next_count <= self._max_revisit_count:  # 未超限才加入
                            visit_count[next_state] = next_count
                            queue.append(next_state)
                            logger.debug(
                                f"[可达校验] 「{current_state.name}」→「{next_state.name}」，累计次数：{next_count}"
                            )

                # 遍历完未到终态（不可达）
                logger.debug(f"[可达校验] 状态「{start_state.name}」不可达终态（或超限）")
                return False

        # -------------------------- 批量校验所有非结束状态 --------------------------
        invalid_states: list[StateT] = []
        for state in all_states:
            if state in self._end_states:
                continue  # 结束状态无需校验
            if not is_valid_state(state):
                invalid_states.append(state)

        # -------------------------- 处理非法状态 --------------------------
        if invalid_states:
            invalid_names = [s.name for s in invalid_states]
            error_msg = (
                f"编译失败：以下状态非法（{check_mode}模式）：\n"
                f"→ 非法状态：{invalid_names}\n"
                f"→ 结束状态集合：{[s.name for s in self._end_states]}\n"
                f"→ 提示：{'无环模式需消除环并确保可达；可达模式可增大max_revisit_count或补充转换规则' if check_mode == 'reachable' else '无环模式需消除环并确保可达'}"
            )
            raise RuntimeError(error_msg)

        # -------------------------- 编译通过 --------------------------
        logger.info(f"[调度器] 编译检查通过（{check_mode}模式）")
        self._compiled = True
        logger.info("[调度器] 编译完成，准备就绪")

    def is_compiled(self) -> bool:
        """检查调度器是否已编译完成

        Returns:
            如果调度器已编译则返回True，否则返回False
        """
        return self._compiled
