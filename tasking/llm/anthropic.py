"""Anthropic LLM implementation module."""
import getpass
from typing import Any, cast

from mcp import Tool as McpTool
from fastmcp.tools import Tool as FastMcpTool

from anthropic import AsyncAnthropic
from anthropic.types import (
    Message as AnthropicMessage,
    Usage,
    MessageParam,
    TextBlockParam,
    ToolUseBlockParam,
    ToolResultBlockParam,
    ContentBlockParam,
)

from pydantic import SecretStr

from .const import Provider
from .interface import ILLM, IEmbedModel
from ..model import (
    ToolCallRequest,
    Message,
    Role,
    StopReason,
    CompletionConfig,
    CompletionUsage,
)
from ..model.setting import LLMConfig
from ..model.message import TextBlock, ImageBlock, VideoBlock, MultimodalContent


def tool_schema(
    tool: McpTool | FastMcpTool,
) -> dict[str, Any]:
    """
    Get the schema of the tool for Anthropic.

    Args:
        tool: McpTool | FastMcpTool
            The tool to get the description of.

    Returns:
        dict[str, Any]:
            The schema of the tool.
    """
    # Anthropic schema
    description = {
        "name": tool.name,
        "description": tool.description,
    }

    if isinstance(tool, FastMcpTool):
        parameters = tool.parameters
        description['input_schema'] = parameters
    elif isinstance(tool, McpTool):  # pyright: ignore[reportUnnecessaryIsInstance]
        description['input_schema'] = tool.inputSchema
    else:
        raise ValueError(f"Unsupported tool type: {type(tool)}")

    return description


def to_anthropic(config: CompletionConfig) -> dict[str, Any]:
    """Convert the completion config to the Anthropic format.

    Returns:
        dict:
            The completion config in the Anthropic format.
    """
    kwargs: dict[str, Any] = {
        "top_p": config.top_p,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }

    # stop words -> stop_sequences
    if config.stop_words:
        kwargs["stop_sequences"] = config.stop_words

    # response_format（Anthropic supports json_object）
    if config.format_json:
        kwargs["response_format"] = {"type": "json_object"}

    # tools（Anthropic: [{name, description, input_schema}]）
    tools: list[dict[str, Any]] = []
    if config.tools:
        for tool in config.tools:
            if tool.name in config.exclude_tools:
                continue
            # FastMcpTool has name/description/parameters
            tools.append(
                {
                    "name": tool.name,
                    "description": getattr(tool, "description", "") or "",
                    "input_schema": getattr(tool, "parameters", {}) or {},
                }
            )
    if len(tools) > 0:
        kwargs["tools"] = tools

        # tool_choice（Anthropic: {"type":"tool","name":"..."} or "auto"/"any"）
        if config.tool_choice is not None:
            # Only set when this tool exists in tools
            if any(t["name"] == config.tool_choice for t in tools):
                kwargs["tool_choice"] = {"type": "tool", "name": config.tool_choice}

    return kwargs


def _extract_text_from_content(content: list[TextBlock | ImageBlock | VideoBlock]) -> str:
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


def _convert_content_to_anthropic_format(content: list[TextBlock | ImageBlock | VideoBlock]) -> list[ContentBlockParam]:
    """Convert unified content to Anthropic's format.

    Args:
        content: List of content blocks

    Returns:
        List of Anthropic-compatible content blocks
    """
    anthropic_blocks: list[ContentBlockParam] = []
    for block in content:
        if isinstance(block, TextBlock):
            anthropic_blocks.append(TextBlockParam(type="text", text=block.text))
        elif isinstance(block, ImageBlock):
            # Convert ImageBlock to Anthropic format
            if block.image_url:
                anthropic_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": block.image_url
                    }
                })
            elif block.image_base64:
                anthropic_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",  # Default, might need adjustment
                        "data": block.image_base64
                    }
                })
        elif isinstance(block, VideoBlock): # pyright: ignore[reportUnnecessaryIsInstance]
            # Video blocks might need special handling or conversion
            # For now, treat as text content with video info
            anthropic_blocks.append(TextBlockParam(
                type="text",
                text=f"[Video: {block.video_url or 'base64 video'}]"
            ))
    return anthropic_blocks


