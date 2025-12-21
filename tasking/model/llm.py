from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class CompletionConfig(BaseModel):
    """CompletionConfig is the configuration for the completion.

    Attributes:
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
        stop_words (list[str], optional, defaults to []):
            The words to stop the response.
        stream (bool, optional, defaults to False):
            Whether to stream the response.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    top_p: float = Field(default=1.0)
    """The top p to use for nucleus sampling."""

    max_tokens: int = Field(
        default=8192,
        ge=1,
        le=128000,
        description="Maximum tokens in response"
    )
    
    frequency_penalty: float = Field(default=1.0)
    """The frequency penalty to reduce repetitiveness."""
    
    temperature: float = Field(default=0.9)
    """The temperature to use for sampling."""

    format_json: bool = Field(default=False)
    """Whether to format the response as JSON."""

    allow_thinking: bool = Field(default=True)
    """Whether to allow the agent to think."""

    stop_words: list[str] = Field(default=[])
    """The words to stop the response."""

    stream: bool = Field(default=False)
    """Whether to stream the response."""

    def update(self, **kwargs: Any) -> None:
        """Update the completion config.

        Args:
            **kwargs:
                The keyword arguments to update the completion config.
        """
        for key, value in kwargs.items():
            setattr(self, key, value)
