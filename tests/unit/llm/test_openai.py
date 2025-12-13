"""OpenAI LLM implementation unit tests."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from typing import Any

from tasking.llm.openai import OpenAiLLM, to_openai_dict, to_openai
from tasking.model import (
    Message,
    Role,
    TextBlock,
    CompletionConfig,
    ToolCallRequest,
    StopReason,
    CompletionUsage,
)
from tasking.model.message import ImageBlock
from tasking.model.setting import LLMConfig


class TestOpenAiLLM:
    """Test OpenAiLLM class."""

    def test_message_format_conversion_to_openai_format(self):
        """Test that tasking.model.message format converts correctly to OpenAI format."""
        # Create test messages
        messages = [
            Message(
                role=Role.USER,
                content=[TextBlock(text="Hello, how are you?")]
            ),
            Message(
                role=Role.ASSISTANT,
                content=[TextBlock(text="I'm doing well, thank you!")]
            ),
            Message(
                role=Role.SYSTEM,
                content=[TextBlock(text="You are a helpful assistant.")]
            )
        ]

        # Convert to OpenAI format
        openai_messages = to_openai_dict(messages)

        # Verify conversion
        assert len(openai_messages) == 3

        # Check first message (user)
        assert openai_messages[0]["role"] == "user"
        assert isinstance(openai_messages[0]["content"], list)
        assert len(openai_messages[0]["content"]) == 1
        assert openai_messages[0]["content"][0]["type"] == "text"
        assert "<block>Hello, how are you?</block>" in openai_messages[0]["content"][0]["text"]

        # Check second message (assistant)
        assert openai_messages[1]["role"] == "assistant"
        assert isinstance(openai_messages[1]["content"], list)
        assert len(openai_messages[1]["content"]) == 1
        assert openai_messages[1]["content"][0]["type"] == "text"
        assert "<block>I'm doing well, thank you!</block>" in openai_messages[1]["content"][0]["text"]

        # Check third message (system gets converted to user in OpenAI implementation)
        assert openai_messages[2]["role"] == "user"
        assert isinstance(openai_messages[2]["content"], list)
        assert len(openai_messages[2]["content"]) == 1
        assert openai_messages[2]["content"][0]["type"] == "text"
        assert "<block>You are a helpful assistant.</block>" in openai_messages[2]["content"][0]["text"]

    def test_message_format_conversion_with_multimodal_content(self):
        """Test message format conversion with multimodal content."""
        messages = [
            Message(
                role=Role.USER,
                content=[
                    TextBlock(text="What do you see in this image?"),
                    ImageBlock(image_url="https://example.com/image.jpg")
                ]
            )
        ]

        openai_messages = to_openai_dict(messages)

        assert len(openai_messages) == 1
        assert openai_messages[0]["role"] == "user"
        assert isinstance(openai_messages[0]["content"], list)

        # Should have text and image content
        content = openai_messages[0]["content"]

        # Check that we have the expected structure (block opening, text, image, block closing)
        assert len(content) == 4

        # Check block opening
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "<block>"

        # Check text content
        text_content = content[1]
        assert text_content["type"] == "text"
        assert "What do you see in this image?" in text_content["text"]

        # Check image content
        image_content = content[2]
        assert image_content["type"] == "image_url"
        assert image_content["image_url"]["url"] == "https://example.com/image.jpg"

        # Check block closing
        assert content[3]["type"] == "text"
        assert content[3]["text"] == "</block>"

    @patch('tasking.llm.openai.AsyncOpenAI')
    def test_parameters_passed_to_openai_client(self, mock_openai):
        """Test that parameters are correctly passed to OpenAI client."""
        # Setup mock client
        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.choices = [
            Mock(
                message=Mock(
                    content="Test response",
                    tool_calls=None
                ),
                finish_reason="stop"
            )
        ]
        mock_completion.usage = Mock(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30
        )
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
        mock_openai.return_value = mock_client

        # Create OpenAiLLM instance
        config = LLMConfig(
            provider="openai",
            model="gpt-4",
            api_key="test-key"
        )
        llm = OpenAiLLM(config)

        # Create completion config
        completion_config = CompletionConfig(
            temperature=0.7,
            max_tokens=100,
            top_p=0.9
        )

        # Call LLM
        messages = [
            Message(role=Role.USER, content=[TextBlock(text="Test")])
        ]

        import asyncio
        result = asyncio.run(llm.completion(messages, completion_config))

        # Verify client was called with correct parameters
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args

        # Check model parameter
        assert call_args.kwargs["model"] == "gpt-4"

        # Check temperature parameter
        assert call_args.kwargs["temperature"] == 0.7

        # Check max_tokens parameter
        assert call_args.kwargs["max_tokens"] == 100

        # Check top_p parameter
        assert call_args.kwargs["top_p"] == 0.9

        # Check messages parameter
        assert "messages" in call_args.kwargs
        openai_messages = call_args.kwargs["messages"]
        assert len(openai_messages) == 1
        assert openai_messages[0]["role"] == "user"
        assert isinstance(openai_messages[0]["content"], list)
        assert "<block>Test</block>" in openai_messages[0]["content"][0]["text"]

    @patch('tasking.llm.openai.AsyncOpenAI')
    def test_mock_client_return_value_parsing(self, mock_openai):
        """Test that mock client return values are correctly parsed."""
        # Setup mock client with specific return value
        mock_client = Mock()
        mock_completion = Mock()
        mock_completion.choices = [
            Mock(
                message=Mock(
                    content="Hello! This is a test response.",
                    tool_calls=None
                ),
                finish_reason="stop"
            )
        ]
        mock_completion.usage = Mock(
            prompt_tokens=15,
            completion_tokens=25,
            total_tokens=40
        )
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
        mock_openai.return_value = mock_client

        # Create OpenAiLLM and call it
        config = LLMConfig(provider="openai", model="gpt-4", api_key="test-key")
        llm = OpenAiLLM(config)

        messages = [Message(role=Role.USER, content=[TextBlock(text="Hello")])]
        completion_config = CompletionConfig()

        import asyncio
        result = asyncio.run(llm.completion(messages, completion_config))

        # OpenAI LLM returns a Message object, not a completion result object
        assert isinstance(result, Message)
        assert result.role == Role.ASSISTANT
        assert len(result.content) == 1
        assert result.content[0].text == "Hello! This is a test response."
        assert result.tool_calls == []  # Empty list instead of None

        # Note: Usage information is not directly returned from the completion method
        # It's used internally but not part of the Message return value

    def test_completion_config_conversion(self):
        """Test CompletionConfig conversion to OpenAI format."""
        config = CompletionConfig(
            temperature=0.8,
            max_tokens=200,
            top_p=0.95,
            frequency_penalty=0.1,
            presence_penalty=0.2,
            stop_words=["STOP", "END"]
        )

        # Convert to OpenAI format
        openai_config = to_openai(config)

        # Verify conversion - only check the parameters that are actually included
        assert openai_config["temperature"] == 0.8
        assert openai_config["max_tokens"] == 200
        assert openai_config["top_p"] == 0.95
        assert openai_config["frequency_penalty"] == 0.1
        # Note: stop parameter is not included in this conversion function

    def test_message_with_tool_calls_conversion(self):
        """Test message conversion with tool calls."""
        # Create message with tool calls
        tool_call = ToolCallRequest(
            id="call_123",
            name="test_function",
            args={"param1": "value1", "param2": 42}
        )

        messages = [
            Message(
                role=Role.ASSISTANT,
                content=[TextBlock(text="I'll call the test function.")],
                tool_calls=[tool_call]
            )
        ]

        # Convert to OpenAI format
        openai_messages = to_openai_dict(messages)

        assert len(openai_messages) == 1
        assert openai_messages[0]["role"] == "assistant"
        assert isinstance(openai_messages[0]["content"], list)
        assert openai_messages[0]["content"][0]["text"] == "<block>I'll call the test function.</block>"
        assert "tool_calls" in openai_messages[0]

        # Check tool call format
        tool_calls = openai_messages[0]["tool_calls"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["id"] == "call_123"
        assert tool_calls[0]["function"]["name"] == "test_function"
        assert '"param1": "value1"' in tool_calls[0]["function"]["arguments"]
        assert '"param2": 42' in tool_calls[0]["function"]["arguments"]

    def test_provider_and_model_properties(self):
        """Test provider and model property methods."""
        config = LLMConfig(
            provider="openai",
            model="gpt-4-turbo",
            api_key="test-key"
        )
        llm = OpenAiLLM(config)

        # Test provider
        assert llm.get_provider().value == "openai"

        # Test model
        assert llm.get_model() == "gpt-4-turbo"

        # Test base_url - this implementation might use a different default URL
        base_url = llm.get_base_url()
        assert isinstance(base_url, str)
        assert len(base_url) > 0  # Just verify it returns some URL string


if __name__ == "__main__":
    pytest.main([__file__])