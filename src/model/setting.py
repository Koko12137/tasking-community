"""
Global settings management using Pydantic.

This module provides a singleton Settings class that loads configuration
from environment variables and .env files.
"""
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    """LLM configuration settings."""

    provider: Literal["openai", "anthropic"] = Field(
        default="openai",
        description="LLM provider name"
    )

    api_key: SecretStr = Field(
        description="API key for the LLM provider",
        default=SecretStr("")
    )

    base_url: str = Field(
        default="https://open.bigmodel.cn/api/coding/paas/v4",
        description="Base URL for LLM API (optional for custom endpoints)"
    )

    model: str = Field(
        default="GLM-4.6",
        description="Model name to use"
    )

    max_tokens: int = Field(
        default=8192,
        ge=1,
        le=128000,
        description="Maximum tokens in response"
    )

    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature"
    )

    timeout: int = Field(
        default=60,
        ge=1,
        le=600,
        description="Request timeout in seconds"
    )

    @field_validator('api_key', mode='before')
    @classmethod
    def validate_api_key(cls, v: str | None) -> str | SecretStr:
        """Validate API key is not empty when provider requires it."""
        if v is None:
            return SecretStr("")
        return SecretStr(v)
    
    
class AgentConfig(BaseModel):
    """Agent configuration settings."""
    
    name: str = Field(
        default=...,
        description="Name of the agent"
    )
    
    agent_type: str = Field(
        ...,
        description="Type of the agent"
    )

    # LLM configuration per-agent
    # 支持多个命名的 LLM 配置，键为配置名（例如: "executor", "planner"），值为 LLMConfig
    # 在环境变量中可以使用嵌套分隔符配置，例如: AGENTS__<agent_key>__llm__<llm_name>__provider=openai
    # 或者将整个 agents 字段设置为 JSON 字符串：
    # AGENTS='{"executor_agent": {"name": "executor_agent", "agent_type": "EXECUTOR", "llm": {"default": {"provider": "openai"}}}}'
    llm: dict[str, LLMConfig] = Field(default_factory=dict, description="Mapping of named LLM configurations")

    def get_llm_config(self, name: str = "default") -> LLMConfig:
        """获取命名的 LLM 配置，若不存在则返回名为 'default' 的配置或一个默认的 LLMConfig。

        Args:
            name: 配置名（例如 'executor'、'planner'），默认使用 'default'

        Returns:
            LLMConfig: 对应的 LLM 配置对象
        """
        cfg: LLMConfig | None = self.llm.get(name)
        if cfg is not None:
            return cfg
        # fallback to explicit default key
        cfg = self.llm.get("default")
        if cfg is not None:
            return cfg
        # return an empty/default instance
        return LLMConfig()


class Settings(BaseSettings):
    """Global application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        # Pydantic model settings
        validate_assignment=True,
        use_enum_values=True,
        frozen=False,
    )
    
    agents: dict[str, AgentConfig] = Field(
        default_factory=dict,
        description="Mapping of named agent configurations"
    )

    # Logging configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level"
    )

    log_file: str = Field(
        default="logs/app.log",
        description="Log file path"
    )

    retry_attempts: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Number of retry attempts for failed tasks"
    )

    # model_config contains pydantic settings (see above)

    def get_agent_config(self, name: str) -> AgentConfig | None:
        """获取命名的 Agent 配置。

        Args:
            name: 配置名

        Returns:
            Optional[AgentConfig]: 对应的 Agent 配置对象，若不存在则返回 None
        """
        return self.agents.get(name)


# Global singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """
    Get the global singleton Settings instance.

    Creates the instance on first call, subsequent calls return the same instance.

    Returns:
        Settings: The global settings instance
    """
    global _settings

    if _settings is None:
        _settings = Settings()

    return _settings


def reload_settings() -> Settings:
    """
    Reload settings from environment variables.

    This is useful for testing or when environment variables change at runtime.

    Returns:
        Settings: The new settings instance
    """
    global _settings
    _settings = Settings()
    return _settings
