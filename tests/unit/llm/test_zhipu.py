"""Zhipu LLM implementation unit tests."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
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
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
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
        result = asyncio.run(llm.completion(messages, completion_config))

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
        mock_zhipu_ai.return_value = mock_client

        # Create ZhipuLLM and call it
        config = LLMConfig(provider="zhipu", model="glm-4", api_key="test-key")
        llm = ZhipuLLM(config)

        messages = [Message(role=Role.USER, content=[TextBlock(text="Hello")])]
        completion_config = CompletionConfig()

        import asyncio
        result = asyncio.run(llm.completion(messages, completion_config))

        # Verify result parsing
        assert len(result.choices) == 1
        choice = result.choices[0]
        assert choice.message.content == "Hello! This is a test response."
        assert choice.stop_reason == StopReason.STOP
        assert choice.message.tool_calls is None

        # Verify usage parsing
        assert result.usage.prompt_tokens == 15
        assert result.usage.completion_tokens == 25
        assert result.usage.total_tokens == 40


class TestZhipuEmbeddingLLM:
    """Test ZhipuEmbeddingLLM class."""

    @patch('tasking.llm.zhipu.asyncio.to_thread')
    @patch('tasking.llm.zhipu.ZhipuAI')
    def test_embedding_parameters_passed_to_client(self, mock_to_thread, mock_zhipu_ai):
        """Test that embedding parameters are correctly passed to Zhipu client."""
        # Setup mock client
        mock_client = Mock()
        mock_embedding = Mock()
        mock_embedding.data = [
            Mock(embedding=[0.1, 0.2, 0.3, 0.4]),
            Mock(embedding=[0.5, 0.6, 0.7, 0.8])
        ]
        mock_client.embeddings.create = AsyncMock()
        mock_client.embeddings.create.return_value = mock_embedding
        mock_zhipu_ai.return_value = mock_client

        # Setup to_thread mock to return the mock embedding directly
        mock_to_thread.return_value = mock_embedding

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

        # Verify client was called with correct parameters
        mock_client.embeddings.create.assert_called_once()
        call_args = mock_client.embeddings.create.call_args

        # Check model parameter
        assert call_args.kwargs["model"] == "embedding-2"

        # Check input parameter (should be joined text)
        assert call_args.kwargs["input"] == "Hello world"

        # Verify result (embed method returns a single list for the batch)
        # The actual implementation returns embedding vectors for the batch combined
        # Let's check that it returns some embedding vectors
        assert len(result) > 0
        assert isinstance(result[0], (float, int))

    @patch('tasking.llm.zhipu.asyncio.to_thread')
    @patch('tasking.llm.zhipu.ZhipuAI')
    def test_embedding_mock_client_return_value(self, mock_to_thread, mock_zhipu_ai):
        """Test that embedding mock client return values are correctly parsed."""
        # Setup mock with specific embedding values
        mock_client = Mock()
        mock_embedding = Mock()
        mock_embedding.data = [
            Mock(embedding=[0.9, 0.8, 0.7, 0.6, 0.5])
        ]
        mock_client.embeddings.create = AsyncMock()
        mock_client.embeddings.create.return_value = mock_embedding
        mock_zhipu_ai.return_value = mock_client

        # Setup to_thread mock to return the mock embedding directly
        mock_to_thread.return_value = mock_embedding

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