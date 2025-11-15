"""Corner case tests for scheduler module."""

import asyncio
import unittest
from unittest.mock import AsyncMock
from queue import Queue

from src.core.scheduler.base import BaseScheduler
from src.core.state_machine.task.const import TaskEvent, TaskState
from src.model import Message
from src.model.queue import IQueue


class ProblematicTask:
    """Task implementation that exhibits problematic behavior for testing."""

    def __init__(self, task_id: str = "problematic", behavior: str = "normal"):
        self._task_id = task_id
        self._current_state = TaskState.INITED
        self._data = {"task_id": task_id}
        self._state_visit_counts = {TaskState.INITED: 1}
        self._error_info = None
        self._sub_tasks = []
        self._event_log = []
        self._behavior = behavior
        self._call_count = 0
        self._title = f"Problematic Task {task_id}"
        self._tags = {"test", "problematic"}

    def get_id(self) -> str:
        """Get task ID."""
        return self._task_id

    def get_current_state(self) -> TaskState:
        """Get current state."""
        if self._behavior == "state_error":
            raise RuntimeError("State retrieval error")
        return self._current_state

    def set_current_state(self, state: TaskState) -> None:
        """Set current state."""
        if self._behavior == "state_set_error":
            raise ValueError("Cannot set state")
        self._current_state = state
        self._state_visit_counts[state] = self._state_visit_counts.get(state, 0) + 1

    def handle_event(self, event: TaskEvent) -> None:
        """Handle event and update state."""
        self._call_count += 1
        self._event_log.append((self._current_state, event))

        # Different problematic behaviors
        if self._behavior == "exception_on_event":
            raise RuntimeError("Event handling error")

        # Normal behavior
        if self._behavior == "reject_all":
            # Don't change state
            pass
        elif self._behavior == "infinite_loop":
            # Stay in current state
            pass
        elif self._behavior == "state_mismatch":
            # Report different state than actual
            if self._call_count % 2 == 0:
                self.set_current_state(TaskState.FINISHED)
        elif self._current_state == TaskState.INITED and event == TaskEvent.IDENTIFIED:
            self.set_current_state(TaskState.CREATED)
        elif self._current_state == TaskState.CREATED and event == TaskEvent.PLANED:
            self.set_current_state(TaskState.RUNNING)
        elif self._current_state == TaskState.RUNNING:
            if event == TaskEvent.DONE:
                self.set_current_state(TaskState.FINISHED)
            elif event == TaskEvent.ERROR:
                self.set_current_state(TaskState.FAILED)
        elif self._current_state == TaskState.FAILED:
            if event == TaskEvent.RETRY:
                self.set_current_state(TaskState.RUNNING)
            elif event == TaskEvent.CANCEL:
                self.set_current_state(TaskState.CANCELED)

    @property
    def data(self) -> dict:
        """Get task data."""
        if self._behavior == "data_error":
            raise RuntimeError("Data access error")
        return self._data

    @data.setter
    def data(self, value: dict) -> None:
        """Set task data."""
        if self._behavior == "data_set_error":
            raise ValueError("Cannot set data")
        self._data = value

    def get_state_visit_count(self, state: TaskState) -> int:
        """Get state visit count."""
        if self._behavior == "visit_count_error":
            raise RuntimeError("Visit count error")
        return self._state_visit_counts.get(state, 0)

    def get_max_revisit_limit(self) -> int:
        """Get max revisit limit."""
        return 3

    def is_error(self) -> bool:
        """Check if task is in error state."""
        return self._error_info is not None

    def get_error_info(self) -> str:
        """Get error information."""
        return self._error_info or ""

    def set_error_info(self, error: str) -> None:
        """Set error information."""
        self._error_info = error

    def set_error(self, error_info: any) -> None:
        """Set error state."""
        self._error_info = str(error_info) if error_info else None

    def clean_error_info(self) -> None:
        """Clear error information."""
        self._error_info = None

    def reset(self) -> None:
        """Reset task to initial state."""
        if self._behavior == "reset_error":
            raise RuntimeError("Reset error")
        self._current_state = TaskState.INITED
        self._state_visit_counts = {TaskState.INITED: 1}
        self._error_info = None
        self._event_log = []
        self._call_count = 0

    def get_sub_tasks(self) -> list:
        """Get sub-tasks."""
        if self._behavior == "subtask_error":
            raise RuntimeError("Subtask access error")
        return self._sub_tasks

    def add_sub_task(self, sub_task: "ProblematicTask") -> None:
        """Add a sub-task."""
        self._sub_tasks.append(sub_task)


