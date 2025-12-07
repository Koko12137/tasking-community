import getpass
import json
from typing import Any, cast

from pydantic import SecretStr

from mcp import Tool as McpTool
from fastmcp.tools import Tool as FastMcpTool

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


def tool_schema(
    tool: McpTool | FastMcpTool,
) -> dict[str, Any]:
    """
    Get the schema of the tool for OpenAI.

    Args:
        tool: McpTool | FastMcpTool
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
        }
    }

    if isinstance(tool, FastMcpTool):
        parameters = tool.parameters
        description['function']['annotations'] = tool.annotations
        description['function']["parameters"] = parameters
    elif isinstance(tool, McpTool):  # pyright: ignore[reportUnnecessaryIsInstance]
        description['function']["parameters"] = tool.inputSchema
        description['function']['annotations'] = tool.annotations
    else:
        raise ValueError(f"Unsupported tool type: {type(tool)}")

    return description


def to_openai(config: CompletionConfig) -> dict[str, Any]:
    """Convert the completion config to the OpenAI format.

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
    tools: list[dict[str, Any]] = [tool_schema(tool) for tool in config.tools if tool.name not in config.exclude_tools]
    if len(tools) > 0:
        kwargs["tools"] = tools

        # Add tool_choice
        if config.tool_choice is not None:
            tool_choice: list[FastMcpTool] = [tool for tool in config.tools if tool.name == config.tool_choice]

            if len(tool_choice) > 0:
                # Get tool_choice schema
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

        if not message.content:
            raise ValueError("Message content cannot be empty")

        # Process Role and Content
        message_dict['role'] = message.role.value

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
            ValueError: 2
                The value error raised by the unsupported message type.

        Returns:
            Message:
                The completed message.
        """
        kwargs = to_openai(completion_config)

        # Create the generation history
        history = to_openai_dict(messages)

        # Call for the completion
        response: ChatCompletion = await self.client.chat.completions.create(  # pyright: ignore[reportCallIssue, reportUnknownVariableType]
            model=self._model,
            messages=history,
            **kwargs,
        )

        content_text: str = response.choices[0].message.content or ""
        # Convert to list[TextBlock] format
        content_blocks = [TextBlock(text=content_text)] if content_text else []

        # Get the usage
        openai_usage: OpenAICompletionUsage | None = response.usage
        # Create the usage
        usage = CompletionUsage(
            prompt_tokens=openai_usage.prompt_tokens if openai_usage else -100,
            completion_tokens=openai_usage.completion_tokens if openai_usage else -100,
            total_tokens=openai_usage.total_tokens if openai_usage else -100
        )

        # Extract tool calls from response
        tool_calls: list[ToolCallRequest] = []
        if response.choices[0].message.tool_calls is not None:
            # Traverse all the tool calls and log the tool call
            for i, tool_call in enumerate(response.choices[0].message.tool_calls):

                # Create the tool call request
                tool_calls.append(ToolCallRequest(
                    id=tool_call.id,
                    name=tool_call.function.name,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportAttributeAccessIssue]
                    type="function",
                    args=json.loads(tool_call.function.arguments)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportAttributeAccessIssue]
                ))

        # Extract Finish reason
        if response.choices[0].finish_reason == "length":
            stop_reason = StopReason.LENGTH
        elif response.choices[0].finish_reason == "content_filter":
            stop_reason = StopReason.CONTENT_FILTER
        elif response.choices[0].finish_reason != "stop" or len(tool_calls) > 0:
            stop_reason = StopReason.TOOL_CALL
        elif response.choices[0].finish_reason == "stop" and len(tool_calls) == 0:
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
    _provider: Provider
    _model: str
    _base_url: str
    _api_key: SecretStr
    _client: AsyncOpenAI

    def __init__(self, config: LLMConfig, **kwargs: Any) -> None:
        """Initialize the OpenAiEmbeddingLLM.

        Args:
            model (str):
                The model of the embedding LLM.
            base_url (str):
                The base URL of the embedding LLM.
            **kwargs:
                The additional keyword arguments.
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

        response = await self._client.embeddings.create(
            model=self._model,
            input=text,
        )
        return response.data[0].embedding[:dimensions]

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

        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        embeddings: list[list[float | int]] = []
        for data in response.data:
            embeddings.append(data.embedding[:dimensions])
        return embeddings
