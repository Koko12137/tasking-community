"""LLM utility functions for building and converting provider-specific configurations."""

from .const import Provider
from .interface import ILLM, IEmbedModel
from ..model.setting import LLMConfig


def build_llm(config: LLMConfig) -> ILLM:
    """根据配置构建对应的语言模型实例

    参数:
        config (LLMConfig): 语言模型配置

    返回:
        ILLM: 语言模型实例
    """
    provider = Provider(config.provider)

    if provider == Provider.OPENAI:
        from .openai import OpenAiLLM
        llm = OpenAiLLM
    elif provider == Provider.ANTHROPIC:
        from .anthropic import AnthropicLLM
        llm = AnthropicLLM
    elif provider == Provider.ARK:
        from .ark import ArkLLM
        llm = ArkLLM
    elif provider == Provider.ZHIPU:
        from .zhipu import ZhipuLLM
        llm = ZhipuLLM
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    # 返回实例
    return llm.from_config(config=config)


def build_embed_model(config: LLMConfig) -> IEmbedModel:
    """根据配置构建对应的嵌入模型实例

    参数:
        config (LLMConfig): 嵌入模型配置

    返回:
        IEmbedModel: 嵌入模型实例
    """
    provider = Provider(config.provider)

    if provider == Provider.OPENAI:
        from .openai import OpenAiEmbeddingLLM
        embed_model = OpenAiEmbeddingLLM
    elif provider == Provider.ANTHROPIC:
        from .anthropic import AnthropicEmbeddingLLM
        embed_model = AnthropicEmbeddingLLM
    elif provider == Provider.ZHIPU:
        from .zhipu import ZhipuEmbeddingLLM
        embed_model = ZhipuEmbeddingLLM
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    # 返回实例
    return embed_model.from_config(config=config)