from enum import Enum


class Provider(str, Enum):
    """LLM providers enumeration. Now includes:
    - OPENAI: OpenAI provider
    - ANTHROPIC: Anthropic provider
    - ARK: Ark provider
    - ZHIPU: Zhipu AI provider
    """
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    ARK = "ark"
    ZHIPU = "zhipu"
