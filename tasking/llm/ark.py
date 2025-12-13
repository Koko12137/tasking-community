"""Ark LLM implementation module for Volcengine."""
import getpass
import json
from typing import Any, cast

from loguru import logger
from pydantic import SecretStr
from mcp import Tool as McpTool
from fastmcp.tools import Tool as FastMcpTool
from volcenginesdkarkruntime import AsyncArk
from volcenginesdkarkruntime.types.chat import (
    ChatCompletion,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionContentPartImageParam,
    ChatCompletionMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionAssistantMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionMessageToolCallParam,
)
from volcenginesdkarkruntime.types.chat.chat_completion_content_part_video_param import (
    ChatCompletionContentPartVideoParam,
)
from volcenginesdkarkruntime.types.chat.chat_completion_message_tool_call_param import (
    Function as ToolCallFunction,
)
from volcenginesdkarkruntime.types.multimodal_embedding import (
    EmbeddingInputParam,
    MultimodalEmbeddingContentPartTextParam,
    MultimodalEmbeddingContentPartImageParam,
)

# Video param is in a different module
from volcenginesdkarkruntime.types.multimodal_embedding.embedding_content_part_video_param import (
    MultimodalEmbeddingContentPartVideoParam,
)

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
from ..model.message import MultimodalContent, TextBlock, ImageBlock, VideoBlock


def tool_schema(
    tool: McpTool | FastMcpTool,
) -> dict[str, Any]:
    """
    Get the schema of the tool for Ark.

    Args:
        tool: McpTool | FastMcpTool
            The tool to get the description of.

    Returns:
        dict[str, Any]:
            The schema of the tool.
    """
    # Ark schema (similar to OpenAI)
    description: dict[str, Any] = {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
        }
    }

    if isinstance(tool, FastMcpTool):
        parameters = tool.parameters
        description['function']['parameters'] = parameters
    elif isinstance(tool, McpTool):  # pyright: ignore[reportUnnecessaryIsInstance]
        description['function']['parameters'] = tool.inputSchema
    else:
        raise ValueError(f"Unsupported tool type: {type(tool)}")

    return description


def to_ark(config: CompletionConfig) -> dict[str, Any]:
    """Convert the completion config to the Ark format.

    Returns:
        dict:
            The completion config in the Ark format.
    """
    kwargs: dict[str, Any] = {
        "top_p": config.top_p,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "frequency_penalty": config.frequency_penalty,
    }

    # stop words
    if config.stop_words:
        kwargs["stop"] = config.stop_words

    # response_format (Ark supports json_object)
    if config.format_json:
        kwargs["response_format"] = {"type": "json_object"}

    # thinking control (Ark specific)
    if config.allow_thinking:
        kwargs["thinking"] = {"type": "enabled"}
    else:
        kwargs["thinking"] = {"type": "disabled"}

    # tools (Ark uses OpenAI-like format)
    tools: list[dict[str, Any]] = [
        tool_schema(tool) for tool in config.tools
        if tool.name not in config.exclude_tools
    ]
    if len(tools) > 0:
        kwargs["tools"] = tools

        # tool_choice
        if config.tool_choice is not None:
            tool_choice: list[FastMcpTool] = [
                tool for tool in config.tools if tool.name == config.tool_choice
            ]

            if len(tool_choice) > 0:
                tool_choice_schema = tool_schema(tool_choice[0])
                kwargs["tool_choice"] = tool_choice_schema

    return kwargs


def _extract_text_from_content(content: list[MultimodalContent]) -> str:
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