def to_anthropic_messages(messages: list[Message]) -> list[MessageParam]:
    """Convert the message to the Anthropic compatible messages dictionaries.

    Args:
        messages (list[Message]):
            The messages to convert.

    Returns:
        list[MessageParam]:
            The Anthropic compatible messages dictionaries.
    """
    history: list[MessageParam] = []

    for message in messages:
        content: str | list[ContentBlockParam]

        if not message.content:
            raise ValueError("Message content cannot be empty")

        # Extract text from content blocks
        text_content = _extract_text_from_content(message.content)

        # Convert to Anthropic format with block wrappers
        if len(message.content) == 1 and isinstance(message.content[0], TextBlock):
            # Pure text message
            content = f"<block>{text_content}</block>"
        else:
            # Multimodal message
            anthropic_blocks: list[ContentBlockParam] = [
                TextBlockParam(type="text", text="<block>"),
                *_convert_content_to_anthropic_format(message.content),
                TextBlockParam(type="text", text="</block>"),
            ]
            content = anthropic_blocks

        last_role: str | None = history[-1]["role"] if history else None

        if last_role == message.role.value and message.role not in {Role.TOOL, Role.ASSISTANT}:
            last_content = history[-1]["content"]
            if isinstance(last_content, str):
                history[-1]["content"] = last_content + f"<block>{text_content}</block>"
            elif isinstance(content, list):
                cast(list[ContentBlockParam], last_content).extend(content)
            continue

        _append_message_by_role(history, message, content)

    return history


def _append_message_by_role(
    history: list[MessageParam],
    message: Message,
    content: str | list[ContentBlockParam],
) -> None:
    """Append message to history based on its role."""
    if message.role == Role.SYSTEM:
        history.append(MessageParam(role="user", content=content))

    elif message.role == Role.USER:
        history.append(MessageParam(role="user", content=content))

    elif message.role == Role.ASSISTANT:
        if history and history[-1]["role"] != "user":
            raise ValueError("Assistant message must be followed by a user message.")

        if message.tool_calls:
            tool_calls_content: list[ToolUseBlockParam] = [
                ToolUseBlockParam(
                    type="tool_use",
                    id=tool_call.id,
                    name=tool_call.name,
                    input=tool_call.args,
                )
                for tool_call in message.tool_calls
            ]
            history.append(MessageParam(role="assistant", content=tool_calls_content))
        else:
            history.append(MessageParam(role="assistant", content=content))

    elif message.role == Role.TOOL:
        # Extract text from content for tool result
        tool_result_text = _extract_text_from_content(message.content)
        tool_result_content: list[ToolResultBlockParam] = [
            ToolResultBlockParam(
                type="tool_result",
                tool_use_id=message.tool_call_id or "",
                content=tool_result_text,
            )
        ]
        history.append(MessageParam(role="user", content=tool_result_content))

    else:
        raise ValueError(f"Unsupported message role: {message.role}")


class AnthropicLLM(ILLM):
    """Anthropic LLM implementation."""

    _provider: Provider
    _model: str
    _base_url: str
    _api_key: SecretStr
    _client: AsyncAnthropic

    def __init__(self, config: LLMConfig, **_kwargs: Any) -> None:
        """Initialize the AnthropicEmbeddingLLM.

        Args:
            config (LLMConfig):
                The LLM configuration.
            **_kwargs:
                The additional keyword arguments (unused).
        """
        self._provider = Provider.ANTHROPIC

        self._model = config.model
        self._base_url = config.base_url or "https://api.anthropic.com"
        self._api_key = config.api_key
        if not self._api_key:
            self._api_key = SecretStr(
                getpass.getpass(f"Enter your API key for {self._provider}: ")
            )

        self._client = AsyncAnthropic(
            base_url=self._base_url,
            api_key=self._api_key.get_secret_value(),
        )

    @classmethod
    def from_config(cls, config: LLMConfig) -> ILLM:
        """Create an instance of AnthropicEmbeddingLLM from LLMConfig."""
        return cls(config)

    def get_provider(self) -> Provider:
        return self._provider

    def get_base_url(self) -> str:
        return self._base_url

    def get_model(self) -> str:
        return self._model

    async def completion(
        self,
        messages: list[Message],
        completion_config: CompletionConfig,
        **kwargs: Any,
    ) -> Message:
        """Completion the messages.

        Args:
            messages (list[Message]):
                The messages to complete.
            completion_config (CompletionConfig):
                The completion configuration.
            **kwargs:
                The additional keyword arguments.

        Raises:
            ValueError:
                The value error raised by the unsupported message type.

        Returns:
            Message:
                The completed message.
        """
        kwargs = to_anthropic(completion_config)
        history = to_anthropic_messages(messages)

        response: AnthropicMessage = await self._client.messages.create(
            model=self._model,
            messages=history,
            **kwargs,
        )

        content, tool_calls = _extract_response_content(response)
        usage = _create_usage(response.usage)
        stop_reason = _map_stop_reason(response.stop_reason)

        return Message(
            role=Role.ASSISTANT,
            content=cast(list[TextBlock | ImageBlock | VideoBlock], content),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
        )


