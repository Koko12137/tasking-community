"""OpenAI LLM implementation module."""
import getpass
import json
from typing import Any, cast

from json_repair import repair_json
from loguru import logger
from pydantic import SecretStr
from mcp.types import Tool as McpTool
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from openai.types.completion_usage import CompletionUsage as OpenAICompletionUsage

from .interface import ILLM, IEmbedModel
from .const import Provider
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
    Get the schema of the tool for OpenAI.

    Args:
        tool: McpTool
            The tool to get the description of.

    Returns:
        dict[str, Any]:
            The schema of the tool.
    """
    # This schema is only compatible with OpenAI.
    description: dict[str, Any] = {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "strict": True,
            "parameters": tool.inputSchema,
            "annotations": tool.annotations,
        }
    }

    return description


def to_openai(config: CompletionConfig, tools: list[McpTool] | None = None) -> dict[str, Any]:
    """Convert the completion config to the OpenAI format.

    Args:
        config (CompletionConfig): The completion configuration.
        tools (list[McpTool] | None): The tools to convert.

    Returns:
        dict:
            The completion config in the OpenAI format.
    """
    kwargs: dict[str, Any] = {
        "top_p": config.top_p,
        "max_tokens": config.max_tokens,
        "frequency_penalty": config.frequency_penalty,
        "temperature": config.temperature,
    }

    # Process format_json
    if config.format_json:
        kwargs["response_format"] = {
            "type": "json_object",
        }

        # Truncate all the other parameters processing
        return kwargs

    # Add thinking control
    if config.allow_thinking:
        kwargs["extra_body"] = {
            "enable_thinking": True,
        }
    else:
        kwargs["extra_body"] = {
            "enable_thinking": False,
        }

    # Add tools
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


def _convert_content_to_openai_format(content: list[TextBlock | ImageBlock | VideoBlock]) -> list[dict[str, Any]]:
    """Convert unified content to OpenAI's format.

    Args:
        content: List of content blocks

    Returns:
        List of OpenAI-compatible content blocks
    """
    openai_blocks: list[dict[str, Any]] = []
    for block in content:
        if isinstance(block, TextBlock):
            openai_blocks.append({'type': 'text', 'text': block.text})
        elif isinstance(block, ImageBlock):
            if block.image_url:
                openai_blocks.append({
                    'type': 'image_url',
                    'image_url': {'url': block.image_url}
                })
            elif block.image_base64:
                openai_blocks.append({
                    'type': 'image_url',
                    'image_url': {
                        'url': f"data:image/jpeg;base64,{block.image_base64}"
                    }
                })
        elif isinstance(block, VideoBlock): # pyright: ignore[reportUnnecessaryIsInstance]
            # Video blocks might need special handling
            openai_blocks.append({
                'type': 'text',
                'text': f"[Video: {block.video_url or 'base64 video'}]"
            })
    return openai_blocks


def to_openai_dict(messages: list[Message]) -> list[ChatCompletionMessageParam]:
    """Convert the message to the OpenAI compatible messages dictionaries.

    Args:
        messages (list[Message, ToolCallRequest, ToolCallResult]):
            The messages to convert.

    Returns:
        list[ChatCompletionMessageParam]:
            The OpenAI compatible messages dictionaries.
    """
    # Create the generation history
    history: list[ChatCompletionMessageParam] = []
    for message in messages:
        message_dict: dict[str, Any] = {}

      # Process Role and Content
        message_dict['role'] = message.role.value

        # Handle empty content
        if not message.content:
            message_dict['content'] = ""
        else:
            # Extract text for block wrapping
            text_content = _extract_text_from_content(message.content)

            # Convert to OpenAI format with block wrappers
            if len(message.content) == 1 and isinstance(message.content[0], TextBlock):
                # Pure text message
                message_dict['content'] = [{'type': 'text', 'text': f"<block>{text_content}</block>"}]
            else:
                # Multimodal message
                message_dict['content'] = [
                    {'type': 'text', 'text': f"<block>"},
                    *_convert_content_to_openai_format(message.content),
                    {'type': 'text', 'text': f"</block>"},
                ]

        # Get last message sender
        last_role = history[-1]['role'] if len(history) > 0 else None
        # Same sender and not Tool/Assistant, concatenate content
        if last_role == message.role.value and message.role not in {Role.TOOL, Role.ASSISTANT}:
            # For simplicity, just append the message as a new entry
            # This avoids type complexity with concatenating mixed content types
            pass

         # 处理不同角色的消息逻辑
        if message.role == Role.SYSTEM:
            if len(history) > 0:
                # 修改 message_dict 的 role 为 user
                message_dict['role'] = Role.USER.value

        elif message.role == Role.USER:
            # 没有额外的操作，防止报错
            pass

        elif message.role == Role.ASSISTANT:
            if len(history) > 0 and history[-1]['role'] != Role.USER.value:
                raise ValueError(f"Assistant message must be followed by a user message.")

            # If the message is a tool call, add the tool call to the history
            if message.tool_calls != []:
                message_dict["tool_calls"] = list[dict[str, Any]]()

                for tool_call in message.tool_calls:
                    message_dict["tool_calls"].append({     # TODO: 统一一下转换的接口
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

        # 添加信息
        history.append(cast(ChatCompletionMessageParam, message_dict))

    return history


class OpenAiLLM(ILLM):
    """OpenAI LLM implementation."""
    _provider: Provider
    _model: str
    _base_url: str
    _api_key: SecretStr

    def __init__(self, config: LLMConfig, **kwargs: Any) -> None:
        """Initialize the OpenAiLLM.

        Args:
            model (str):
                The model of the LLM.
            config (LLMConfig):
                The configuration of the LLM.
            **kwargs:
                The additional keyword arguments.
        """
        # Initialize the provider
        self._provider = Provider.OPENAI

        self._model = config.model
        self._base_url = config.base_url
        self._api_key = config.api_key
        if self._api_key.get_secret_value() == "":
            self._api_key = SecretStr(getpass.getpass(f"Enter your API key for {self._provider}: "))

        # Initialize the client
        self.client = AsyncOpenAI(
            base_url=self._base_url,
            api_key=self._api_key.get_secret_value(),
        )

        # Check extra keyword arguments for requests
        self.kwargs: dict[str, Any] = {}
        for key, value in kwargs.items():
            if key == "extra_body":
                self.kwargs["extra_body"] = {key: value}
    @classmethod
    def from_config(cls, config: LLMConfig) -> ILLM:
        """Create an instance of OpenAiLLM from LLMConfig."""
        return cls(config)

    def get_provider(self) -> Provider:
        """Get the provider of the LLM."""
        return self._provider

    def get_base_url(self) -> str:
        """Get the base URL of the LLM."""
        return self._base_url

    def get_model(self) -> str:
        """Get the model of the LLM."""
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
            ValueError: 2
                The value error raised by the unsupported message type or API errors.

        Returns:
            Message:
                The completed message.
        """
        logger.info(f"[OpenAI] Starting completion with model {self._model}, messages: {len(messages)}, max_tokens: {completion_config.max_tokens}, streaming: {stream_queue is not None}")

        kwargs = to_openai(completion_config, tools)

        # Create the generation history
        history = to_openai_dict(messages)

        # Initialize accumulators for streaming response
        accumulated_content = ""
        accumulated_tool_calls: dict[str, ToolCallRequest] = {}
        current_tool_call_index = 0

        try:
            if stream_queue is not None:
                # Streaming mode
                stream = await self.client.chat.completions.create(
                    model=self._model,
                    messages=history,
                    stream=True,
                    **kwargs,
                )
                async for chunk in stream:
                    if chunk.choices:
                        choice = chunk.choices[0]

                        # Handle content delta
                        if choice.delta and choice.delta.content:
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
                        if choice.delta and choice.delta.tool_calls:
                            for tool_call_delta in choice.delta.tool_calls:
                                if tool_call_delta.index is not None: # pyright: ignore[reportUnnecessaryComparison]
                                    tool_index = tool_call_delta.index
                                else:
                                    tool_index = current_tool_call_index
                                    current_tool_call_index += 1

                                # Use string key for dictionary
                                tool_key = str(tool_index)
                                if tool_key not in accumulated_tool_calls:
                                    function_name = tool_call_delta.function.name if tool_call_delta.function and tool_call_delta.function.name else ""
                                    accumulated_tool_calls[tool_key] = ToolCallRequest(
                                        id=tool_call_delta.id or f"tool_call_{tool_index}",
                                        name=function_name,
                                        type="function",
                                        args=json.loads(repair_json(tool_call_delta.function.arguments or '{}')) if tool_call_delta.function and tool_call_delta.function.arguments else {},
                                    )
                                else:
                                    # Update existing tool call
                                    existing_tool_call = accumulated_tool_calls[tool_key]
                                    if tool_call_delta.id:
                                        existing_tool_call.id = tool_call_delta.id
                                    if tool_call_delta.function and tool_call_delta.function.name:
                                        existing_tool_call.name = tool_call_delta.function.name
                                    if tool_call_delta.function and tool_call_delta.function.arguments:
                                        # Merge arguments
                                        new_args = json.loads(repair_json(tool_call_delta.function.arguments or '{}'))
                                        existing_tool_call.args.update(new_args)

                # For streaming, we need to make a separate non-streaming call to get usage info
                # This is a common pattern when streaming doesn't provide full usage details
                final_response = await self.client.chat.completions.create(
                    model=self._model,
                    messages=history,
                    stream=False,
                    **kwargs,
                )
                logger.info(f"[OpenAI] Streaming completion successful, input_tokens: {final_response.usage.prompt_tokens if final_response.usage else 'unknown'}, output_tokens: {final_response.usage.completion_tokens if final_response.usage else 'unknown'}")

            else:
                # Non-streaming mode
                response = cast(
                    ChatCompletion,
                    await self.client.chat.completions.create(
                        model=self._model,
                        messages=history,
                        **kwargs,
                    ),
                )

                logger.info(f"[OpenAI] Completion successful, input_tokens: {response.usage.prompt_tokens if response.usage else 'unknown'}, output_tokens: {response.usage.completion_tokens if response.usage else 'unknown'}")
                final_response = response

        except Exception as e:
            logger.error(f"[OpenAI] Completion failed: {e}")
            raise e

        # Extract final content and tool calls
        tool_calls: list[ToolCallRequest]
        if stream_queue is not None:
            # For streaming mode, use accumulated data
            content_blocks = [TextBlock(text=accumulated_content)] if accumulated_content else []
            tool_calls = list(accumulated_tool_calls.values())
            usage = CompletionUsage(
                prompt_tokens=final_response.usage.prompt_tokens if final_response.usage else -100,
                completion_tokens=final_response.usage.completion_tokens if final_response.usage else -100,
                total_tokens=final_response.usage.total_tokens if final_response.usage else -100
            )
            if final_response.choices:
                finish_reason = final_response.choices[0].finish_reason
            else:
                finish_reason = None
        else:
            # For non-streaming mode, extract from response
            content_text: str = final_response.choices[0].message.content or ""
            content_blocks = [TextBlock(text=content_text)] if content_text else []

            # Get the usage
            openai_usage: OpenAICompletionUsage | None = final_response.usage
            usage = CompletionUsage(
                prompt_tokens=openai_usage.prompt_tokens if openai_usage else -100,
                completion_tokens=openai_usage.completion_tokens if openai_usage else -100,
                total_tokens=openai_usage.total_tokens if openai_usage else -100
            )

            # Extract tool calls from response
            tool_calls = []
            if final_response.choices[0].message.tool_calls is not None:
                for tool_call in final_response.choices[0].message.tool_calls:
                    tool_calls.append(ToolCallRequest(
                        id=tool_call.id,
                        name=tool_call.function.name,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportAttributeAccessIssue]
                        type="function",
                        args=json.loads(repair_json(tool_call.function.arguments or '{}'))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportAttributeAccessIssue]
                    ))
            finish_reason = final_response.choices[0].finish_reason

        # Extract Finish reason
        if finish_reason == "length":
            stop_reason = StopReason.LENGTH
        elif finish_reason == "content_filter":
            stop_reason = StopReason.CONTENT_FILTER
        elif finish_reason != "stop" or len(tool_calls) > 0:
            stop_reason = StopReason.TOOL_CALL
        elif finish_reason == "stop" and len(tool_calls) == 0:
            stop_reason = StopReason.STOP
        else:
            stop_reason = StopReason.NONE

        message = Message(
            role=Role.ASSISTANT,
            content=cast(list[TextBlock | ImageBlock | VideoBlock], content_blocks),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
        )

        # Return the response
        return message


