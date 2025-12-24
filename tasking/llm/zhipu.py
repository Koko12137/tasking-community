"""Zhipu AI LLM implementation module."""
import asyncio
import getpass
import json
from typing import Any, cast

from json_repair import repair_json
from loguru import logger
from pydantic import SecretStr
from mcp.types import Tool as McpTool
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
from ..model.queue import IAsyncQueue


def tool_schema(
    tool: McpTool,
) -> dict[str, Any]:
    """
    Get the schema of the tool for Zhipu AI.

    Args:
        tool: McpTool
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

    # Extract parameters from McpTool inputSchema
    if hasattr(tool, 'inputSchema') and tool.inputSchema:
        function_schema["parameters"]["properties"] = tool.inputSchema.get("properties", {})
        function_schema["parameters"]["required"] = tool.inputSchema.get("required", [])
        # Add type if available
        if "type" in tool.inputSchema:
            function_schema["parameters"]["type"] = tool.inputSchema["type"]

    # Build the complete tool schema in Zhipu AI format
    return {
        "type": "function",
        "function": function_schema
    }


def to_zhipu(config: CompletionConfig, tools: list[McpTool] | None = None) -> dict[str, Any]:
    """Convert the completion config to the Zhipu AI format.

    Args:
        config (CompletionConfig): The completion configuration.
        tools (list[McpTool] | None): The tools to convert.

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
    if tools:
        kwargs["tools"] = [tool_schema(tool) for tool in tools]

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

    
        # Process Role and Content
        message_dict['role'] = message.role.value

        # Handle empty content
        if not message.content:
            message_dict['content'] = ""
        else:
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
                    tool_calls: list[dict[str, Any]] = []
                    message_dict["tool_calls"] = tool_calls

                    for tool_call in message.tool_calls:
                        tool_calls.append({
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
        tools: list[McpTool] | None,
        stream_queue: IAsyncQueue[Message] | None,
        completion_config: CompletionConfig,
        **kwargs: Any,
    ) -> Message:
        """Completion the messages.

        Args:
            messages (list[Message]):
                The messages to complete.
            tools (list[McpTool] | None):
                可用的工具列表，如果没有工具则为 None
            stream_queue (IQueue[Message] | None):
                流式数据队列，用于输出补全过程中产生的流式数据，如果不需要流式输出则为 None
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
        logger.info(f"[Zhipu] Starting completion with model {self._model}, messages: {len(messages)}, max_tokens: {completion_config.max_tokens}, streaming: {stream_queue is not None}")

        # Convert completion config to Zhipu AI format using the conversion function
        zhipu_kwargs = to_zhipu(completion_config, tools)

        # Add any extra kwargs while preserving defaults
        for key, value in kwargs.items():
            if key not in zhipu_kwargs:
                zhipu_kwargs[key] = value

        # Convert messages to Zhipu AI format
        history = to_zhipu_messages(messages)

        # Initialize accumulators for streaming response
        accumulated_content = ""
        accumulated_tool_calls: dict[int, ToolCallRequest] = {}

        try:
            if stream_queue is not None:
                # Streaming mode
                zhipu_kwargs["stream"] = True

                # Create a streaming completion using asyncify
                create_completion = asyncify(self._client.chat.completions.create)
                stream = await create_completion(
                    model=self._model,
                    messages=history,
                    **zhipu_kwargs,
                )

                # Process the stream
                stream = cast(Any, stream)  # Cast to Any to handle streaming properly
                async for chunk in stream:  # type: ignore[reportGeneralTypeIssues]
                    # Zhipu AI streaming format might be different
                    if hasattr(chunk, 'choices') and chunk.choices:
                        choice = chunk.choices[0]

                        # Handle content delta
                        if hasattr(choice, 'delta') and hasattr(choice.delta, 'content'):
                            if choice.delta.content:
                                content_delta = choice.delta.content
                                accumulated_content += content_delta
                                # Send chunk message to stream queue
                                chunk_message = Message(
                                    role=Role.ASSISTANT,
                                    content=[TextBlock(text=content_delta)],
                                    is_chunking=True,
                                    stop_reason=StopReason.NONE,
                                )
                                await stream_queue.put(chunk_message)

                        # Handle tool call delta
                        if hasattr(choice, 'delta') and hasattr(choice.delta, 'tool_calls'):
                            if choice.delta.tool_calls:
                                for tool_call_delta in choice.delta.tool_calls:
                                    if hasattr(tool_call_delta, 'index'):
                                        tool_index = tool_call_delta.index
                                    else:
                                        tool_index = 0

                                    if tool_index not in accumulated_tool_calls:
                                        # Initialize new tool call
                                        tool_call = ToolCallRequest(
                                            id=getattr(tool_call_delta, 'id', f"tool_call_{tool_index}"),
                                            name=getattr(tool_call_delta, 'function', {}).get('name', ''),
                                            type="function",
                                            args=json.loads(repair_json(getattr(tool_call_delta, 'function', {}).get('arguments') or '{}'))
                                        )
                                        accumulated_tool_calls[tool_index] = tool_call
                                    else:
                                        # Update existing tool call
                                        existing_tool_call = accumulated_tool_calls[tool_index]
                                        if hasattr(tool_call_delta, 'id') and tool_call_delta.id:
                                            existing_tool_call.id = tool_call_delta.id
                                        if hasattr(tool_call_delta, 'function'):
                                            if hasattr(tool_call_delta.function, 'name') and tool_call_delta.function.name:
                                                existing_tool_call.name = tool_call_delta.function.name
                                            if hasattr(tool_call_delta.function, 'arguments') and tool_call_delta.function.arguments:
                                                new_args = json.loads(repair_json(tool_call_delta.function.arguments or '{}'))
                                                existing_tool_call.args.update(new_args)

                # For Zhipu AI, we need to make a non-streaming call to get final usage
                # This is a common pattern for APIs that don't provide usage in streaming
                zhipu_kwargs_final = to_zhipu(completion_config, tools)
                zhipu_kwargs_final["stream"] = False
                create_completion_final = asyncify(self._client.chat.completions.create)
                final_response = await create_completion_final(
                    model=self._model,
                    messages=history,
                    **zhipu_kwargs_final,
                )

                final_response = cast(ZhipuCompletion, final_response)  # Type assertion for proper usage access
                logger.info(f"[Zhipu] Streaming completion successful, input_tokens: {final_response.usage.prompt_tokens if final_response.usage else 'unknown'}, output_tokens: {final_response.usage.completion_tokens if final_response.usage else 'unknown'}")

            else:
                # Non-streaming mode
                zhipu_kwargs["stream"] = False
                create_completion = asyncify(self._client.chat.completions.create)
                response = await create_completion(
                    model=self._model,
                    messages=history,
                    **zhipu_kwargs,
                )

                # Extract usage information for logging
                if isinstance(response, ZhipuCompletion) and response.usage:
                    logger.info(f"[Zhipu] Completion successful, input_tokens: {response.usage.prompt_tokens}, output_tokens: {response.usage.completion_tokens}")
                else:
                    logger.info("[Zhipu] Completion successful (usage info unavailable)")

                final_response = response

        except Exception as e:
            logger.error(f"[Zhipu] Completion failed: {e}")
            raise e

        # Extract final content and tool calls
        tool_calls: list[ToolCallRequest]
        if stream_queue is not None:
            # For streaming mode, use accumulated data
            content_blocks = [TextBlock(text=accumulated_content)] if accumulated_content else []
            tool_calls = list(accumulated_tool_calls.values())
            final_response = cast(ZhipuCompletion, final_response)  # Type assertion for proper usage access
            usage = CompletionUsage(
                prompt_tokens=final_response.usage.prompt_tokens if final_response.usage else -1,
                completion_tokens=final_response.usage.completion_tokens if final_response.usage else -1,
                total_tokens=final_response.usage.total_tokens if final_response.usage else -1
            )
            finish_reason = final_response.choices[0].finish_reason if final_response.choices else "stop"
        else:
            # For non-streaming mode, extract from response
            # Extract content from response using proper types
            content_text: str = ""
            zhipu_usage: ZhipuUsage | None = None
            tool_calls_response: list[ZhipuToolCall] = []
            finish_reason = "stop"

            # Use the actual types from zai package
            if isinstance(final_response, ZhipuCompletion) and final_response.choices:
                choice = final_response.choices[0]
                message = choice.message
                content_text = message.content or ""
                tool_calls_response = message.tool_calls or []
                finish_reason = choice.finish_reason

                # Extract usage information
                zhipu_usage = final_response.usage
            else:
                # Fallback for unexpected response format
                content_text = str(final_response) if final_response else ""

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
            tool_calls = []
            if tool_calls_response:
                # Traverse all the tool calls and create tool call requests
                for tool_call in tool_calls_response:
                    tool_calls.append(ToolCallRequest(
                        id=tool_call.id,
                        name=tool_call.function.name,
                        type="function",
                        args=json.loads(repair_json(tool_call.function.arguments or '{}'))
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

        logger.info(f"[Zhipu Embedding] Starting embedding with model {self._model}, text_length: {len(text)}, dimensions: {dimensions}")

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
            result_embedding = embedding[:dimensions] if len(embedding) > dimensions else embedding
            logger.info(f"[Zhipu Embedding] Embedding successful, dimensions: {len(result_embedding)}")
            return result_embedding

        except Exception as e:
            logger.error(f"[Zhipu Embedding] Embedding failed: {e}")
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

        logger.info(f"[Zhipu Embedding] Starting batch embedding with model {self._model}, batch_size: {len(texts)}, dimensions: {dimensions}")

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

            logger.info(f"[Zhipu Embedding] Batch embedding successful, generated {len(embeddings)} embeddings")
            return embeddings

        except Exception as e:
            logger.error(f"[Zhipu Embedding] Batch embedding failed: {e}")
            raise e
