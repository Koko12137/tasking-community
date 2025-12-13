"""Zhipu AI LLM implementation module."""
import asyncio
import getpass
import json
from typing import Any, cast

from loguru import logger
from pydantic import SecretStr
from mcp import Tool as McpTool
from fastmcp.tools import Tool as FastMcpTool
from zai import ZhipuAiClient as ZhipuAI
from zai.types.chat.chat_completion import (
    Completion as ZhipuCompletion,
    CompletionMessageToolCall as ZhipuToolCall,
    CompletionUsage as ZhipuUsage,
)
from asyncer import asyncify

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
    Get the schema of the tool for Zhipu AI.

    Args:
        tool: McpTool | FastMcpTool
            The tool to get the description of.

    Returns:
        dict[str, Any]:
            The schema of the tool.
    """
    # Zhipu AI function calling schema (matches official documentation)
    function_schema: dict[str, Any] = {
        "name": tool.name,
        "description": tool.description,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }

    if isinstance(tool, FastMcpTool):
        # Extract parameters from FastMcpTool
        if hasattr(tool, 'parameters') and tool.parameters:
            function_schema["parameters"]["properties"] = tool.parameters.get("properties", {})
            function_schema["parameters"]["required"] = tool.parameters.get("required", [])
            # Add type if available
            if "type" in tool.parameters:
                function_schema["parameters"]["type"] = tool.parameters["type"]
    elif isinstance(tool, McpTool): # pyright: ignore[reportUnnecessaryIsInstance]
        # Extract parameters from McpTool inputSchema
        if hasattr(tool, 'inputSchema') and tool.inputSchema:
            function_schema["parameters"]["properties"] = tool.inputSchema.get("properties", {})
            function_schema["parameters"]["required"] = tool.inputSchema.get("required", [])
            # Add type if available
            if "type" in tool.inputSchema:
                function_schema["parameters"]["type"] = tool.inputSchema["type"]
    else:
        raise ValueError(f"Unsupported tool type: {type(tool)}")

    # Build the complete tool schema in Zhipu AI format
    return {
        "type": "function",
        "function": function_schema
    }


def to_zhipu(config: CompletionConfig) -> dict[str, Any]:
    """Convert the completion config to the Zhipu AI format.

    Returns:
        dict:
            The completion config in the Zhipu AI format.
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

    # response_format (Zhipu AI supports json_object)
    if config.format_json:
        kwargs["response_format"] = {"type": "json_object"}

    # tools (Zhipu AI uses OpenAI-like format)
    tools: list[dict[str, Any]] = [
        tool_schema(tool) for tool in config.tools
        if tool.name not in config.exclude_tools
    ]
    if len(tools) > 0:
        kwargs["tools"] = tools

        # tool_choice
        if config.tool_choice is not None:
            tool_choice: list[FastMcpTool] = [
                tool for tool in config.tools
                if tool.name == config.tool_choice
            ]

            if len(tool_choice) > 0:
                tool_choice_schema = tool_schema(tool_choice[0])
                kwargs["tool_choice"] = tool_choice_schema

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


def _convert_content_to_zhipu_format(
    content: list[TextBlock | ImageBlock | VideoBlock]
) -> list[dict[str, Any]]:
    """Convert unified content to Zhipu AI's format.

    Args:
        content: List of content blocks

    Returns:
        List of Zhipu AI-compatible content blocks
    """
    zhipu_blocks: list[dict[str, Any]] = []
    for block in content:
        if isinstance(block, TextBlock):
            zhipu_blocks.append({'type': 'text', 'text': block.text})
        elif isinstance(block, ImageBlock):
            if block.image_url:
                zhipu_blocks.append({
                    'type': 'image_url',
                    'image_url': {'url': block.image_url}
                })
            elif block.image_base64:
                zhipu_blocks.append({
                    'type': 'image_url',
                    'image_url': {
                        'url': f"data:image/jpeg;base64,{block.image_base64}"
                    }
                })
        elif isinstance(block, VideoBlock):   # pyright: ignore[reportUnnecessaryIsInstance]
            # Video blocks are converted to text description
            # Zhipu AI's chat completions currently doesn't directly support video input
            if block.video_url:
                video_text = f"[视频内容: {block.video_url}]"
                zhipu_blocks.append({
                    'type': 'text',
                    'text': video_text
                })
            else:
                zhipu_blocks.append({
                    'type': 'text',
                    'text': "[视频内容: base64编码的视频]"
                })
    return zhipu_blocks


