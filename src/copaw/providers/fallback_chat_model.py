# -*- coding: utf-8 -*-
"""Fallback wrapper for ChatModel with multiple backup models.

This module provides a fallback mechanism that automatically switches to
backup models when the primary model fails. Each model in the chain
is tried in order until one succeeds or all models fail.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, List, Optional

from agentscope.model import ChatModelBase, _model_response
from ..providers import ProviderManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FallbackModelConfig:
    """Configuration for a single fallback model."""

    provider_id: str
    model: str
    name: str = ""  # Optional display name


@dataclass(frozen=True, slots=True)
class FallbackConfig:
    """Fallback model configuration."""

    enabled: bool = True
    fallback_models: List[FallbackModelConfig] = ()
    max_retries_per_model: int = 1  # Retries for each model before switching


class FallbackChatModel(ChatModelBase):
    """Chat model wrapper with automatic fallback to backup models.

    When the primary model fails, automatically tries backup models in order.
    Each model can be retried multiple times before switching to the next.

    Example:
        >>> fallback_config = FallbackConfig(
        ...     fallback_models=[
        ...         FallbackModelConfig("openai", "gpt-4", "GPT-4"),
        ...         FallbackModelConfig("anthropic", "claude-3", "Claude"),
        ...         FallbackModelConfig("ollama", "llama3", "Local Llama"),
        ...     ],
        ...     max_retries_per_model=2,
        ... )
        >>> model = FallbackChatModel(primary_model, fallback_config)
    """

    def __init__(
        self,
        primary_model: ChatModelBase,
        fallback_config: FallbackConfig,
    ) -> None:
        """Initialize with primary model and fallback configuration.

        Args:
            primary_model: The primary model instance to try first
            fallback_config: Fallback configuration with backup models
        """
        super().__init__(
            model_name=primary_model.model_name,
            stream=primary_model.stream,
        )
        self._primary = primary_model
        self._config = fallback_config

        # Cache for created fallback models (lazy initialization)
        self._fallback_models_cache: List[ChatModelBase] = []

    def _get_all_models(self) -> List[ChatModelBase]:
        """Get primary model plus all fallback models.

        Returns:
            List of model instances in order of preference
        """
        models = [self._primary]

        # Lazy load fallback models
        if not self._fallback_models_cache and self._config.fallback_models:
            manager = ProviderManager.get_instance()

            for fallback in self._config.fallback_models:
                try:
                    provider = manager.get_provider(fallback.provider_id)
                    if provider is None:
                        logger.warning(
                            f"Fallback provider '{fallback.provider_id}' "
                            f"not found, skipping",
                        )
                        continue

                    if provider.is_local:
                        from ..local_models import create_local_chat_model

                        model = create_local_chat_model(
                            model_id=fallback.model,
                            stream=True,
                            generate_kwargs={"max_tokens": None},
                        )
                    else:
                        model = provider.get_chat_model_instance(
                            fallback.model,
                        )

                    self._fallback_models_cache.append(model)
                    models.append(model)
                    logger.info(
                        f"Loaded fallback model: "
                        f"{fallback.provider_id}/{fallback.model}",
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to load fallback model "
                        f"{fallback.provider_id}/{fallback.model}: {e}",
                    )

        return models + self._fallback_models_cache

    async def __call__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> (
        _model_response.ChatResponse
        | AsyncGenerator[_model_response.ChatResponse, None]
    ):
        """Try models in order until one succeeds.

        Args:
            *args: Arguments to pass to the model
            **kwargs: Keyword arguments to pass to the model

        Returns:
            Response from the first successful model

        Raises:
            Exception: If all models fail
        """
        if not self._config.enabled or not self._config.fallback_models:
            # Fallback disabled, just use primary
            return await self._primary(*args, **kwargs)

        models = self._get_all_models()
        max_retries = self._config.max_retries_per_model

        last_exception: Optional[Exception] = None

        for model_idx, model in enumerate(models):
            model_name = getattr(model, "model_name", f"model_{model_idx}")
            is_primary = model_idx == 0

            for attempt in range(1, max_retries + 1):
                try:
                    result = await model(*args, **kwargs)

                    # Log successful fallback
                    if not is_primary:
                        logger.info(
                            f"✓ Fallback to {model_name} succeeded "
                            f"(primary failed, model "
                            f"{model_idx + 1}/{len(models)})",
                        )

                    # Handle streaming responses
                    if isinstance(result, AsyncGenerator):
                        return self._wrap_stream_with_fallback(
                            result,
                            model_idx,
                            models,
                            args,
                            kwargs,
                            max_retries,
                        )

                    return result

                except Exception as exc:
                    last_exception = exc

                    # Check if we should retry this model
                    if attempt < max_retries:
                        logger.warning(
                            f"Model {model_name} failed "
                            f"(attempt {attempt}/{max_retries}): "
                            f"{exc}. Retrying...",
                        )
                        await asyncio.sleep(1)  # Brief delay before retry
                        continue

                    # Check if we should switch to next model
                    if model_idx < len(models) - 1:
                        next_model_name = getattr(
                            models[model_idx + 1],
                            "model_name",
                            f"model_{model_idx + 1}",
                        )
                        logger.warning(
                            f"✗ Model {model_name} failed after "
                            f"{max_retries} attempts. "
                            f"Switching to fallback: {next_model_name}",
                        )
                    else:
                        logger.error(
                            f"✗ All models failed ({len(models)} "
                            f"models total). Last error from "
                            f"{model_name}: {exc}",
                        )

        # All models failed
        if last_exception:
            raise last_exception

        raise RuntimeError("All fallback models failed without exception")

    async def _wrap_stream_with_fallback(
        self,
        stream: AsyncGenerator,
        current_model_idx: int,
        all_models: List[ChatModelBase],
        call_args: tuple,
        call_kwargs: dict,
        max_retries: int,
    ) -> AsyncGenerator[_model_response.ChatResponse, None]:
        """Wrap streaming response with fallback support.

        If the stream fails mid-consumption, retry with the same model first,
        then switch to fallback models if needed.

        Args:
            stream: The current streaming response
            current_model_idx: Index of the current model in all_models
            all_models: List of all available models
            call_args: Original call arguments
            call_kwargs: Original call keyword arguments
            max_retries: Max retries per model

        Yields:
            Response chunks from the stream
        """
        current_model = all_models[current_model_idx]
        model_name = getattr(
            current_model,
            "model_name",
            f"model_{current_model_idx}",
        )

        try:
            async for chunk in stream:
                yield chunk

        except Exception as exc:
            logger.warning(
                f"Streaming from {model_name} failed: {exc}. "
                f"Attempting fallback...",
            )
            await stream.aclose()

            # Try remaining models for stream
            for next_model_idx in range(current_model_idx, len(all_models)):
                next_model = all_models[next_model_idx]
                next_model_name = getattr(
                    next_model,
                    "model_name",
                    f"model_{next_model_idx}",
                )

                if next_model_idx != current_model_idx:
                    logger.info(
                        f"Switching stream to fallback: " f"{next_model_name}",
                    )

                for attempt in range(1, max_retries + 1):
                    try:
                        result = await next_model(*call_args, **call_kwargs)

                        if isinstance(result, AsyncGenerator):
                            logger.info(
                                f"✓ Stream from {next_model_name} succeeded",
                            )
                            async for chunk in result:
                                yield chunk
                            return

                    except Exception as retry_exc:
                        logger.warning(
                            f"Stream retry {attempt}/{max_retries} for "
                            f"{next_model_name} failed: {retry_exc}",
                        )
                        await asyncio.sleep(1)

            # All models failed for streaming
            raise exc


__all__ = [
    "FallbackChatModel",
    "FallbackConfig",
    "FallbackModelConfig",
]
