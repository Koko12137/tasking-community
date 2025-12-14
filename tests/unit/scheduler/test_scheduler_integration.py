"""Integration tests for scheduler workflows."""

import asyncio
import unittest
from typing import Optional, List
from unittest.mock import AsyncMock
from queue import Queue

from tasking.core.scheduler.base import BaseScheduler
from tasking.core.state_machine.task.const import TaskEvent, TaskState
from tasking.core.state_machine.task import ITask
from tasking.model import Message
from tasking.model.queue import IQueue


class SimpleTask:
    """Simple task implementation for integration testing."""

    def __init__(self, task_id: str = "test_task", valid_states: set[TaskState] | None = None):
        self._task_id = task_id
        self._current_state = TaskState.CREATED
        self._data = {"task_id": task_id}
        self._state_visit_counts = {TaskState.CREATED: 1}
        self._error_info = None
        self._event_log = []
        self._max_revisit_count = 0
        # Default valid states
        self._valid_states = valid_states or {TaskState.CREATED, TaskState.RUNNING, TaskState.FINISHED, TaskState.CANCELED}

    def get_id(self) -> str:
        return self._task_id

    def get_valid_states(self) -> set[TaskState]:
        """Get valid states."""
        return self._valid_states.copy()

    def get_current_state(self) -> TaskState:
        return self._current_state

    def set_current_state(self, state: TaskState) -> None:
        self._current_state = state
        self._state_visit_counts[state] = self._state_visit_counts.get(state, 0) + 1

    def set_max_revisit_count(self, count: int) -> None:
        self._max_revisit_count = count

    async def handle_event(self, event: TaskEvent) -> None:
        self._event_log.append((self._current_state, event))

        # Simple state machine
        if self._current_state == TaskState.CREATED and event == TaskEvent.INIT:
            self.set_current_state(TaskState.RUNNING)
        elif self._current_state == TaskState.RUNNING and event == TaskEvent.PLANED:
            self.set_current_state(TaskState.RUNNING)
        elif self._current_state == TaskState.RUNNING and event == TaskEvent.DONE:
            self.set_current_state(TaskState.FINISHED)
        elif self._current_state == TaskState.RUNNING and event == TaskEvent.CANCEL:
            self.set_current_state(TaskState.CANCELED)

    def get_state_visit_count(self, state: TaskState) -> int:
        return self._state_visit_counts.get(state, 0)

    def get_max_revisit_limit(self) -> int:
        return 3

    def is_error(self) -> bool:
        return self._current_state == TaskState.CANCELED

    def get_error_info(self) -> Optional[str]:
        return self._error_info

    def set_error(self, error_info: any) -> None:
        self._error_info = str(error_info) if error_info else None
        self._current_state = TaskState.CANCELED

    @property
    def data(self) -> dict:
        return self._data


class TestSimpleSchedulerIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for simple scheduler workflows."""

    async def test_basic_workflow_execution(self) -> None:
        """Test a complete workflow from start to finish."""
        # Create a simple scheduler
        async def on_created(scheduler, context, queue, fsm):
            await fsm.handle_event(TaskEvent.INIT)
            return TaskEvent.INIT

        async def on_running(scheduler, context, queue, fsm):
            await fsm.handle_event(TaskEvent.DONE)
            return TaskEvent.DONE

        scheduler = BaseScheduler(
            end_states={TaskState.FINISHED},
            on_state_fn={
                TaskState.CREATED: on_created,
                TaskState.RUNNING: on_running
            },
            on_state_changed_fn={
                (TaskState.CREATED, TaskState.RUNNING): lambda s, c, q, f: TaskEvent.INIT,
                (TaskState.RUNNING, TaskState.FINISHED): lambda s, c, q, f: TaskEvent.DONE
            },
            max_revisit_count=3
        )

        # Create and configure task
        # Task valid states must match scheduler configuration
        task = SimpleTask("integration_test_task", valid_states={TaskState.CREATED, TaskState.RUNNING, TaskState.FINISHED})
        context = {"test": "integration"}
        queue = Queue()

        # Execute workflow
        await scheduler.schedule(context, queue, task)

        # Verify complete workflow
        self.assertEqual(task.get_current_state(), TaskState.FINISHED)
        self.assertEqual(task.get_state_visit_count(TaskState.CREATED), 1)
        self.assertEqual(task.get_state_visit_count(TaskState.CREATED), 1)
        self.assertEqual(task.get_state_visit_count(TaskState.RUNNING), 1)
        self.assertEqual(task.get_state_visit_count(TaskState.FINISHED), 1)


class TestSchedulerErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Test scheduler error handling capabilities."""

    async def test_task_failure_handling(self) -> None:
        """Test scheduler handling of task failures."""
        # Create a scheduler with error handling
        async def error_handler(scheduler, context, queue, fsm):
            fsm.set_error("Test error")
            return TaskEvent.CANCEL

        async def on_created(scheduler, context, queue, fsm):
            await fsm.handle_event(TaskEvent.INIT)
            return TaskEvent.INIT

        scheduler = BaseScheduler(
            end_states={TaskState.CANCELED},
            on_state_fn={
                TaskState.CREATED: on_created,
                TaskState.RUNNING: error_handler
            },
            on_state_changed_fn={
                (TaskState.CREATED, TaskState.RUNNING): lambda s, c, q, f: TaskEvent.INIT,
                (TaskState.RUNNING, TaskState.CANCELED): lambda s, c, q, f: TaskEvent.CANCEL
            },
            max_revisit_count=1
        )

        # Task valid states must match scheduler configuration
        task = SimpleTask("error_test_task", valid_states={TaskState.CREATED, TaskState.RUNNING, TaskState.CANCELED})
        context = {"should_fail": True}
        queue = Queue()

        # Execute workflow
        await scheduler.schedule(context, queue, task)

        # Verify error handling
        self.assertEqual(task.get_current_state(), TaskState.CANCELED)
        self.assertTrue(task.get_error_info())
        self.assertEqual(task.get_error_info(), "Test error")