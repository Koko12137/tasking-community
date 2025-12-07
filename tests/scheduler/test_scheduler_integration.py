"""Integration tests for scheduler workflows."""

import asyncio
import unittest
from typing import Optional, List
from unittest.mock import AsyncMock
from queue import Queue

from src.core.scheduler.base import BaseScheduler
from src.core.state_machine.task.const import TaskEvent, TaskState
from src.core.state_machine.task import ITask
from src.model import Message
from src.model.queue import IQueue


class SimpleTask:
    """Simple task implementation for integration testing."""

    def __init__(self, task_id: str = "test_task"):
        self._task_id = task_id
        self._current_state = TaskState.INITED
        self._data = {"task_id": task_id}
        self._state_visit_counts = {TaskState.INITED: 1}
        self._error_info = None
        self._event_log = []

    def get_id(self) -> str:
        return self._task_id

    def get_current_state(self) -> TaskState:
        return self._current_state

    def set_current_state(self, state: TaskState) -> None:
        self._current_state = state
        self._state_visit_counts[state] = self._state_visit_counts.get(state, 0) + 1

    async def handle_event(self, event: TaskEvent) -> None:
        self._event_log.append((self._current_state, event))

        # Simple state machine
        if self._current_state == TaskState.INITED and event == TaskEvent.IDENTIFIED:
            self.set_current_state(TaskState.CREATED)
        elif self._current_state == TaskState.CREATED and event == TaskEvent.PLANED:
            self.set_current_state(TaskState.RUNNING)
        elif self._current_state == TaskState.RUNNING and event == TaskEvent.DONE:
            self.set_current_state(TaskState.FINISHED)
        elif self._current_state == TaskState.RUNNING and event == TaskEvent.ERROR:
            self.set_current_state(TaskState.FAILED)

    def get_state_visit_count(self, state: TaskState) -> int:
        return self._state_visit_counts.get(state, 0)

    def get_max_revisit_limit(self) -> int:
        return 3

    def is_error(self) -> bool:
        return self._current_state == TaskState.FAILED

    def get_error_info(self) -> Optional[str]:
        return self._error_info

    def set_error(self, error_info: any) -> None:
        self._error_info = str(error_info) if error_info else None
        self._current_state = TaskState.FAILED

    @property
    def data(self) -> dict:
        return self._data


class TestSimpleSchedulerIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for simple scheduler workflows."""

    async def test_basic_workflow_execution(self) -> None:
        """Test a complete workflow from start to finish."""
        # Create a simple scheduler
        async def on_inited(scheduler, context, queue, fsm):
            await fsm.handle_event(TaskEvent.IDENTIFIED)
            return TaskEvent.IDENTIFIED

        async def on_created(scheduler, context, queue, fsm):
            await fsm.handle_event(TaskEvent.PLANED)
            return TaskEvent.PLANED

        async def on_running(scheduler, context, queue, fsm):
            await fsm.handle_event(TaskEvent.DONE)
            return TaskEvent.DONE

        scheduler = BaseScheduler(
            end_states={TaskState.FINISHED},
            on_state_fn={
                TaskState.INITED: on_inited,
                TaskState.CREATED: on_created,
                TaskState.RUNNING: on_running
            },
            on_state_changed_fn={
                (TaskState.INITED, TaskState.CREATED): lambda s, c, q, f: TaskEvent.IDENTIFIED,
                (TaskState.CREATED, TaskState.RUNNING): lambda s, c, q, f: TaskEvent.PLANED,
                (TaskState.RUNNING, TaskState.FINISHED): lambda s, c, q, f: TaskEvent.DONE
            },
            max_revisit_count=3
        )

        # Create and configure task
        task = SimpleTask("integration_test_task")
        context = {"test": "integration"}
        queue = Queue()

        # Execute workflow
        await scheduler.schedule(context, queue, task)

        # Verify complete workflow
        self.assertEqual(task.get_current_state(), TaskState.FINISHED)
        self.assertEqual(task.get_state_visit_count(TaskState.INITED), 1)
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
            return TaskEvent.ERROR

        async def on_inited(scheduler, context, queue, fsm):
            await fsm.handle_event(TaskEvent.IDENTIFIED)
            return TaskEvent.IDENTIFIED

        async def on_created(scheduler, context, queue, fsm):
            await fsm.handle_event(TaskEvent.PLANED)
            return TaskEvent.PLANED

        scheduler = BaseScheduler(
            end_states={TaskState.FAILED},
            on_state_fn={
                TaskState.INITED: on_inited,
                TaskState.CREATED: on_created,
                TaskState.RUNNING: error_handler
            },
            on_state_changed_fn={
                (TaskState.INITED, TaskState.CREATED): lambda s, c, q, f: TaskEvent.IDENTIFIED,
                (TaskState.CREATED, TaskState.RUNNING): lambda s, c, q, f: TaskEvent.PLANED,
                (TaskState.RUNNING, TaskState.FAILED): lambda s, c, q, f: TaskEvent.ERROR
            },
            max_revisit_count=1
        )

        task = SimpleTask("error_test_task")
        context = {"should_fail": True}
        queue = Queue()

        # Execute workflow
        await scheduler.schedule(context, queue, task)

        # Verify error handling
        self.assertEqual(task.get_current_state(), TaskState.FAILED)
        self.assertTrue(task.get_error_info())
        self.assertEqual(task.get_error_info(), "Test error")