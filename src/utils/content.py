"""Utility functions for handling Message content."""
from typing import Any
from ..model.message import Message, TextBlock, ImageBlock, VideoBlock


def extract_text_from_message(message: Message) -> str:
    """Extract text content from a Message.

    Args:
        message: The Message object

    Returns:
        Concatenated text from all TextBlocks in the message
    """
    return extract_text_from_content(message.content)


def extract_text_from_content(content: list[TextBlock | ImageBlock | VideoBlock]) -> str:
    """Extract text content from the unified content field.

    Args:
        content: List of content blocks (TextBlock, ImageBlock, VideoBlock)

    Returns:
        Concatenated text from all TextBlocks
    """
    text_parts: list[str] = []
    for block in content:
        if isinstance(block, TextBlock):
            text_parts.append(block.text)
    return "".join(text_parts)


def create_text_message(text: str, **kwargs: Any) -> Message:
    """Create a Message with text content.

    Args:
        text: The text content
        **kwargs: Additional Message parameters

    Returns:
        Message with a single TextBlock
    """
    return Message(
        content=[TextBlock(text=text)],
        **kwargs
    )


def is_text_message(message: Message) -> bool:
    """Check if a Message contains only text content.

    Args:
        message: The Message to check

    Returns:
        True if the message contains only TextBlocks
    """
    return all(isinstance(block, TextBlock) for block in message.content)


def is_multimodal_message(message: Message) -> bool:
    """Check if a Message contains non-text content.

    Args:
        message: The Message to check

    Returns:
        True if the message contains ImageBlocks or VideoBlocks
    """
    return any(isinstance(block, (ImageBlock, VideoBlock)) for block in message.content)