"""
Unit tests for middleware step counter components.
"""

import pytest
from unittest.mock import Mock, patch
from typing import Any

from tasking.core.middleware.step_counter import (
    IStepCounter,
    BaseStepCounter,
    MaxStepCounter,
    TokenStepCounter,
    MaxStepsError
)
from tasking.model import CompletionUsage


class TestIStepCounter:
    """Test IStepCounter interface compliance."""

    def test_istep_counter_is_abstract(self) -> None:
        """Test that IStepCounter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            IStepCounter()

    def test_istep_counter_method_signatures(self) -> None:
        """Test that IStepCounter defines required methods."""
        # Check that abstract methods are defined
        abstract_methods = IStepCounter.__abstractmethods__
        expected_methods = {
            "get_uid", "get_limit", "get_used", "use_steps",
            "is_exhausted", "reset", "peek"
        }

        assert abstract_methods == expected_methods


class TestMaxStepCounter:
    """Test MaxStepCounter implementation."""

    def test_max_step_counter_initialization(self) -> None:
        """Test MaxStepCounter initialization."""
        counter = MaxStepCounter(limit=100)

        assert counter.get_limit() == 100
        assert counter.get_used() == 0
        assert not counter.is_exhausted()
        assert counter.peek() == 0

    def test_max_step_counter_use_steps(self) -> None:
        """Test using steps in MaxStepCounter."""
        counter = MaxStepCounter(limit=100)

        # Use some steps
        result = counter.use_steps(25)
        assert result == 25
        assert counter.get_used() == 25
        assert not counter.is_exhausted()
        assert counter.peek() == 25

        # Use more steps
        result = counter.use_steps(50)
        assert result == 50
        assert counter.get_used() == 75
        assert not counter.is_exhausted()

    def test_max_step_counter_exhaustion(self) -> None:
        """Test MaxStepCounter exhaustion behavior."""
        counter = MaxStepCounter(limit=100)

        # Use exactly the limit
        result = counter.use_steps(100)
        assert result == 100
        assert counter.get_used() == 100
        assert counter.is_exhausted()

        # Try to use more steps after exhaustion
        with pytest.raises(MaxStepsError):
            counter.use_steps(10)

    def test_max_step_counter_over_limit(self) -> None:
        """Test MaxStepCounter when trying to use more than limit."""
        counter = MaxStepCounter(limit=50)

        with pytest.raises(MaxStepsError):
            counter.use_steps(75)

        # Counter should still be at 0
        assert counter.get_used() == 0
        assert not counter.is_exhausted()

    def test_max_step_counter_reset(self) -> None:
        """Test MaxStepCounter reset functionality."""
        counter = MaxStepCounter(limit=100)

        # Use some steps
        counter.use_steps(50)
        assert counter.get_used() == 50
        assert counter.peek() == 50

        # Reset
        counter.reset()
        assert counter.get_used() == 0
        assert not counter.is_exhausted()
        assert counter.peek() == 0

    def test_max_step_counter_zero_steps(self) -> None:
        """Test MaxStepCounter with zero steps."""
        counter = MaxStepCounter(limit=100)

        result = counter.use_steps(0)
        assert result == 0
        assert counter.get_used() == 0

    def test_max_step_counter_negative_steps(self) -> None:
        """Test MaxStepCounter with negative steps."""
        counter = MaxStepCounter(limit=100)

        with pytest.raises(ValueError):
            counter.use_steps(-10)

    def test_max_step_counter_uid(self) -> None:
        """Test MaxStepCounter UID generation."""
        counter1 = MaxStepCounter(limit=100)
        counter2 = MaxStepCounter(limit=100)

        # UIDs should be unique
        uid1 = counter1.get_uid()
        uid2 = counter2.get_uid()

        assert uid1 != uid2
        assert isinstance(uid1, str)
        assert isinstance(uid2, str)
        assert len(uid1) > 0
        assert len(uid2) > 0


class TestTokenStepCounter:
    """Test TokenStepCounter implementation."""

    def test_token_step_counter_initialization(self) -> None:
        """Test TokenStepCounter initialization."""
        counter = TokenStepCounter(limit=1000)

        assert counter.get_limit() == 1000
        assert counter.get_used() == 0
        assert not counter.is_exhausted()

    def test_token_step_counter_use_completion_usage(self) -> None:
        """Test using completion usage in TokenStepCounter."""
        counter = TokenStepCounter(limit=1000)

        # Create a mock completion usage
        usage = CompletionUsage(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30
        )

        result = counter.use_steps(usage)
        assert result == 30
        assert counter.get_used() == 30
        assert counter.peek() == 30

    @patch('src.core.middleware.step_counter.logger')
    def test_token_step_counter_use_int_with_warning(self, mock_logger: Mock) -> None:
        """Test TokenStepCounter with integer usage (should log warning)."""
        counter = TokenStepCounter(limit=1000)

        # Pass an integer instead of CompletionUsage
        result = counter.use_steps(50)  # type: ignore

        assert result == 50
        assert counter.get_used() == 50
        # Should log a warning about expecting CompletionUsage
        mock_logger.warning.assert_called()

    def test_token_step_counter_exhaustion(self) -> None:
        """Test TokenStepCounter exhaustion behavior."""
        counter = TokenStepCounter(limit=100)

        # Use exactly the limit
        usage = CompletionUsage(
            prompt_tokens=30,
            completion_tokens=70,
            total_tokens=100
        )
        result = counter.use_steps(usage)
        assert result == 100
        assert counter.is_exhausted()

        # Try to use more tokens after exhaustion
        with pytest.raises(MaxStepsError):
            counter.use_steps(CompletionUsage(total_tokens=10))

    def test_token_step_counter_partial_usage(self) -> None:
        """Test TokenStepCounter with partial token usage that exceeds limit."""
        counter = TokenStepCounter(limit=100)

        # Try to use more than limit
        usage = CompletionUsage(
            prompt_tokens=50,
            completion_tokens=100,
            total_tokens=150
        )

        with pytest.raises(MaxStepsError):
            counter.use_steps(usage)

        # Counter should remain unchanged
        assert counter.get_used() == 0


class TestMaxStepsError:
    """Test MaxStepsError exception."""

    def test_max_steps_error_inheritance(self) -> None:
        """Test that MaxStepsError is an Exception."""
        error = MaxStepsError("Test error")
        assert isinstance(error, Exception)

    def test_max_steps_error_message(self) -> None:
        """Test MaxStepsError message."""
        message = "Step limit exceeded"
        error = MaxStepsError(message)
        assert str(error) == message

    def test_max_steps_error_with_context(self) -> None:
        """Test MaxStepsError with detailed context."""
        used = 100
        limit = 50
        error = MaxStepsError(f"Used {used} steps, limit is {limit}")

        assert str(error) == f"Used {used} steps, limit is {limit}"
        assert "100" in str(error)
        assert "50" in str(error)


class TestBaseStepCounter:
    """Test BaseStepCounter if it exists."""

    def test_base_step_counter_exists(self) -> None:
        """Test that BaseStepCounter is available from middleware."""
        # This test ensures the import is working
        from tasking.core.middleware.step_counter import BaseStepCounter
        assert BaseStepCounter is not None