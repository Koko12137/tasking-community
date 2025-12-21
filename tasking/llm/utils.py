"""LLM utility functions for building and converting provider-specific configurations."""

import asyncio
from typing import Any, Callable, Coroutine, ParamSpec, TypeVar, cast
from functools import wraps

from loguru import logger
from tenacity import stop_after_attempt, wait_exponential, AsyncRetrying, RetryError

from .const import Provider
from .interface import ILLM, IEmbedModel
from ..model.setting import LLMConfig

P = ParamSpec('P')
T = TypeVar('T')

def timeout_retry_async(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    timeout: float = 120.0,
) -> Callable[[Callable[P, Coroutine[Any, Any, T]]], Callable[P, Coroutine[Any, Any, T]]]:
    """Decorator for adding timeout and retry logic to async functions using tenacity.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Base delay between retries in seconds (default: 1.0)
        max_delay: Maximum delay between retries in seconds (default: 60.0)
        timeout: Timeout for each attempt in seconds (default: 120.0)

    Returns:
        Decorated function with timeout and retry logic
    """
    def decorator(func: Callable[P, Coroutine[Any, Any, T]]) -> Callable[P, Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(max_retries + 1),
                    wait=wait_exponential(multiplier=base_delay, min=base_delay, max=max_delay),
                    before_sleep=lambda rs: logger.warning(
                        f"Timeout on attempt {rs.attempt_number} for {func.__name__}. "
                        f"Retrying in {rs.next_action.sleep if rs.next_action else 'unknown':.2f}s..."
                    ),
                    reraise=True
                ):
                    with attempt:
                        # Add timeout to each attempt
                        return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            except RetryError as e:
                exception = e.last_attempt.exception() if e.last_attempt and e.last_attempt.exception() else Exception("Unknown error")
                logger.error(f"All retry attempts failed for {func.__name__}: {exception}")
                if exception is None:
                    exception = Exception("Unknown error")
                raise exception
            except Exception as e:
                # Re-raise any other exception
                raise e

            # This should never be reached, but added for type checker
            assert False, "Unreachable code reached"

        return wrapper
    return decorator


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
