"""Unit tests for LLM retry mechanism."""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch
from typing import Any

from tasking.llm.utils import timeout_retry_async
from tasking.model import Message, Role, TextBlock, CompletionConfig


class TestRetryMechanism:
    """Test cases for the timeout_retry_async decorator."""

    @pytest.fixture
    def mock_message(self):
        """Create a mock message for testing."""
        return Message(
            role=Role.USER,
            content=[TextBlock(text="Test message")]
        )

    @pytest.fixture
    def mock_config(self):
        """Create a mock completion config for testing."""
        return CompletionConfig(
            max_tokens=100,
            temperature=0.7
        )

    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self, mock_message, mock_config):
        """Test that successful calls are not retried."""
        call_count = 0

        @timeout_retry_async(max_retries=3, timeout=1.0)
        async def mock_function(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return "success"

        result = await mock_function(mock_message, mock_config)

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, mock_message, mock_config):
        """Test that timeouts trigger retries."""
        call_count = 0

        @timeout_retry_async(max_retries=3, timeout=0.1, base_delay=0.01)
        async def mock_function(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # Simulate timeout by sleeping longer than timeout
                await asyncio.sleep(0.2)
            return "success"

        result = await mock_function(mock_message, mock_config)

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_on_exception(self, mock_message, mock_config):
        """Test that exceptions trigger retries."""
        call_count = 0
        test_exception = ValueError("Test error")

        @timeout_retry_async(max_retries=3, timeout=1.0, base_delay=0.01)
        async def mock_function(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise test_exception
            return "success"

        result = await mock_function(mock_message, mock_config)

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, mock_message, mock_config):
        """Test that max retries are respected and final exception is raised."""
        call_count = 0
        test_exception = ValueError("Persistent error")

        @timeout_retry_async(max_retries=2, timeout=1.0, base_delay=0.01)
        async def mock_function(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise test_exception

        with pytest.raises(ValueError, match="Persistent error"):
            await mock_function(mock_message, mock_config)

        # Should be called max_retries + 1 times (initial + retries)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exponential_backoff(self, mock_message, mock_config):
        """Test that retry delays follow exponential backoff."""
        call_times = []

        @timeout_retry_async(max_retries=3, timeout=1.0, base_delay=0.01, max_delay=0.1)
        async def mock_function(*args, **kwargs):
            call_times.append(asyncio.get_event_loop().time())
            if len(call_times) < 3:
                raise ValueError("Test error")
            return "success"

        with patch('asyncio.sleep') as mock_sleep:
            await mock_function(mock_message, mock_config)

        # Verify sleep was called with increasing delays
        assert mock_sleep.call_count == 2  # 2 retries = 2 sleep calls

        # Check that sleep arguments follow exponential pattern
        sleep_args = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_args[0] >= 0.01  # Base delay
        assert sleep_args[1] >= sleep_args[0] * 2  # Exponential increase
        assert sleep_args[1] <= 0.1  # Max delay cap

    @pytest.mark.asyncio
    async def test_log_messages_on_retry(self, mock_message, mock_config):
        """Test that appropriate log messages are generated during retries."""
        call_count = 0

        @timeout_retry_async(max_retries=2, timeout=1.0, base_delay=0.01)
        async def mock_function(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError(f"Attempt {call_count} failed")
            return "success"

        with patch('tasking.llm.utils.logger') as mock_logger:
            result = await mock_function(mock_message, mock_config)

            assert result == "success"
            # Should log retry warnings
            warning_calls = [call for call in mock_logger.warning.call_args_list
                           if "retry" in str(call).lower() or "Timeout" in str(call)]
            assert len(warning_calls) >= 1

            # Check that any logging method was called
            total_log_calls = (mock_logger.info.call_args_list +
                             mock_logger.warning.call_args_list +
                             mock_logger.error.call_args_list)
            # The retry warning should be logged
            assert len([call for call in total_log_calls
                       if "attempt" in str(call).lower() or "retry" in str(call).lower()]) >= 1

    @pytest.mark.asyncio
    async def test_preserve_function_signature(self, mock_message, mock_config):
        """Test that the decorated function preserves its original signature."""
        @timeout_retry_async(max_retries=3, timeout=1.0)
        async def test_function(msg: Message, config: CompletionConfig, extra: str = "default"):
            return f"{msg.content[0].text}_{extra}"

        # Test with all arguments
        result = await test_function(mock_message, mock_config, "custom")
        assert result == "Test message_custom"

        # Test with default argument
        result = await test_function(mock_message, mock_config)
        assert result == "Test message_default"

    @pytest.mark.asyncio
    async def test_max_retries_with_different_exceptions(self, mock_message, mock_config):
        """Test that different types of exceptions are handled properly."""
        call_count = 0

        @timeout_retry_async(max_retries=2, timeout=1.0, base_delay=0.01)
        async def mock_function(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First error")
            if call_count == 2:
                raise RuntimeError("Second error")
            raise TypeError("Third error")

        with pytest.raises(TypeError, match="Third error"):
            await mock_function(mock_message, mock_config)

        # Should be called max_retries + 1 times
        assert call_count == 3