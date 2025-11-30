import os
import getpass
import json
from typing import Any

from pydantic import SecretStr
from openai import AsyncOpenAI
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.completion_usage import CompletionUsage as OpenAICompletionUsage

from .interface import ILLM, IEmbeddingLLM
from ..model import (
    ToolCallRequest, 
    Message, 
    Role,
    StopReason, 
    CompletionConfig,
    CompletionUsage,
)
from ..utils.transform.tool import Provider


def to_openai_dict(messages: list[Message]) -> list[dict[str, str | list[dict[str, str]]]]:
    """Convert the message to the OpenAI compatible messages dictionaries.
    
    Args:
        messages (list[Message, ToolCallRequest, ToolCallResult]): 
            The messages to convert.
            
    Returns:
        list[dict[str, str | list[dict[str, str]]]]: 
            The OpenAI compatible messages dictionaries.
    """
    # Create the generation history
    history: list[dict[str, str | list[dict[str, str]]]] = []
    for message in messages: 
        message_dict: dict[str, str | list[dict[str, Any]]] = {}
        
        # 处理 Role 和 Content / Multimodal Content
        message_dict['role'] = message.role.value
        if message.content != "" and message.multimodal_content == []:
            message_dict['content'] = [{'type': 'text', 'text': f"<block>{message.content}</block>"}]
        elif message.multimodal_content is not [] and message.content == "":
            message_dict['content'] = [
                {'type': 'text', 'text': f"<block>"},
                *message.multimodal_content,
                {'type': 'text', 'text': f"</block>"},
            ]
        else:
            raise ValueError(f"Unsupported message content: {message.content} and {message.multimodal_content}")
        
        # 获取最后一个消息的发送者
        last_role = history[-1]['role'] if len(history) > 0 else None
        # 同样的发送者且不为 Tool / Assistant 则进行内容拼接
        if last_role == message.role.value and message.role not in {Role.TOOL, Role.ASSISTANT}:
            # 拼接新的消息到最后的 content 中
            history[-1]['content'].extend(message_dict['content'])
            continue
        
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
            message_dict['content'] = message.content
            message_dict['tool_call_id'] = message.tool_call_id

        else:
            raise ValueError(f"Unsupported message role: {message.role}")
        
        # 添加信息
        history.append(message_dict)
        
    return history


class OpenAiLLM(ILLM):
    _provider: Provider
    _model: str
    _base_url: str
    _api_key: SecretStr
    
    def __init__(
        self, 
        model: str, 
        base_url: str,
        api_key: SecretStr,
        **kwargs: Any,
    ) -> None:
        """Initialize the OpenAiLLM.
        
        Args:
            model (str): 
                The model of the LLM.
            base_url (str): 
                The base URL of the LLM.
            api_key (SecretStr): 
                The API key for the LLM.
            **kwargs: 
                The additional keyword arguments.
        """
        # Initialize the provider
        self._provider = Provider.OPENAI
        
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        if api_key.get_secret_value() == "":
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
            ValueError: 2
                The value error raised by the unsupported message type.

        Returns:
            Message: 
                The completed message.
        """
        kwargs = completion_config.to_dict(provider=self._provider)
        
        # Create the generation history
        history = to_openai_dict(messages)
        
        # Call for the completion
        response: ChatCompletion = await self.client.chat.completions.create(  # pyright: ignore[reportCallIssue, reportUnknownVariableType]
            model=self._model,
            messages=history,
            **kwargs, 
        )
            
        content: str = response.choices[0].message.content
        # Get the usage
        openai_usage: OpenAICompletionUsage = response.usage
        # Create the usage
        usage = CompletionUsage(
            prompt_tokens=openai_usage.prompt_tokens or -100,
            completion_tokens=openai_usage.completion_tokens or -100,
            total_tokens=openai_usage.total_tokens or -100
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
            content=content, 
            tool_calls=tool_calls, 
            stop_reason=stop_reason, 
            usage=usage, 
        )
        
        # Return the response
        return message


class OpenAiEmbeddingLLM(IEmbeddingLLM):
    _provider: Provider
    _model: str
    _base_url: str
    _client: AsyncOpenAI
    
    def __init__(
        self, 
        model: str, 
        base_url: str, 
        **kwargs: Any,
    ) -> None:
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
        
        self._model = model
        self._base_url = base_url
        
        # Initialize the client
        api_key_field = kwargs.get("api_key_field", "OPENAI_KEY")
        self._client = AsyncOpenAI(
            base_url=self._base_url,
            api_key=os.getenv(api_key_field) or getpass.getpass(f"Enter your {api_key_field}: "), 
        )
                
    def get_provider(self) -> Provider:
        return self._provider

    def get_base_url(self) -> str:
        return self._base_url

    def get_model(self) -> str:
        return self._model

    async def embed(
        self, 
        text: str, 
        dimensions: int = 1024, 
        **kwargs: Any,
    ) -> list[float]:
        """Embedding the text.
        
        Args:
            text (str): 
                The text to embed. 
            dimensions (int, defaults to 1024):
                The dimensions of the embedding.
            **kwargs:
                The additional keyword arguments.
                
        Returns:
            list[float]: 
                The embedding of the text.
        """
        response = await self._client.embeddings.create(
            model=self._model, 
            input=text, 
        )
        return response.data[0].embedding[:dimensions]