def _extract_response_content(
    response: AnthropicMessage,
) -> tuple[list[TextBlock], list[ToolCallRequest]]:
    """Extract content and tool calls from Anthropic response."""
    content_text: str = ""
    tool_calls: list[ToolCallRequest] = []

    for part in response.content:
        if part.type == "text":
            content_text += part.text
        elif part.type == "tool_use":
            tool_calls.append(ToolCallRequest(
                id=part.id,
                name=part.name,
                type="function",
                args=part.input,
            ))

    # Convert to list[TextBlock] format
    content_blocks = [TextBlock(text=content_text)] if content_text else []

    return content_blocks, tool_calls


def _create_usage(anthropic_usage: Usage) -> CompletionUsage:
    """Create CompletionUsage from Anthropic Usage."""
    prompt_tokens = anthropic_usage.input_tokens or -100
    completion_tokens = anthropic_usage.output_tokens or -100
    total_tokens = (
        (prompt_tokens + completion_tokens)
        if prompt_tokens > 0 and completion_tokens > 0
        else -100
    )
    return CompletionUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def _map_stop_reason(stop_reason: str | None) -> StopReason:
    """Map Anthropic stop reason to StopReason enum."""
    mapping = {
        "length": StopReason.LENGTH,
        "content_filter": StopReason.CONTENT_FILTER,
        "tool_use": StopReason.TOOL_CALL,
        "stop": StopReason.STOP,
        "end_turn": StopReason.STOP,
    }
    return mapping.get(stop_reason or "", StopReason.NONE)


class AnthropicEmbeddingLLM(IEmbedModel):
    """Anthropic Embedding LLM implementation (not supported)."""

    _provider: Provider
    _model: str
    _base_url: str
    _api_key: SecretStr
    _client: AsyncAnthropic

    def __init__(self, config: LLMConfig, **_kwargs: Any) -> None:
        """Initialize the AnthropicEmbeddingLLM.

        Args:
            config (LLMConfig):
                The LLM configuration.
            **_kwargs:
                The additional keyword arguments (unused).
        """
        self._provider = Provider.ANTHROPIC

        self._model = config.model
        self._base_url = config.base_url or "https://api.anthropic.com"
        self._api_key = config.api_key
        if not self._api_key:
            self._api_key = SecretStr(
                getpass.getpass(f"Enter your API key for {self._provider}: ")
            )

        self._client = AsyncAnthropic(
            base_url=self._base_url,
            api_key=self._api_key.get_secret_value(),
        )

    @classmethod
    def from_config(cls, config: LLMConfig) -> IEmbedModel:
        """Create an instance of AnthropicEmbeddingLLM from LLMConfig."""
        return cls(config)

    def get_provider(self) -> Provider:
        return self._provider

    def get_base_url(self) -> str:
        return self._base_url

    def get_model(self) -> str:
        return self._model

    async def embed(
        self,
        content: list[MultimodalContent],
        dimensions: int = 1024,
        **_kwargs: Any,
    ) -> list[float | int]:
        """Embedding the content.

        Args:
            content (list[MultimodalContent]):
                The multimodal content to embed.
            dimensions (int, defaults to 1024):
                The dimensions of the embedding.
            **_kwargs:
                The additional keyword arguments (unused).

        Raises:
            NotImplementedError:
                Anthropic does not currently support embeddings API.

        Returns:
            list[float | int]:
                The embedding vector.
        """
        _ = content, dimensions
        raise NotImplementedError("Anthropic does not currently support embeddings API")

    async def embed_batch(
        self,
        contents: list[list[MultimodalContent]],
        dimensions: int,
        **_kwargs: Any,
    ) -> list[list[float | int]]:
        """Embedding the batch of contents.

        Args:
            contents (list[list[MultimodalContent]]):
                The multimodal contents to embed.
            dimensions (int):
                The dimensions of the embedding.
            **_kwargs:
                The additional keyword arguments (unused).

        Raises:
            NotImplementedError:
                Anthropic does not currently support embeddings API.

        Returns:
            list[list[float | int]]:
                The embeddings of the contents.
        """
        _ = contents, dimensions
        raise NotImplementedError("Anthropic does not currently support embeddings API")
