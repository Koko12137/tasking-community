from uuid import uuid4
from typing import Callable, Any, List, Awaitable

from .interface import IStateMachine, StateT, EventT


class BaseStateMachine(IStateMachine[StateT, EventT]):
    """基础状态机实现，提供合法状态管控、重置功能及编译时全状态可达性检查"""
    _id: str
    # ========== 编译状态 ==========
    _is_compiled: bool
    
    # ========== 状态管理 ==========
    _valid_states: set[StateT]
    _initial_state: StateT
    _current_state: StateT
    _transitions: dict[
        tuple[StateT, EventT], 
        tuple[StateT, Callable[[IStateMachine[StateT, EventT]], Awaitable[None] | None] | None]
    ]

    def __init__(
        self,
        valid_states: set[StateT],
        initial_state: StateT,
        transitions: dict[
            tuple[StateT, EventT],
            tuple[StateT, Callable[[IStateMachine[StateT, EventT]], Awaitable[None] | None] | None]
        ],
        **kwargs: Any
    ) -> None:
        """初始化基础状态机

        Args:
            kwargs: 其他参数（保留以备扩展）
        """
        # 不调用 super().__init__，因为 IStateMachine 是抽象接口类，没有 __init__ 方法
        
        # 状态机唯一标识
        self._id = str(uuid4())
        # 编译标志，初始化为未编译
        self._is_compiled = False

        self._valid_states = valid_states
        self._initial_state = initial_state
        self._current_state = initial_state
        self._transitions = transitions
        
        # 编译状态机
        self.compile()

    # ********** 状态机初始化 **********
    
    def get_id(self) -> str:
        """获取状态机唯一标识
        
        Returns:
            状态机ID字符串
        """
        return self._id

    def get_valid_states(self) -> set[StateT]:
        """获取所有有效状态
        
        Returns:
            有效状态的集合视图的副本
        """
        return self._valid_states.copy()

    def get_current_state(self) -> StateT:
        """获取当前状态
        
        Returns:
            当前状态
        """
        return self._current_state
        
    def get_transitions(
        self
    ) -> dict[
        tuple[StateT, EventT], 
        tuple[StateT, Callable[[IStateMachine[StateT, EventT]], Awaitable[None] | None] | None]
    ]:
        """获取所有状态转换规则的集合视图的副本
        
        Returns:
            状态转换规则的字典，键为(from_state, event)，值为(to_state, action)
        """
        return self._transitions.copy()
        
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
        # 基础校验
        if self._is_compiled:
            raise RuntimeError("State machine has already been compiled")
        if not (self._valid_states and self._initial_state):
            raise ValueError("Valid states and initial state must be set before compilation")
        if self._initial_state not in self._valid_states:
            raise ValueError(f"Initial state {self._initial_state} is not in valid states")
        if not self._transitions:
            raise ValueError("At least one transition rule must be set before compilation")

        # ========== 全状态可达性检查（允许有环） ==========
        # 1. 初始化可达状态集合（从初始状态开始）
        reachable_states: set[StateT] = {self._initial_state}
        # 2. 用BFS遍历所有可达状态（队列实现，FIFO）
        queue: List[StateT] = [self._initial_state]
        
        while queue:
            # 取出当前待处理的可达状态
            current_state = queue.pop(0)
            # 遍历所有以当前状态为起点的转换规则
            for (from_state, _event), (to_state, _action) in self._transitions.items():
                # 仅处理“起点是当前状态”且“目标状态未被标记为可达”的情况
                if from_state == current_state and to_state not in reachable_states:
                    reachable_states.add(to_state)
                    queue.append(to_state)  # 将新可达状态加入队列，继续遍历其后续转换

        # 3. 校验：可达状态是否完全覆盖有效状态集合
        unreachable_states = self._valid_states - reachable_states
        if unreachable_states:
            raise ValueError(
                f"Compilation failed: Unreachable states detected! "
                f"Initial state: {self._initial_state}, "
                f"Unreachable states: {unreachable_states}"
            )

        # 所有校验通过，标记为已编译并重置当前状态
        self._is_compiled = True
        self._current_state = self._initial_state

    def is_compiled(self) -> bool:
        return self._is_compiled

    # ********** 事件处理 **********

    def handle_event(self, event: EventT) -> None:
        """处理事件并触发状态转换（事件必须是合法事件）
        
        Args:
            event: 触发事件
            
        Raises:
            ValueError: 如果没有定义对应的转换规则则抛出该异常
        """
        key = (self._current_state, event)
        if key not in self._transitions:
            raise ValueError(
                f"No transition defined for state {self._current_state} with event {event}"
            )
        next_state, action = self._transitions[key]
        
        if action is not None:
            action(self)  # 执行状态转换前的动作
        # 切换到下一个状态
        self._current_state = next_state

    def reset(self) -> None:
        """重置状态机到初始状态"""
        if not self._is_compiled:
            raise RuntimeError("Cannot reset before compilation")
        self._current_state = self._initial_state