def to_zhipu_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert the message to the Zhipu AI compatible messages dictionaries.

    Args:
        messages (list[Message]):
            The messages to convert.

    Returns:
        list[dict[str, Any]]:
            The Zhipu AI compatible messages dictionaries.
    """
    history: list[dict[str, str | list[dict[str, Any]]]] = []

    for message in messages:
        message_dict: dict[str, str | list[dict[str, Any]]] = {}

        if not message.content:
            raise ValueError("Message content cannot be empty")

        # Process Role and Content
        message_dict['role'] = message.role.value

        # Handle different role logic
        if message.role == Role.SYSTEM:
            if len(history) > 0:
                # Modify message_dict role to user for system messages after first
                message_dict['role'] = Role.USER.value
            # For system messages, use text content with block wrapper
            text_content = _extract_text_from_content(message.content)
            message_dict['content'] = f"<block>{text_content}</block>"

        elif message.role == Role.USER:
            # Extract text for block wrapping
            text_content = _extract_text_from_content(message.content)

            # Convert to Zhipu AI format with block wrappers
            if len(message.content) == 1 and isinstance(message.content[0], TextBlock):
                # Pure text message
                message_dict['content'] = f"<block>{text_content}</block>"
            else:
                # Multimodal message with block wrappers
                zhipu_blocks = _convert_content_to_zhipu_format(message.content)
                # Add block markers
                message_dict['content'] = [
                    {'type': 'text', 'text': "<block>"},
                    *zhipu_blocks,
                    {'type': 'text', 'text': "</block>"},
                ]

        elif message.role == Role.ASSISTANT:
            if len(history) > 0 and history[-1]['role'] != Role.USER.value:
                raise ValueError("Assistant message must be followed by a user message.")

            # Extract text content for assistant message with block wrapper
            text_content = _extract_text_from_content(message.content)
            message_dict['content'] = f"<block>{text_content}</block>"

            # If the message is a tool call, add the tool call to the history
            if message.tool_calls:
                message_dict["tool_calls"] = []

                for tool_call in message.tool_calls:
                    message_dict["tool_calls"].append({
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(tool_call.args, ensure_ascii=False),
                        }
                    })

        elif message.role == Role.TOOL:
            message_dict['role'] = message.role.value
            # Extract text from content for tool result
            tool_result_text = _extract_text_from_content(message.content)
            message_dict['content'] = tool_result_text
            message_dict['tool_call_id'] = message.tool_call_id

        else:
            raise ValueError(f"Unsupported message role: {message.role}")

        # Check if we can merge with previous message (same role, not TOOL/ASSISTANT)
        last_role: str | None = None
        if history:
            role_val = history[-1].get('role')
            if isinstance(role_val, str):
                last_role = role_val

        if (
            last_role == message.role.value and
            message.role not in {Role.TOOL, Role.ASSISTANT} and
            history[-1].get('content')
        ):
            # Merge with previous message by adding block wrapper
            last_content = history[-1]['content']
            text_content = _extract_text_from_content(message.content)

            if isinstance(last_content, str):
                history[-1]['content'] = last_content + f"<block>{text_content}</block>"
            elif isinstance(last_content, list): # pyright: ignore[reportUnnecessaryIsInstance]
                # Last content is multimodal, create new list with block markers
                updated_content = last_content + [
                    {'type': 'text', 'text': f"<block>{text_content}</block>"}
                ]
                history[-1]['content'] = updated_content
        else:
            # Add message to history
            history.append(message_dict)

    return history


class ZhipuLLM(ILLM):
    """Zhipu AI LLM implementation."""

    _provider: Provider
    _model: str
    _base_url: str
    _api_key: SecretStr
    _client: ZhipuAI

    def __init__(self, config: LLMConfig, **_kwargs: Any) -> None:
        """Initialize the ZhipuLLM.

        Args:
            config (LLMConfig):
                The LLM configuration.
            **_kwargs:
                The additional keyword arguments (ignored).
        """
        self._provider = Provider.ZHIPU

        self._model = config.model
        self._base_url = config.base_url or "https://open.bigmodel.cn/api/paas/v4/"
        self._api_key = config.api_key
        if not self._api_key or self._api_key.get_secret_value() == "":
            self._api_key = SecretStr(
                getpass.getpass(f"Enter your API key for {self._provider}: ")
            )

        self._client = ZhipuAI(
            api_key=self._api_key.get_secret_value(),
            base_url=self._base_url,
        )

    @classmethod
    def from_config(cls, config: LLMConfig) -> ILLM:
        """Create an instance of ZhipuLLM from LLMConfig."""
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
        # Convert completion config to Zhipu AI format using the conversion function
        zhipu_kwargs = to_zhipu(completion_config)
        zhipu_kwargs["stream"] = False

        # Add any extra kwargs while preserving defaults
        for key, value in kwargs.items():
            if key not in zhipu_kwargs:
                zhipu_kwargs[key] = value

        # Convert messages to Zhipu AI format
        history = to_zhipu_messages(messages)

        try:
            # Call Zhipu AI API using asyncify for better sync-to-async conversion
            create_completion = asyncify(self._client.chat.completions.create)
            response = await create_completion(
                model=self._model,
                messages=history,
                **zhipu_kwargs,
            )

        except Exception as e:
            logger.error(e)
            raise e

        # Extract content from response using proper types
        content_text: str = ""
        zhipu_usage: ZhipuUsage | None = None
        tool_calls_response: list[ZhipuToolCall] = []
        finish_reason = "stop"

        # Use the actual types from zai package
        if isinstance(response, ZhipuCompletion) and response.choices:
            choice = response.choices[0]
            message = choice.message
            content_text = message.content or ""
            tool_calls_response = message.tool_calls or []
            finish_reason = choice.finish_reason

            # Extract usage information
            zhipu_usage = response.usage
        else:
            # Fallback for unexpected response format
            content_text = str(response) if response else ""

        # Convert to list[TextBlock] format
        content_blocks = [TextBlock(text=content_text)] if content_text else []

        # Create the usage using proper types
        if zhipu_usage:
            usage = CompletionUsage(
                prompt_tokens=zhipu_usage.prompt_tokens,
                completion_tokens=zhipu_usage.completion_tokens,
                total_tokens=zhipu_usage.total_tokens
            )
        else:
            # Fallback usage when actual usage data is not available
            usage = CompletionUsage(
                prompt_tokens=-1,
                completion_tokens=-1,
                total_tokens=-1
            )

        # Extract tool calls from response
        tool_calls: list[ToolCallRequest] = []
        if tool_calls_response:
            # Traverse all the tool calls and create tool call requests
            for tool_call in tool_calls_response:
                tool_calls.append(ToolCallRequest(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    type="function",
                    args=json.loads(tool_call.function.arguments)
                ))
        if finish_reason == "length":
            stop_reason = StopReason.LENGTH
        elif finish_reason == "content_filter":
            stop_reason = StopReason.CONTENT_FILTER
        elif finish_reason == "tool_calls" or len(tool_calls) > 0:
            stop_reason = StopReason.TOOL_CALL
        elif finish_reason == "stop" and len(tool_calls) == 0:
            stop_reason = StopReason.STOP
        else:
            stop_reason = StopReason.NONE

        return Message(
            role=Role.ASSISTANT,
            content=cast(list[TextBlock | ImageBlock | VideoBlock], content_blocks),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
        )


class ZhipuEmbeddingLLM(IEmbedModel):
    """Zhipu AI Embedding LLM implementation."""

    _provider: Provider
    _model: str
    _base_url: str
    _api_key: SecretStr
    _client: ZhipuAI

    def __init__(self, config: LLMConfig, **_kwargs: Any) -> None:
        """Initialize the ZhipuEmbeddingLLM.

        Args:
            config (LLMConfig):
                The LLM configuration.
            **_kwargs:
                The additional keyword arguments (ignored).
        """
        self._provider = Provider.ZHIPU

        self._model = config.model
        self._base_url = config.base_url or "https://open.bigmodel.cn/api/paas/v4/"
        self._api_key = config.api_key
        if not self._api_key or self._api_key.get_secret_value() == "":
            self._api_key = SecretStr(
                getpass.getpass(f"Enter your API key for {self._provider}: ")
            )

        self._client = ZhipuAI(
            api_key=self._api_key.get_secret_value(),
            base_url=self._base_url,
        )

    @classmethod
    def from_config(cls, config: LLMConfig) -> IEmbedModel:
        """Create an instance of ZhipuEmbeddingLLM from LLMConfig."""
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
        **kwargs: Any,
    ) -> list[float | int]:
        """Embedding the content.

        Args:
            content (list[MultimodalContent]):
                The multimodal content to embed.
            dimensions (int, defaults to 1024):
                The dimensions of the embedding.
            **kwargs:
                The additional keyword arguments.

        Returns:
            list[float | int]:
                The embedding of the content.
        """
        # Zhipu AI embedding API only supports string input, extract text from multimodal content
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, TextBlock):
                text_parts.append(item.text)

        # Join all text parts
        text = " ".join(text_parts).strip()

        if not text:
            raise ValueError("Cannot embed empty content")

        # Prepare API parameters
        # Add dimensions if specified (supported by embedding-3 model)
        embed_kwargs: dict[str, Any] = {}
        if dimensions != 1024:  # Only add if not default
            embed_kwargs["dimensions"] = dimensions

        try:
            response = await asyncio.to_thread(
                self._client.embeddings.create,
                model=self._model,
                input=text,
                **embed_kwargs,
            )

            # Return the embedding vector, truncated to requested dimensions if necessary
            embedding = response.data[0].embedding
            return embedding[:dimensions] if len(embedding) > dimensions else embedding

        except Exception as e:
            logger.error(e)
            raise e

    async def embed_batch(
        self,
        contents: list[list[MultimodalContent]],
        dimensions: int,
        **kwargs: Any,
    ) -> list[list[float | int]]:
        """Embedding the batch of contents.

        Args:
            contents (list[list[MultimodalContent]]):
                The multimodal contents to embed.
            dimensions (int):
                The dimensions of the embedding.
            **kwargs:
                The additional keyword arguments.

        Returns:
            list[list[float | int]]:
                The embeddings of the contents.
        """
        # Convert all contents to strings
        texts: list[str] = []
        for content in contents:
            # For multimodal content, extract text
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, TextBlock):
                    text_parts.append(item.text)

            # Join all text parts for this content
            text = " ".join(text_parts).strip()
            if not text:
                text = ""  # Allow empty strings in batch processing
            texts.append(text)

        # Prepare API parameters
        # Add dimensions if specified (supported by embedding-3 model)
        embed_kwargs: dict[str, Any] = {}
        if dimensions != 1024:  # Only add if not default
            embed_kwargs["dimensions"] = dimensions

        try:
            response = await asyncio.to_thread(
                self._client.embeddings.create,
                model=self._model,
                input=texts,
                **embed_kwargs,
            )

            # Process embeddings and ensure correct dimensions
            embeddings: list[list[float | int]] = []
            for data in response.data:
                embedding = data.embedding
                # Truncate to requested dimensions if necessary
                if len(embedding) > dimensions:
                    processed_embedding = embedding[:dimensions]
                else:
                    processed_embedding = embedding
                embeddings.append(processed_embedding)

        except Exception as e:
            logger.error(e)
            raise e

        return embeddings