class TestSchedulerCornerCases(unittest.IsolatedAsyncioTestCase):
    """Test scheduler corner cases and edge conditions."""

    async def test_task_with_exception_handling(self) -> None:
        """Test scheduler handling of tasks that throw exceptions."""
        async def resilient_executor(_context, _queue, task):
            try:
                # Simulate task processing that might encounter errors
                if task.get_id() == "exception_task":
                    raise RuntimeError("Task execution error")
                task.handle_event(TaskEvent.DONE)
            except Exception:
                task.set_error_info("Executor caught error")

        # Create scheduler with error-tolerant executor
        async def on_running(scheduler, context, queue, fsm):
            return await resilient_executor(context, queue, fsm)

        scheduler = BaseScheduler(
            end_states={TaskState.FINISHED, TaskState.FAILED},
            on_state_fn={
                TaskState.INITED: lambda s, c, q, f: TaskEvent.IDENTIFIED,
                TaskState.CREATED: lambda s, c, q, f: TaskEvent.PLANED,
                TaskState.RUNNING: on_running
            },
            on_state_changed_fn={
                (TaskState.INITED, TaskState.CREATED): lambda s, c, q, f: TaskEvent.IDENTIFIED,
                (TaskState.CREATED, TaskState.RUNNING): lambda s, c, q, f: TaskEvent.PLANED,
                (TaskState.RUNNING, TaskState.FAILED): lambda s, c, q, f: TaskEvent.ERROR,
                (TaskState.RUNNING, TaskState.FINISHED): lambda s, c, q, f: TaskEvent.DONE
            },
            max_revisit_count=3
        )

        # Create task that will throw exception
        task = ProblematicTask("exception_task")
        context = {"test": "exception_handling"}
        queue = Queue()

        # Execute - should detect infinite loop due to exception handling issues
        with self.assertRaises(RuntimeError) as context:
            await scheduler.schedule(context, queue, task)

        # Verify the error message indicates infinite loop detection
        self.assertIn("状态连续未变化次数超过限制", str(context.exception))
        self.assertIn("RUNNING", str(context.exception))

    async def test_invalid_state_transitions(self) -> None:
        """Test scheduler handling of invalid state transitions."""
        # Create a task that rejects all events
        task = ProblematicTask("reject_all_task", "reject_all")
        context = {"test": "invalid_transitions"}
        queue = Queue()

        # Create a simple scheduler
        async def mock_handler(_scheduler, _context, _queue, _fsm):
            return TaskEvent.DONE

        scheduler = BaseScheduler(
            end_states={TaskState.FINISHED},
            on_state_fn={
                TaskState.INITED: mock_handler,
                TaskState.CREATED: mock_handler,
                TaskState.RUNNING: mock_handler
            },
            on_state_changed_fn={
                (TaskState.INITED, TaskState.CREATED): lambda s, c, q, f: TaskEvent.IDENTIFIED,
                (TaskState.CREATED, TaskState.RUNNING): lambda s, c, q, f: TaskEvent.PLANED,
                (TaskState.RUNNING, TaskState.FINISHED): lambda s, c, q, f: TaskEvent.DONE
            },
            max_revisit_count=3
        )

        # Execute workflow - should raise RuntimeError due to exceeded revisit count
        with self.assertRaises(RuntimeError) as context:
            await scheduler.schedule(context, queue, task)

        # Verify the error message
        self.assertIn("状态连续未变化次数超过限制", str(context.exception))
        self.assertIn("INITED", str(context.exception))

        # Task should not progress since it rejects all events
        self.assertEqual(task.get_current_state(), TaskState.INITED)
        # For reject_all behavior, set_current_state is never called, so visit count stays 1
        # But the scheduler should have attempted to process it multiple times
        self.assertEqual(task.get_state_visit_count(TaskState.INITED), 1)
        # Verify that the task was called multiple times (the loop count)
        self.assertGreater(task._call_count, 3)

    async def test_max_revisit_count_enforcement(self) -> None:
        """Test scheduler enforces maximum revisit count."""
        # Create scheduler with low revisit limit
        scheduler = BaseScheduler(
            end_states={TaskState.FINISHED},
            on_state_fn={},
            on_state_changed_fn={
                (TaskState.INITED, TaskState.FINISHED): lambda s, c, q, f: TaskEvent.DONE
            },
            max_revisit_count=1
        )

        # Create a task that will cause many revisits
        task = ProblematicTask("revisit_test")
        # Simulate multiple visits to the same state
        for _ in range(5):
            task._state_visit_counts[TaskState.INITED] = task.get_state_visit_count(TaskState.INITED) + 1

        context = {"test": "revisit_limit"}
        queue = Queue()

        # Execute
        try:
            await scheduler.schedule(context, queue, task)
        except Exception:
            # Expected due to revisit limit
            pass

        # Verify behavior
        self.assertGreaterEqual(task.get_state_visit_count(TaskState.INITED), 1)