class OpenAiEmbeddingLLM(IEmbedModel):
    """OpenAI Embedding LLM implementation."""
    _provider: Provider
    _model: str
    _base_url: str
    _api_key: SecretStr
    _client: AsyncOpenAI

    def __init__(self, config: LLMConfig, **_kwargs: Any) -> None:
        """Initialize the OpenAiEmbeddingLLM.

        Args:
            model (str):
                The model of the embedding LLM.
            base_url (str):
                The base URL of the embedding LLM.
            **_kwargs:
                The additional keyword arguments (unused).
        """
        # Initialize the provider
        self._provider = Provider.OPENAI

        self._model = config.model
        self._base_url = config.base_url
        self._api_key = config.api_key
        # Check API key
        if self._api_key.get_secret_value() == "":
            self._api_key = SecretStr(getpass.getpass(f"Enter your API key for {self._provider}: "))

        # Initialize the client
        self._client = AsyncOpenAI(
            base_url=self._base_url,
            api_key=self._api_key.get_secret_value(),
        )

    @classmethod
    def from_config(cls, config: LLMConfig) -> IEmbedModel:
        """Create an instance of OpenAiEmbeddingLLM from LLMConfig."""
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
        """Embedding the text.

        Args:
            content (list[MultimodalContent]):
                The multimodal content to embed.
            dimensions (int, defaults to 1024):
                The dimensions of the embedding.
            **kwargs:
                The additional keyword arguments.

        Returns:
            list[float | int]:
                The embedding of the text.
        """
        # OpenAI embedding API only supports string input, for multimodal content, extract text
        text = " ".join(
            [item.text if isinstance(item, TextBlock) else "" for item in content]
        )

        logger.info(f"[OpenAI Embedding] Starting embedding with model {self._model}, text_length: {len(text)}, dimensions: {dimensions}")

        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=text,
            )
            embedding = response.data[0].embedding[:dimensions]
            logger.info(f"[OpenAI Embedding] Embedding successful, dimensions: {len(embedding)}")
            return embedding

        except Exception as e:
            logger.error(f"[OpenAI Embedding] Embedding failed: {e}")
            raise e

    async def embed_batch(
        self,
        contents: list[list[MultimodalContent]],
        dimensions: int,
        **kwargs: Any
    ) -> list[list[float | int]]:
        """Embedding the batch of texts.

        Args:
            contents (list[list[MultimodalContent]]):
                The multimodal contents to embed.
            dimensions (int):
                The dimensions of the embedding.
            **kwargs:
                The additional keyword arguments.

        Returns:
            list[list[float | int]]:
                The embeddings of the texts.
        """
        # Convert all contents to strings
        texts: list[str] = []
        for content in contents:
            # For multimodal content, extract text
            text = " ".join(
                item.text if isinstance(item, TextBlock) else ""
                for item in content
            )
            texts.append(text)

        logger.info(f"[OpenAI Embedding] Starting batch embedding with model {self._model}, batch_size: {len(texts)}, dimensions: {dimensions}")

        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=texts,
            )
            embeddings: list[list[float | int]] = []
            for data in response.data:
                embeddings.append(data.embedding[:dimensions])
            logger.info(f"[OpenAI Embedding] Batch embedding successful, generated {len(embeddings)} embeddings")
            return embeddings

        except Exception as e:
            logger.error(f"[OpenAI Embedding] Batch embedding failed: {e}")
            raise e
