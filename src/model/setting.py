"""
Global settings management using Pydantic.

This module provides a singleton Settings class that loads configuration
from environment variables and .env files.
"""
import os
from pathlib import Path
from typing import Literal, Any

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> str | None:
    """
    Find the .env file by searching multiple possible locations.

    Search order:
    1. Path specified by TASKING_ENV_FILE environment variable
    2. Current working directory (.env)
    3. Project root directory (where setup.py/pyproject.toml exists) (.env)
    4. Parent of src/ directory (.env) - for development structure
    5. Package installation directory (.env) - when installed as package

    Returns:
        str | None: Path to .env file if found, None otherwise
    """
    # 1. Check custom path from environment variable
    custom_path = os.getenv('TASKING_ENV_FILE')
    if custom_path and Path(custom_path).exists():
        return custom_path

    # 2. Current working directory
    cwd = Path.cwd()
    env_file = cwd / '.env'
    if env_file.exists():
        return str(env_file)

    # 3. Project root directory (where setup.py or pyproject.toml exists)
    current = cwd
    for _ in range(5):  # Search up to 5 levels
        if (current / 'setup.py').exists() or (current / 'pyproject.toml').exists():
            env_file = current / '.env'
            if env_file.exists():
                return str(env_file)
            break
        current = current.parent

    # 4. Check if we're in a development structure (src/ directory exists)
    # tasking/src/model/setting.py -> go up to find src/ parent
    this_file = Path(__file__).resolve()

    # Try to find the project root from the file location
    # This works for both development and installed package scenarios
    possible_root = this_file

    # Search up to find either setup.py/pyproject.toml or tasking package boundary
    for _ in range(10):  # Search up to 10 levels
        parent = possible_root.parent
        if (parent / 'setup.py').exists() or (parent / 'pyproject.toml').exists():
            # Found project root, check for .env
            env_file = parent / '.env'
            if env_file.exists():
                return str(env_file)
            break
        # Check if we've reached a boundary where tasking package might be installed
        if (parent / 'tasking').is_dir() and this_file.is_relative_to(parent / 'tasking'):
            # We're inside the tasking package, check package root
            env_file = parent / 'tasking' / '.env'
            if env_file.exists():
                return str(env_file)
        possible_root = parent

    # 5. Package directory when installed as a package
    # Find the tasking package root by going up from current file
    package_root = this_file
    for _ in range(8):  # Search up to 8 levels to find package root
        if package_root.name == 'tasking':
            env_file = package_root / '.env'
            if env_file.exists():
                return str(env_file)
            break
        if package_root.parent == package_root:  # Reached filesystem root
            break
        package_root = package_root.parent

    # Final attempt: check common installation locations
    home = Path.home()
    common_locations = [
        home / '.env',
        home / '.tasking' / '.env',
        Path('/etc/tasking/.env'),
        Path('/usr/local/etc/tasking/.env')
    ]

    for location in common_locations:
        if location.exists():
            return str(location)

    return None


def _load_env_file(env_file_path: str) -> None:
    """
    Manually load a .env file by reading and setting environment variables.

    Args:
        env_file_path: Path to the .env file to load
    """
    with open(env_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Split on first '=' only
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                # Remove surrounding quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]

                # Set in environment if not already set
                if key and key not in os.environ:
                    os.environ[key] = value


class LLMConfig(BaseModel):
    """LLM configuration settings."""

    provider: str = Field(
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

    timeout: int = Field(
        default=60,
        ge=1,
        le=600,
        description="Request timeout in seconds"
    )
    
    extra_body: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra body parameters to include in LLM requests"
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
        default=...,
        description="Type of the agent"
    )

    llm: dict[str, LLMConfig] = Field(
        default_factory=dict,
        description="Mapping of named LLM configurations"
    )
    """获取命名的 LLM 配置，若不存在则返回名为 'default' 的配置或一个默认的 LLMConfig。
    在环境变量中，可以使用嵌套分隔符配置，例如:
        AGENTS__<agent_key>__llm__<llm_name>__provider，或者将整个 llm 字段设置为 JSON 字符串。
    
    Args:
        name: 配置名（例如 'thinking'、'orchestrating'），agent 会通过当前工作流的的阶段获取llm，
            如果没有独立配置则默认使用 'default'

    Returns:
        LLMConfig: 对应的 LLM 配置对象
    """

    def get_llm_config(self, name: str = "default") -> LLMConfig:
        """获取命名的 LLM 配置，若不存在则返回名为 'default' 的配置或一个默认的 LLMConfig。

        Args:
            name: 配置名（例如 'thinking'、'orchestrating'），默认使用 'default'

        Returns:
            LLMConfig: 对应的 LLM 配置对象
        """
        # Try to get the named configuration
        # Access the dict through the model instance attribute
        cfg = getattr(self, 'llm', {}).get(name)
        if cfg is not None:
            return cfg
        # fallback to explicit default key
        cfg = getattr(self, 'llm', {}).get("default")
        if cfg is not None:
            return cfg
        # return an empty/default instance
        return LLMConfig()


class Settings(BaseSettings):
    """Global application settings."""

    model_config = SettingsConfigDict(
        env_file=None,  # We'll handle .env file loading manually
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        # Pydantic model settings
        validate_assignment=True,
        use_enum_values=True,
        frozen=False,
    )

    def __init__(self, **kwargs: Any):
        """Initialize Settings with automatic .env file loading."""
        # Find .env file path
        env_file_path = _find_env_file()

        # If .env file found, load it first before initializing
        if env_file_path:
            # Manually load .env file
            _load_env_file(env_file_path)

        # Initialize the Settings instance
        super().__init__(**kwargs)

    agents: dict[str, AgentConfig] = Field(
        default_factory=dict,
        description="Mapping of named agent configurations"
    )
    
    embeddings: dict[str, LLMConfig] = Field(
        default_factory=dict,
        description="Mapping of named embedding model configurations"
    )
    """获取命名的嵌入模型配置，在环境变量中，可以使用嵌套分隔符配置，例如:
        EMBEDDINGS__<embed_model_name>__provider，或者将整个嵌入模型字段设置为 JSON 字符串。
        
    Args:
        name: 嵌入模型配置名
        
    Returns:
        LLMConfig: 对应的嵌入模型配置对象    
    """

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
        # Access the agents dict through the model instance attribute
        agents_dict = getattr(self, 'agents', {})
        return agents_dict.get(name)
    
    def get_embedding_config(self, name: str) -> LLMConfig:
        """获取命名的嵌入模型配置。

        Args:
            name: 嵌入模型配置名

        Returns:
            LLMConfig: 对应的嵌入模型配置对象，若不存在则返回一个默认的 LLMConfig
        """
        # Access the embeddings dict through the model instance attribute
        cfg = getattr(self, 'embeddings', {}).get(name)
        if cfg is not None:
            return cfg
        # return an empty/default instance
        return LLMConfig()


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
