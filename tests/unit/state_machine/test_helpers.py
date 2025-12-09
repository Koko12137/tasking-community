"""
测试辅助函数和基类

提供共享的测试工具函数和基类，减少测试代码重复。
"""

from typing import Any, Dict, Tuple, Optional, Callable
from unittest import TestCase
import uuid

from tasking.core.state_machine.task.base import BaseTask
from tasking.core.state_machine.task.tree import BaseTreeTaskNode
from tasking.core.state_machine.task.const import TaskState, TaskEvent
from tasking.core.state_machine.base import BaseStateMachine
from tasking.core.state_machine.task.interface import ITreeTaskNode
from tasking.model import CompletionConfig, Message, Role

# Type aliases for complex types
TaskTransition = Tuple[TaskState, Optional[Callable]]
TransitionMap = Dict[Tuple[TaskState, TaskEvent], TaskTransition]


def extract_states_from_transitions(transitions: TransitionMap) -> set[TaskState]:
    """从状态转换规则中提取所有状态

    Args:
        transitions: 状态转换规则映射

    Returns:
        包含所有状态的集合
    """
    states = set()
    for (from_state, _event), (to_state, _action) in transitions.items():
        states.add(from_state)
        states.add(to_state)
    return states


class BaseTaskTestMixin:
    """测试任务的混入类，提供共享的测试工具方法"""

    @staticmethod
    def create_basic_transitions() -> TransitionMap:
        """创建基础的状态转换规则"""
        return {
            (TaskState.INITED, TaskEvent.IDENTIFIED): (TaskState.CREATED, None),
            (TaskState.CREATED, TaskEvent.PLANED): (TaskState.RUNNING, None),
            (TaskState.RUNNING, TaskEvent.DONE): (TaskState.FINISHED, None),
            (TaskState.RUNNING, TaskEvent.ERROR): (TaskState.FAILED, None),
            (TaskState.CREATED, TaskEvent.CANCEL): (TaskState.CANCELED, None),
        }

    @staticmethod
    def create_completion_config(**overrides: Any) -> CompletionConfig:
        """创建完成配置"""
        default_config = {
            "temperature": 0.7,
            "max_tokens": 1000
        }
        default_config.update(overrides)
        return CompletionConfig(**default_config)

    @staticmethod
    def create_base_task(
        protocol: str,
        tags: set[str],
        task_type: str,
        transitions: Optional[TransitionMap] = None,
        max_revisit_limit: int = 0,
        **config_overrides: Any
    ) -> BaseTask:
        """创建基础任务实例"""
        if transitions is None:
            transitions = BaseTaskTestMixin.create_basic_transitions()

        completion_config = BaseTaskTestMixin.create_completion_config(**config_overrides)

        # 从 transitions 中提取所有状态
        valid_states = extract_states_from_transitions(transitions)
        # 使用 INITED 作为初始状态
        init_state = TaskState.INITED

        return BaseTask(
            valid_states=valid_states,
            init_state=init_state,
            transitions=transitions,
            protocol=protocol,
            tags=tags,
            task_type=task_type,
            max_revisit_limit=max_revisit_limit,
            completion_config=completion_config
        )

    @staticmethod
    def create_tree_task(
        protocol: str,
        tags: set[str],
        task_type: str,
        parent_task: Optional[ITreeTaskNode] = None,
        transitions: Optional[TransitionMap] = None,
        max_revisit_limit: int = 0,
        max_depth: int = 10,
        **config_overrides: Any
    ) -> BaseTreeTaskNode:
        """创建树形任务实例"""
        if transitions is None:
            transitions = BaseTaskTestMixin.create_basic_transitions()

        completion_config = BaseTaskTestMixin.create_completion_config(**config_overrides)

        # 从 transitions 中提取所有状态
        valid_states = extract_states_from_transitions(transitions)
        # 使用 INITED 作为初始状态
        init_state = TaskState.INITED

        return BaseTreeTaskNode(
            valid_states=valid_states,
            init_state=init_state,
            transitions=transitions,
            protocol=protocol,
            tags=tags,
            task_type=task_type,
            max_depth=max_depth,
            max_revisit_limit=max_revisit_limit,
            completion_config=completion_config,
            parent=parent_task
        )

    @staticmethod
    def create_message(role: Role, content: str, **kwargs: Any) -> Message:
        """创建消息实例"""
        return Message(role=role, content=content, **kwargs)


class BaseStateMachineTestMixin(TestCase):
    """状态机测试的混入类"""

    @staticmethod
    def create_simple_state_machine(
        initial_state: TaskState,
        transitions: TransitionMap
    ) -> BaseStateMachine:
        """创建简单的状态机实例"""
        # 从 transitions 中提取所有状态
        valid_states = extract_states_from_transitions(transitions)

        return BaseStateMachine(
            valid_states=valid_states,
            initial_state=initial_state,
            transitions=transitions
        )

    def assert_state_sequence(self, state_machine: BaseStateMachine, expected_states: list[TaskState]) -> None:
        """断言状态转换序列"""
        for expected_state in expected_states:
            self.assertEqual(state_machine.get_current_state(), expected_state)
            if expected_state != expected_states[-1]:
                # 如果不是最后一个状态，触发下一个状态转换
                # 这里需要根据具体的转换逻辑来触发事件
                pass
