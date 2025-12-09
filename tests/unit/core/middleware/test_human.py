"""
Unit tests for middleware human components.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from typing import Any, cast

from tasking.core.middleware.human import (
    IHumanClient,
    BaseHumanClient,
    HumanInterfere
)
from tasking.model import Message, Role, IQueue, AsyncQueue, TextBlock, MultimodalContent


class TestHumanInterfere:
    """Test HumanInterfere exception class."""

    def test_human_interfere_initialization(self) -> None:
        """Test HumanInterfere initialization with messages."""
        text_block = TextBlock(text="Test human message")
        messages = [text_block]

        exception = HumanInterfere(messages)

        assert exception._messages == messages
        assert exception._message == "Test human message"
        assert str(exception) == "HumanInterfere: Test human message"

    def test_human_interfere_get_messages(self) -> None:
        """Test getting messages from HumanInterfere."""
        text_block1 = TextBlock(text="Message 1")
        text_block2 = TextBlock(text="Message 2")
        messages = [text_block1, text_block2]

        exception = HumanInterfere(messages)

        assert exception.get_messages() == messages

    def test_human_interfere_empty_messages(self) -> None:
        """Test HumanInterfere with empty messages."""
        messages: list[MultimodalContent] = []

        exception = HumanInterfere(messages)

        assert exception._messages == []
        assert exception._message == ""
        assert str(exception) == "HumanInterfere: "

    def test_human_interfere_mixed_content_types(self) -> None:
        """Test HumanInterfere with mixed content types."""
        text_block = TextBlock(text="Text content")
        # Note: In real usage, there might be other content types like ImageBlock
        messages = [text_block]

        exception = HumanInterfere(messages)

        # Should only extract text from TextBlock instances
        assert exception._message == "Text content"


class TestIHumanClient:
    """Test IHumanClient interface compliance."""

    def test_ihuman_client_is_abstract(self) -> None:
        """Test that IHumanClient cannot be instantiated directly."""
        with pytest.raises(TypeError):
            IHumanClient()

    def test_ihuman_client_method_signatures(self) -> None:
        """Test that IHumanClient defines required methods."""
        # Check that abstract methods are defined
        abstract_methods = IHumanClient.__abstractmethods__
        expected_methods = {"is_valid", "ask_human"}

        assert abstract_methods == expected_methods


class ConcreteHumanClient(IHumanClient):
    """Concrete implementation for testing."""

    def is_valid(self, context: dict[str, Any]) -> bool:
        return context.get("valid", False)

    async def ask_human(
        self,
        context: dict[str, Any],
        queue: IQueue[Message],
        message: Message,
    ) -> Message:
        return Message(
            role=Role.ASSISTANT,
            content=[TextBlock(text="Human response")]
        )


class TestConcreteHumanClient:
    """Test concrete human client implementation."""

    def test_is_valid_true(self) -> None:
        """Test is_valid returns True when context indicates validity."""
        client = ConcreteHumanClient()
        context = {"valid": True}

        assert client.is_valid(context) is True

    def test_is_valid_false(self) -> None:
        """Test is_valid returns False when context indicates invalidity."""
        client = ConcreteHumanClient()
        context = {"valid": False}

        assert client.is_valid(context) is False

    def test_is_valid_missing_key(self) -> None:
        """Test is_valid returns False when valid key is missing."""
        client = ConcreteHumanClient()
        context = {}

        assert client.is_valid(context) is False

    @pytest.mark.asyncio
    async def test_ask_human(self) -> None:
        """Test ask_human method returns appropriate response."""
        client = ConcreteHumanClient()
        context = {"test": "value"}
        queue = Mock(spec=IQueue)
        message = Message(
            role=Role.USER,
            content=[TextBlock(text="Human input")]
        )

        response = await client.ask_human(context, queue, message)

        assert response.role == Role.ASSISTANT
        assert len(response.content) == 1
        assert isinstance(response.content[0], TextBlock)
        assert response.content[0].text == "Human response"


class TestBaseHumanClient:
    """Test BaseHumanClient if it exists."""

    def test_base_human_client_exists(self) -> None:
        """Test that BaseHumanClient is available from middleware."""
        # This test ensures the import is working
        from tasking.core.middleware.human import BaseHumanClient
        assert BaseHumanClient is not None