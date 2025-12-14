"""
Basic tests for the scheduler module.
"""

import unittest
from typing import Optional, List
from unittest.mock import MagicMock
from queue import Queue

from tasking.core.scheduler.base import BaseScheduler
# StateChangeContext removed - not found in interface
from tasking.core.state_machine.task.const import TaskEvent, TaskState
# Message imported for testing purposes


class MockTask:
    """Mock task implementation."""

    def __init__(self, task_id: str = "test_task", initial_state: TaskState = TaskState.CREATED, valid_states: set[TaskState] | None = None):
        self._task_id = task_id
        self._current_state = initial_state
        self._data = {"task_id": task_id}
        self._state_visit_counts = {initial_state: 1}
        self._error_info = None
        self._sub_tasks = []
        self._event_log = []
        self._max_revisit_count = 0
        # Default valid states
        self._valid_states = valid_states or {TaskState.CREATED, TaskState.RUNNING, TaskState.FINISHED, TaskState.CANCELED}

    def get_id(self) -> str:
        """Get task ID."""
        return self._task_id

    def get_valid_states(self) -> set[TaskState]:
        """Get valid states."""
        return self._valid_states.copy()

    def get_current_state(self) -> TaskState:
        """Get current state."""
        return self._current_state

    def set_current_state(self, state: TaskState) -> None:
        """Set current state."""
        self._current_state = state
        self._state_visit_counts[state] = self._state_visit_counts.get(state, 0) + 1

    def set_max_revisit_count(self, count: int) -> None:
        """Set max revisit count (no-op stub for scheduler)."""
        self._max_revisit_count = count

    async def handle_event(self, event: TaskEvent) -> None:
        """Handle event and update state."""
        self._event_log.append((self._current_state, event))

        # Simple state machine - use early returns for clarity
        state_transition_map = {
            (TaskState.CREATED, TaskEvent.INIT): TaskState.RUNNING,
            (TaskState.RUNNING, TaskEvent.PLANED): TaskState.RUNNING,
            (TaskState.RUNNING, TaskEvent.DONE): TaskState.FINISHED,
            (TaskState.RUNNING, TaskEvent.CANCEL): TaskState.CANCELED,
        }

        key = (self._current_state, event)
        if key in state_transition_map:
            self.set_current_state(state_transition_map[key])

    @property
    def data(self) -> dict:
        """Get task data."""
        return self._data

    @data.setter
    def data(self, value: dict) -> None:
        """Set task data."""
        self._data = value

    def get_state_visit_count(self, state: TaskState) -> int:
        """Get state visit count."""
        return self._state_visit_counts.get(state, 0)

    def is_error(self) -> bool:
        """Check if task has error."""
        return self._error_info is not None

    def get_error_info(self) -> Optional[str]:
        """Get error info."""
        return self._error_info

    def set_error_info(self, error: Optional[str]) -> None:
        """Set error info."""
        self._error_info = error

    def clean_error_info(self) -> None:
        """Clean error info."""
        self._error_info = None

    def reset(self) -> None:
        """Reset task to initial state."""
        self._current_state = TaskState.CREATED
        self._state_visit_counts = {TaskState.CREATED: 1}
        self._error_info = None
        self._event_log = []

    def get_sub_tasks(self) -> List["MockTask"]:
        """Get sub tasks."""
        return self._sub_tasks

    def add_sub_task(self, sub_task: "MockTask") -> None:
        """Add sub task."""
        self._sub_tasks.append(sub_task)


