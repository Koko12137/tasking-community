"""Tests for scheduler builder functions."""

import unittest
from unittest.mock import MagicMock

from tasking.core.scheduler import build_base_scheduler
from tasking.core.agent import IAgent
from tasking.core.state_machine.task.const import TaskState


class TestSimpleSchedulerBuilder(unittest.IsolatedAsyncioTestCase):
    """Test simple scheduler builder function."""

    async def test_build_base_scheduler_creation(self) -> None:
        """Test build_base_scheduler creates scheduler instance."""
        # Create mock executor agent
        mock_executor = MagicMock(spec=IAgent)
        
        # Build scheduler
        scheduler = build_base_scheduler(
            executor=mock_executor,
            orchestrator=None,
            max_error_retry=3
        )
        
        # Verify scheduler is created
        self.assertIsNotNone(scheduler)
        self.assertEqual(scheduler.get_max_revisit_count(), 3)
        self.assertIn(TaskState.FINISHED, scheduler.get_end_states())
        self.assertIn(TaskState.CANCELED, scheduler.get_end_states())

    async def test_build_base_scheduler_with_orchestrator(self) -> None:
        """Test build_base_scheduler with orchestrator."""
        # Create mock agents
        mock_executor = MagicMock(spec=IAgent)
        mock_orchestrator = MagicMock(spec=IAgent)
        
        # Build scheduler
        scheduler = build_base_scheduler(
            executor=mock_executor,
            orchestrator=mock_orchestrator,
            max_error_retry=5
        )
        
        # Verify scheduler is created with orchestrator
        self.assertIsNotNone(scheduler)
        self.assertEqual(scheduler.get_max_revisit_count(), 5)

    async def test_build_base_scheduler_default_parameters(self) -> None:
        """Test build_base_scheduler with default parameters."""
        mock_executor = MagicMock(spec=IAgent)
        
        # Build scheduler with default max_error_retry
        scheduler = build_base_scheduler(
            executor=mock_executor
        )
        
        # Verify default max_error_retry is 3
        self.assertEqual(scheduler.get_max_revisit_count(), 3)


class TestSchedulerBuilderErrors(unittest.TestCase):
    """Test scheduler builder error handling."""

    def test_build_base_scheduler_requires_executor(self) -> None:
        """Test that build_base_scheduler requires executor parameter."""
        # This should raise TypeError if executor is not provided
        with self.assertRaises(TypeError):
            # Missing required executor parameter
            build_base_scheduler()  # type: ignore