def _convert_content_to_ark_format(
    content: list[MultimodalContent],
) -> list[ChatCompletionContentPartParam]:
    """Convert unified content to Ark's format.

    Args:
        content: List of content blocks

    Returns:
        List of Ark-compatible content blocks
    """
    ark_blocks: list[ChatCompletionContentPartParam] = []
    for block in content:
        if isinstance(block, TextBlock):
            ark_blocks.append(ChatCompletionContentPartTextParam(
                type="text",
                text=block.text
            ))
        elif isinstance(block, ImageBlock):
            # Convert ImageBlock to Ark format
            if block.image_url:
                ark_blocks.append(ChatCompletionContentPartImageParam(
                    type="image_url",
                    image_url={"url": block.image_url}
                ))
            elif block.image_base64:
                url_str = f"data:image/{block.image_type};base64,{block.image_base64}"
                ark_blocks.append(ChatCompletionContentPartImageParam(
                    type="image_url",
                    image_url={"url": url_str}
                ))
        elif isinstance(block, VideoBlock): # pyright: ignore[reportUnnecessaryIsInstance]
            # Video blocks might need special handling
            if block.video_base64:
                video_url_str = f"data:video/{block.video_type};base64,{block.video_base64}"
            else:
                video_url_str = block.video_url or ""
            ark_blocks.append(ChatCompletionContentPartVideoParam(
                type="video_url",
                video_url={"url": video_url_str},
            ))
    return ark_blocks


def to_ark_dict(messages: list[Message]) -> list[ChatCompletionMessageParam]:
    """Convert the message to the Ark compatible messages dictionaries.

    Args:
        messages (list[Message]):
            The messages to convert.

    Returns:
        list[ChatCompletionMessageParam]:
            The Ark compatible messages dictionaries.
    """
    history: list[ChatCompletionMessageParam] = []

    for message in messages:
        content: list[ChatCompletionContentPartParam]

        if not message.content:
            raise ValueError("Message content cannot be empty")

        # Extract text for block wrapping
        text_content = _extract_text_from_content(message.content)

        # Convert to Ark format with block wrappers
        if len(message.content) == 1 and isinstance(message.content[0], TextBlock):
            # Pure text message
            content = [ChatCompletionContentPartTextParam(
                type="text",
                text=f"<block>{text_content}</block>"
            )]
        else:
            # Multimodal message
            content = [
                ChatCompletionContentPartTextParam(type="text", text="<block>"),
                *_convert_content_to_ark_format(message.content),
                ChatCompletionContentPartTextParam(type="text", text="</block>"),
            ]

        last_role: str | None = history[-1]["role"] if history else None

        if last_role == message.role.value and message.role not in {Role.TOOL, Role.ASSISTANT}:
            last_content = history[-1].get("content")
            if isinstance(last_content, list):
                last_content.extend(content)
            continue

        _append_message_by_role(history, message, content)

    return history


def _append_message_by_role(
    history: list[ChatCompletionMessageParam],
    message: Message,
    content: list[ChatCompletionContentPartParam],
) -> None:
    """Append message to history based on its role."""
    if message.role == Role.SYSTEM:
        history.append(ChatCompletionSystemMessageParam(
            role="system",
            content=content,
        ))

    elif message.role == Role.USER:
        history.append(ChatCompletionUserMessageParam(
            role="user",
            content=content,
        ))

    elif message.role == Role.ASSISTANT:
        if history and history[-1]["role"] != "user":
            raise ValueError("Assistant message must be followed by a user message.")

        if message.tool_calls:
            tool_calls: list[ChatCompletionMessageToolCallParam] = [
                ChatCompletionMessageToolCallParam(
                    id=tool_call.id,
                    type="function",
                    function=ToolCallFunction(
                        name=tool_call.name,
                        arguments=json.dumps(tool_call.args, ensure_ascii=False),
                    ),
                )
                for tool_call in message.tool_calls
            ]
            history.append(ChatCompletionAssistantMessageParam(
                role="assistant",
                content=content,
                tool_calls=tool_calls,
            ))
        else:
            history.append(ChatCompletionAssistantMessageParam(
                role="assistant",
                content=content,
            ))

    elif message.role == Role.TOOL:
        # Extract text from content for tool result
        tool_result_text = _extract_text_from_content(message.content)
        history.append(ChatCompletionToolMessageParam(
            role="tool",
            content=tool_result_text,
            tool_call_id=message.tool_call_id or "",
        ))

    else:
        raise ValueError(f"Unsupported message role: {message.role}")


