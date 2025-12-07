from typing import Any

from pydantic import BaseModel, Field, ConfigDict
from fastmcp.tools import Tool as FastMcpTool


class CompletionConfig(BaseModel):
    """CompletionConfig is the configuration for the completion.

    Attributes:
        tools (list[FastMcpTool], optional, defaults to []):
            The tools to use for the agent.
        tool_choice (str, optional, defaults to None):
            The tool choice to use for the agent.
        exclude_tools (list[str], optional, defaults to []):
            The tools to exclude from the tool choice.

        top_p (float, optional, defaults to 1.0):
            The top p to use for the agent.
        max_tokens (int, optional, defaults to 8192):
            The max tokens to use for the agent.
        frequency_penalty (float, optional, defaults to 1.0):
            The frequency penalty to use for the agent.
        temperature (float, optional, defaults to 0.9):
            The temperature to use for the agent.

        format_json (bool, optional, defaults to False):
            Whether to format the response as JSON.

        allow_thinking (bool, optional, defaults to True):
            Whether to allow the agent to think.

        stream (bool, optional, defaults to False):
            Whether to stream the response.
        stream_interval (float, optional, defaults to 1.0):
            The interval to stream the response.

        stop_words (list[str], optional, defaults to []):
            The words to stop the response.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Tool parameters
    tools: list[FastMcpTool] = Field(default=[])
    tool_choice: str | None = Field(default=None)
    exclude_tools: list[str] = Field(default=[])

    # Generation parameters
    top_p: float = Field(default=1.0)
    max_tokens: int = Field(default=8192)
    frequency_penalty: float = Field(default=1.0)
    temperature: float = Field(default=0.9)

    # Format parameters
    format_json: bool = Field(default=False)
    # Thinking parameters
    allow_thinking: bool = Field(default=True)
    # Stop parameters
    stop_words: list[str] = Field(default=[])

    def update(self, **kwargs: Any) -> None:
        """Update the completion config.

        Args:
            **kwargs:
                The keyword arguments to update the completion config.
        """
        for key, value in kwargs.items():
            setattr(self, key, value)