class TestBaseScheduler(unittest.IsolatedAsyncioTestCase):
    """Test BaseScheduler functionality."""

    async def test_compilation_no_end_states(self) -> None:
        """Test that compilation fails without end states."""
        with self.assertRaises(RuntimeError) as context:
            BaseScheduler(
                end_states=set(),
                on_state_fn={},
                on_state_changed_fn={},
                max_revisit_count=1
            )
        self.assertIn("未配置结束状态", str(context.exception))

    async def test_compilation_no_transitions(self) -> None:
        """Test that compilation fails without transitions."""
        with self.assertRaises(RuntimeError) as context:
            BaseScheduler(
                end_states={TaskState.FINISHED},
                on_state_fn={},
                on_state_changed_fn={},
                max_revisit_count=1
            )
        self.assertIn("未配置任何状态转换规则", str(context.exception))

    async def test_compilation_end_state_not_reachable(self) -> None:
        """Test that compilation fails when end state is not reachable."""
        async def mock_callback(_scheduler, _context, _queue, _fsm):
            return TaskEvent.DONE

        with self.assertRaises(ValueError) as context:
            BaseScheduler(
                end_states={TaskState.FINISHED},
                on_state_fn={},
                on_state_changed_fn={
                    (TaskState.CREATED, TaskState.RUNNING): mock_callback,
                },
                max_revisit_count=1
            )
        self.assertIn("未参与任何转换", str(context.exception))

    async def test_compilation_success(self) -> None:
        """Test successful compilation."""
        async def mock_callback(_scheduler, _context, _queue, _fsm):
            return TaskEvent.DONE

        async def mock_state_fn(_scheduler, _context, _queue, _fsm):
            return TaskEvent.DONE

        scheduler = BaseScheduler(
            end_states={TaskState.FINISHED},
            on_state_fn={
                TaskState.CREATED: mock_state_fn,  # CREATED has outgoing edge, needs on_state_fn
                TaskState.RUNNING: mock_state_fn
            },
            on_state_changed_fn={
                (TaskState.CREATED, TaskState.RUNNING): mock_callback,
                (TaskState.RUNNING, TaskState.FINISHED): mock_callback
            },
            max_revisit_count=1
        )
        self.assertTrue(scheduler.is_compiled())
        self.assertEqual(scheduler.get_max_revisit_count(), 1)

    async def test_compilation_detects_unreachable_states(self) -> None:
        """Test that compilation rejects states that cannot reach an end state."""

        async def noop_state(_scheduler, _context, _queue, _fsm):
            return TaskEvent.DONE

        with self.assertRaises(RuntimeError) as context:
            BaseScheduler(
                end_states={TaskState.FINISHED},
                on_state_fn={
                    TaskState.CREATED: noop_state,
                    TaskState.RUNNING: noop_state,  # RUNNING has outgoing edge, needs on_state_fn
                },
                on_state_changed_fn={
                    (TaskState.CREATED, TaskState.RUNNING): lambda *_: TaskEvent.PLANED,
                    (TaskState.RUNNING, TaskState.CREATED): lambda *_: TaskEvent.INIT,
                    (TaskState.FINISHED, TaskState.CREATED): lambda *_: TaskEvent.INIT,
                },
                max_revisit_count=1,
            )
        # Now it should fail on unreachable states check, not on_state_fn check
        self.assertIn("非法状态", str(context.exception))

    async def test_compilation_enforces_acyclic_mode_with_cycle(self) -> None:
        """Test that acyclic mode rejects cyclic state graphs."""

        async def noop_state(_scheduler, _context, _queue, _fsm):
            return TaskEvent.DONE

        with self.assertRaises(RuntimeError) as context:
            BaseScheduler(
                end_states={TaskState.FINISHED},
                on_state_fn={
                    TaskState.CREATED: noop_state,
                    TaskState.RUNNING: noop_state,  # RUNNING has outgoing edge, needs on_state_fn
                },
                on_state_changed_fn={
                    (TaskState.CREATED, TaskState.RUNNING): lambda *_: TaskEvent.PLANED,
                    (TaskState.RUNNING, TaskState.CREATED): lambda *_: TaskEvent.INIT,
                    (TaskState.RUNNING, TaskState.FINISHED): lambda *_: TaskEvent.DONE,
                },
                max_revisit_count=-1,
            )
        # Now it should fail on acyclic check, not on_state_fn check
        self.assertIn("无环", str(context.exception))

    async def test_schedule_not_compiled_error(self) -> None:
        """Test that schedule fails when scheduler is not compiled."""
        # Create a scheduler manually without compiling
        scheduler = BaseScheduler.__new__(BaseScheduler)
        # Initialize the required attributes without calling compile
        scheduler._BaseScheduler__compiled = False
        scheduler._BaseScheduler__end_states = {TaskState.FINISHED}
        scheduler._BaseScheduler__on_state_fn = {}
        scheduler._BaseScheduler__on_state_changed_fn = {}
        scheduler._BaseScheduler__max_revisit_count = 0

        task = MagicMock()
        queue = Queue()

        with self.assertRaises(RuntimeError) as context:
            await scheduler.schedule({}, queue, task)
        self.assertIn("调度器未编译", str(context.exception))

    async def test_on_state_methods_not_compiled(self) -> None:
        """Test that on_state methods fail when scheduler is not compiled."""
        # Create a scheduler manually without compiling
        scheduler = BaseScheduler.__new__(BaseScheduler)
        # Initialize the required attributes without calling compile
        scheduler._BaseScheduler__compiled = False
        scheduler._BaseScheduler__end_states = {TaskState.FINISHED}
        scheduler._BaseScheduler__on_state_fn = {}
        scheduler._BaseScheduler__on_state_changed_fn = {}
        scheduler._BaseScheduler__max_revisit_count = 0

        task = MagicMock()
        queue = Queue()

        with self.assertRaises(RuntimeError):
            await scheduler.on_state({}, queue, task, TaskState.CREATED)

        # Test state transition without error
        try:
            context = {"test": "state_change"}
            await scheduler.on_state_changed(
                context, queue, task, TaskState.CREATED, TaskState.RUNNING
            )
        except RuntimeError:
            pass  # Expected for invalid transition

    async def test_simple_workflow_execution(self) -> None:
        """Test execution of a simple workflow."""
        async def created_fn(_scheduler, _context, _queue, fsm):
            await fsm.handle_event(TaskEvent.INIT)
            return TaskEvent.INIT

        async def running_fn(_scheduler, _context, _queue, fsm):
            await fsm.handle_event(TaskEvent.PLANED)
            return TaskEvent.PLANED

        async def running_fn2(_scheduler, _context, _queue, fsm):
            await fsm.handle_event(TaskEvent.DONE)
            return TaskEvent.DONE

        async def transition_fn(_scheduler, _context, _queue, _fsm):
            return TaskEvent.DONE

        # Need max_revisit_count > 0 for workflow to work
        scheduler = BaseScheduler(
            end_states={TaskState.FINISHED},
            on_state_fn={
                TaskState.CREATED: created_fn,  # type: ignore
                TaskState.RUNNING: running_fn2  # type: ignore
            },
            on_state_changed_fn={
                (TaskState.CREATED, TaskState.RUNNING): transition_fn,
                (TaskState.RUNNING, TaskState.FINISHED): transition_fn
            },
            max_revisit_count=3  # Allow multiple visits
        )

        # Task valid states must match scheduler configuration
        task = MockTask("simple_task", valid_states={TaskState.CREATED, TaskState.RUNNING, TaskState.FINISHED})
        context = {"test": "execution"}
        queue = Queue()

        await scheduler.schedule(context, queue, task)  # type: ignore

        self.assertEqual(task.get_current_state(), TaskState.FINISHED)


if __name__ == '__main__':
    unittest.main()