class ArkLLM(ILLM):
    """Ark LLM implementation for Volcengine."""

    _provider: Provider
    _model: str
    _base_url: str
    _api_key: SecretStr
    _client: AsyncArk

    def __init__(self, config: LLMConfig, **_kwargs: Any) -> None:
        """Initialize the ArkLLM.

        Args:
            config (LLMConfig):
                The configuration for the LLM.
            **kwargs:
                The additional keyword arguments.

        Raises:
            ImportError:
                If volcenginesdkarkruntime is not installed.
        """
        self._provider = Provider.ARK

        self._model = config.model
        self._base_url = config.base_url or "https://ark.cn-beijing.volces.com/api/v3"
        api_key = config.api_key
        self._api_key = api_key
        if api_key.get_secret_value() == "":
            self._api_key = SecretStr(
                getpass.getpass(f"Enter your API key for {self._provider}: ")
            )

        self._client = AsyncArk(
            base_url=self._base_url,
            api_key=self._api_key.get_secret_value(),
        )

    @classmethod
    def from_config(cls, config: LLMConfig) -> ILLM:
        """Create an instance of ArkLLM from LLMConfig."""
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
                The value error raised by the unsupported message type or API errors.

        Returns:
            Message:
                The completed message.
        """
        assert self._client is not None, "Client not initialized"

        kwargs = to_ark(completion_config)
        history = to_ark_dict(messages)

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=history,
                stream=False,
                **kwargs,
            )

            # Type assertion: stream=False returns ChatCompletion, not AsyncStream
            response = cast(ChatCompletion, response)

            content_text: str = response.choices[0].message.content or ""
            # Convert to list[TextBlock] format
            content_blocks = [TextBlock(text=content_text)] if content_text else []

            usage = _create_usage(response)
            tool_calls = _extract_tool_calls(response)
            stop_reason = _map_stop_reason(response, tool_calls)

            return Message(
                role=Role.ASSISTANT,
                content=cast(list[MultimodalContent], content_blocks),
                tool_calls=tool_calls,
                stop_reason=stop_reason,
                usage=usage,
            )

        except Exception as e:
            logger.error(e)
            raise e


def _create_usage(response: ChatCompletion) -> CompletionUsage:
    """Create CompletionUsage from Ark response."""
    ark_usage = response.usage
    if ark_usage is None:
        return CompletionUsage(
            prompt_tokens=-100,
            completion_tokens=-100,
            total_tokens=-100,
        )
    return CompletionUsage(
        prompt_tokens=ark_usage.prompt_tokens or -100,
        completion_tokens=ark_usage.completion_tokens or -100,
        total_tokens=ark_usage.total_tokens or -100,
    )


def _extract_tool_calls(response: ChatCompletion) -> list[ToolCallRequest]:
    """Extract tool calls from Ark response."""
    tool_calls: list[ToolCallRequest] = []
    message_tool_calls = response.choices[0].message.tool_calls

    if message_tool_calls is not None:
        for tool_call in message_tool_calls:
            tool_calls.append(ToolCallRequest(
                id=tool_call.id,
                name=tool_call.function.name,
                type="function",
                args=json.loads(tool_call.function.arguments),
            ))

    return tool_calls


def _map_stop_reason(
    response: ChatCompletion,
    tool_calls: list[ToolCallRequest],
) -> StopReason:
    """Map Ark finish reason to StopReason enum."""
    finish_reason = response.choices[0].finish_reason

    if finish_reason == "length":
        return StopReason.LENGTH
    if finish_reason == "content_filter":
        return StopReason.CONTENT_FILTER
    if finish_reason != "stop" or tool_calls:
        return StopReason.TOOL_CALL
    if finish_reason == "stop" and not tool_calls:
        return StopReason.STOP
    return StopReason.NONE


def _convert_content_to_ark_embedding_format(
    content: list[MultimodalContent],
) -> list[EmbeddingInputParam]:
    """Convert unified content to Ark embedding format.

    Args:
        content: List of content blocks

    Returns:
        List of Ark-compatible embedding input items
    """
    ark_items: list[EmbeddingInputParam] = []
    for block in content:
        if isinstance(block, TextBlock):
            ark_items.append(
                MultimodalEmbeddingContentPartTextParam(
                    type="text",
                    text=block.text
                )
            )
        elif isinstance(block, ImageBlock):
            # Convert ImageBlock to Ark embedding format
            if block.image_url:
                ark_items.append(
                    MultimodalEmbeddingContentPartImageParam(
                        type="image_url",
                        image_url={"url": block.image_url}
                    )
                )
            elif block.image_base64:
                url_str = f"data:image/{block.image_type};base64,{block.image_base64}"
                ark_items.append(
                    MultimodalEmbeddingContentPartImageParam(
                        type="image_url",
                        image_url={"url": url_str}
                    )
                )
        elif isinstance(block, VideoBlock): # pyright: ignore[reportUnnecessaryIsInstance]
            # Convert VideoBlock to Ark embedding format
            # Prioritize base64 over URL for video data
            if block.video_base64:
                url_str = f"data:video/{block.video_type};base64,{block.video_base64}"
                ark_items.append(
                    MultimodalEmbeddingContentPartVideoParam(
                        type="video_url",
                        video_url={"url": url_str}
                    )
                )
            elif block.video_url:
                ark_items.append(
                    MultimodalEmbeddingContentPartVideoParam(
                        type="video_url",
                        video_url={"url": block.video_url}
                    )
                )
        else:
            raise ValueError(f"Unsupported content block type: {type(block)}")

    return ark_items


class ArkEmbeddingLLM(IEmbedModel):
    """Ark Embedding LLM implementation."""

    _provider: Provider
    _model: str
    _base_url: str
    _api_key: SecretStr
    _client: AsyncArk | None = None

    def __init__(self, config: LLMConfig, **_kwargs: Any) -> None:
        """Initialize the ArkLLM.

        Args:
            config (LLMConfig):
                The configuration for the LLM.
            **kwargs:
                The additional keyword arguments.

        Raises:
            ImportError:
                If volcenginesdkarkruntime is not installed.
        """
        self._provider = Provider.ARK

        self._model = config.model
        self._base_url = config.base_url or "https://ark.cn-beijing.volces.com/api/v3"
        api_key = config.api_key
        self._api_key = api_key
        if api_key.get_secret_value() == "":
            self._api_key = SecretStr(
                getpass.getpass(f"Enter your API key for {self._provider}: ")
            )

        self._client = AsyncArk(
            base_url=self._base_url,
            api_key=self._api_key.get_secret_value(),
        )

    @classmethod
    def from_config(cls, config: LLMConfig) -> IEmbedModel:
        """Create an instance of ArkEmbeddingModel from LLMConfig."""
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

        Returns:
            list[float | int]:
                The embedding vector.
        """
        assert self._client is not None, "Client not initialized"

        # Convert tasking MultimodalContent to Ark embedding format
        ark_input = _convert_content_to_ark_embedding_format(content)

        if not ark_input:
            raise ValueError("No valid content found for embedding")

        try:
            # Call the API using proper Ark embedding format
            response = await self._client.multimodal_embeddings.create(
                model=self._model,
                input=ark_input,
                dimensions=dimensions,
            )

            # Extract the embedding vector
            # response.data is a MultimodalEmbedding object with an embedding field
            return response.data.embedding

        except Exception as e:
            logger.error(e)
            raise e

    async def embed_batch(
        self,
        contents: list[list[MultimodalContent]],
        dimensions: int,
        **_kwargs: Any,
    ) -> list[list[float | int]]:
        """Embedding the batch of contents.

        Args:
            contents (list[str | list[dict[str, Any]]]):
                The texts or multimodal contents to embed.
            dimensions (int):
                The dimensions of the embedding.
            **_kwargs:
                The additional keyword arguments (unused).

        Returns:
            list[list[float | int]]:
                The embeddings of the contents.
        """
        assert self._client is not None, "Client not initialized"

        # Process each content individually and collect embeddings
        embeddings: list[list[float]] = []

        for content in contents:
            # Use the single embed method for each content
            embedding = await self.embed(content, dimensions)
            embeddings.append(embedding)

        return embeddings
