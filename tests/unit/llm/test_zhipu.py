"""Zhipu LLM implementation unit tests."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Any

from tasking.llm.zhipu import ZhipuLLM, ZhipuEmbeddingLLM, to_zhipu_messages
from tasking.model import (
    Message,
    Role,
    TextBlock,
    CompletionConfig,
    ToolCallRequest,
    StopReason,
    CompletionUsage,
    MultimodalContent,
)
from tasking.model.message import ImageBlock
from tasking.model.setting import LLMConfig


class TestZhipuLLM:
    """Test ZhipuLLM class."""

    def test_message_format_conversion_to_zhipu_format(self):
        """Test that tasking.model.message format converts correctly to Zhipu format."""
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

        # Convert to Zhipu format
        zhipu_messages = to_zhipu_messages(messages)

        # Verify conversion
        assert len(zhipu_messages) == 3

        # Check first message (user)
        assert zhipu_messages[0]["role"] == "user"
        # Content should be string with <block> tags
        assert "<block>Hello, how are you?</block>" in zhipu_messages[0]["content"]

        # Check second message (assistant)
        assert zhipu_messages[1]["role"] == "assistant"
        assert "<block>I'm doing well, thank you!</block>" in zhipu_messages[1]["content"]

        # Check third message (system - may be converted to user in Zhipu)
        # Zhipu may convert system to user role
        assert zhipu_messages[2]["role"] in ["system", "user"]
        assert "<block>You are a helpful assistant.</block>" in zhipu_messages[2]["content"]

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

        zhipu_messages = to_zhipu_messages(messages)

        assert len(zhipu_messages) == 1
        assert zhipu_messages[0]["role"] == "user"
        assert isinstance(zhipu_messages[0]["content"], list)

        # Should have text and image content plus block tags
        content = zhipu_messages[0]["content"]

        # Check that we have the expected structure
        assert len(content) >= 3  # At least <block>, text, </block>

        # Extract text blocks
        text_blocks = [block for block in content if block["type"] == "text"]
        image_blocks = [block for block in content if block["type"] == "image_url"]

        # Should have text content
        assert any("What do you see in this image?" in block["text"] for block in text_blocks)

        # Should have image content
        assert len(image_blocks) == 1
        assert image_blocks[0]["image_url"]["url"] == "https://example.com/image.jpg"

    @patch('tasking.llm.zhipu.ZhipuAI')
    def test_parameters_passed_to_zhipu_client(self, mock_zhipu_ai):
        """Test that parameters are correctly passed to Zhipu client."""
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
        mock_client.chat.completions.create = Mock(return_value=mock_completion)
        mock_zhipu_ai.return_value = mock_client

        # Create ZhipuLLM instance
        config = LLMConfig(
            provider="zhipu",
            model="glm-4",
            api_key="test-key"
        )
        llm = ZhipuLLM(config)

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
        result = asyncio.run(llm.completion(messages, None, None, completion_config))

        # Verify client was called with correct parameters
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args

        # Check model parameter
        assert call_args.kwargs["model"] == "glm-4"

        # Check temperature parameter
        assert call_args.kwargs["temperature"] == 0.7

        # Check max_tokens parameter
        assert call_args.kwargs["max_tokens"] == 100

        # Check top_p parameter
        assert call_args.kwargs["top_p"] == 0.9

        # Check messages parameter
        assert "messages" in call_args.kwargs
        zhipu_messages = call_args.kwargs["messages"]
        assert len(zhipu_messages) == 1
        assert zhipu_messages[0]["role"] == "user"
        assert zhipu_messages[0]["content"] == "<block>Test</block>"

    @patch('tasking.llm.zhipu.ZhipuAI')
    def test_mock_client_return_value_parsing(self, mock_zhipu_ai):
        """Test that mock client return values are correctly parsed."""
        # Setup mock client with specific return value
        mock_client = Mock()

        # Import ZhipuCompletion to make mock pass isinstance check
        from zai.types.chat.chat_completion import Completion as ZhipuCompletion

        mock_completion = Mock(spec=ZhipuCompletion)  # Make it pass isinstance check
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
        # Mock the sync method since ZhipuLLM uses asyncify
        mock_client.chat.completions.create = Mock(return_value=mock_completion)
        mock_zhipu_ai.return_value = mock_client

        # Create ZhipuLLM and call it
        config = LLMConfig(provider="zhipu", model="glm-4", api_key="test-key")
        llm = ZhipuLLM(config)

        messages = [Message(role=Role.USER, content=[TextBlock(text="Hello")])]
        completion_config = CompletionConfig()

        import asyncio
        result = asyncio.run(llm.completion(messages, None, None, completion_config))

        # Verify result parsing - result should be a Message object
        assert isinstance(result, Message)
        assert result.role == Role.ASSISTANT
        assert len(result.content) == 1
        assert result.content[0].text == "Hello! This is a test response."
        assert result.stop_reason == StopReason.STOP
        assert result.tool_calls == []  # Empty list for no tool calls

        # Verify usage parsing
        assert result.usage.prompt_tokens == 15
        assert result.usage.completion_tokens == 25
        assert result.usage.total_tokens == 40


class TestZhipuEmbeddingLLM:
    """Test ZhipuEmbeddingLLM class."""

    @patch('tasking.llm.zhipu.asyncio.to_thread')
    @patch('tasking.llm.zhipu.ZhipuAI')
    def test_embedding_parameters_passed_to_client(self, mock_zhipu_ai, mock_to_thread):
        """Test that embedding parameters are correctly passed to Zhipu client."""
        # Setup mock embedding response that to_thread will return
        mock_embedding_response = Mock()
        # Create proper mock structure for response.data[0].embedding access
        mock_data_item = Mock()
        mock_data_item.embedding = [0.1, 0.2, 0.3, 0.4]
        mock_embedding_response.data = [mock_data_item]
        mock_to_thread.return_value = mock_embedding_response

        # Setup mock client
        mock_client = Mock()
        mock_zhipu_ai.return_value = mock_client

        # Create ZhipuEmbeddingLLM instance
        config = LLMConfig(
            provider="zhipu",
            model="embedding-2",
            api_key="test-key"
        )
        embedding_llm = ZhipuEmbeddingLLM(config)

        # Call embedding with single TextBlock to simplify testing
        contents = [TextBlock(text="Hello world")]

        import asyncio
        result = asyncio.run(embedding_llm.embed(contents, dimensions=1536))

        # Verify asyncio.to_thread was called with correct parameters
        mock_to_thread.assert_called_once()
        call_args = mock_to_thread.call_args

        # Check that the client method and parameters were passed correctly
        assert call_args.args[0] == mock_client.embeddings.create  # First arg should be the client method
        assert call_args.kwargs["model"] == "embedding-2"
        assert call_args.kwargs["input"] == "Hello world"

        # Verify result (embed method returns the embedding vector)
        assert len(result) > 0
        assert isinstance(result[0], (float, int))
        assert result == [0.1, 0.2, 0.3, 0.4]  # Should match our mock setup

    @patch('tasking.llm.zhipu.asyncio.to_thread')
    @patch('tasking.llm.zhipu.ZhipuAI')
    def test_embedding_mock_client_return_value(self, mock_zhipu_ai, mock_to_thread):
        """Test that embedding mock client return values are correctly parsed."""
        # Setup mock embedding response that to_thread will return
        mock_embedding_response = Mock()
        # Create proper mock structure for response.data[0].embedding access
        mock_data_item = Mock()
        mock_data_item.embedding = [0.9, 0.8, 0.7, 0.6, 0.5]
        mock_embedding_response.data = [mock_data_item]
        mock_to_thread.return_value = mock_embedding_response

        # Setup mock client
        mock_client = Mock()
        mock_zhipu_ai.return_value = mock_client

        # Create and test
        config = LLMConfig(provider="zhipu", model="embedding-2", api_key="test-key")
        embedding_llm = ZhipuEmbeddingLLM(config)

        import asyncio
        result = asyncio.run(embedding_llm.embed([TextBlock(text="Test text")], dimensions=1536))

        # Verify embedding result
        assert len(result) > 0
        assert isinstance(result[0], (float, int))


if __name__ == "__main__":
    pytest.main([__file__])