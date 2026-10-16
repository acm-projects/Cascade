"""Which LLM every call site uses, plus client creation and pricing.

ONE setting chooses the provider for everything (the agent, the transcript summaries and the
Trends tab):  LLM_PROVIDER=anthropic (default) or openai.  The model is fixed per provider
(MODELS below) - there are no per-feature model settings and no model names to edit in .env.
"""

from __future__ import annotations

import os
from typing import Any

ANTHROPIC = "anthropic"
OPENAI = "openai"


class LLMConfigError(RuntimeError):
    """A setup problem (missing key, bad LLM_PROVIDER) with a message that is safe to show a user."""


# One fixed model per provider.
MODELS: dict[str, str] = {
    ANTHROPIC: "claude-haiku-5-5",
    OPENAI: "gpt-6-luna",
}


def selected_provider() -> str:
    """The provider chosen by LLM_PROVIDER, read at call time (default: anthropic)."""
    value = os.environ.get("LLM_PROVIDER", "").strip().lower() or ANTHROPIC
    if value not in MODELS:
        raise LLMConfigError(f"LLM_PROVIDER must be 'anthropic' or 'openai' (got '{value}').")
    return value


def selected_model() -> str:
    return MODELS[selected_provider()]


def make_client(provider: str | None = None) -> Any:
    """Build the client for the selected provider. The key is read now (not at import), so a key
    added to .env applies to the next job. Raises RuntimeError with a message safe to show."""
    provider = provider or selected_provider()
    key_name = f"{provider.upper()}_API_KEY"
    api_key = os.environ.get(key_name, "").strip()
    if not api_key:
        raise LLMConfigError(f"{key_name} is not set (LLM_PROVIDER is '{provider}').")
    if provider == OPENAI:
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise LLMConfigError("The openai package is not installed (pip install openai).") from exc
        return openai.OpenAI(api_key=api_key)
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


# USD per million tokens. Each entry: the prompt size above which the "large" rates apply, and
# (<=threshold, >threshold) pairs for input, output, cached input (cache READS) and cache WRITES.
# Prompt caching: reads cost 0.1x the input rate, newly cached tokens cost 1.25x (both providers).
PRICING: dict[str, dict[str, Any]] = {
    "claude-haiku-5-5": {
        "threshold": 100_000,
        "input": (0.10, 0.50),
        "output": (0.50, 2.50),
        "cached": (0.01, 0.05),
        "cache_write": (0.125, 0.625),  # 5-minute cache, from the Anthropic pricing page
    },
    "gpt-6-luna": {
        # per developers.openai.com: prompts over 272K input tokens cost 2x input/cache, 1.5x output
        "threshold": 272_000,
        "input": (0.10, 0.20),
        "output": (0.50, 0.75),
        "cached": (0.01, 0.02),
        "cache_write": (0.125, 0.25),  # 1.25x input (developers.openai.com prompt caching guide)
    },
}


def call_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float | None:
    """Estimated USD for one API call, or None when we have no price for the model.

    `input_tokens` is the TOTAL prompt size. Of it, `cached_tokens` were read from the prompt cache
    (cheap) and `cache_write_tokens` were newly written to it (1.25x); the rest is ordinary input.
    The price tier is picked from the total prompt size.
    """
    price = PRICING.get(model)
    if price is None:
        return None
    tier = 1 if input_tokens > price["threshold"] else 0
    cached = max(0, min(cached_tokens, input_tokens))
    written = max(0, min(cache_write_tokens, input_tokens - cached))
    ordinary = input_tokens - cached - written
    return (
        ordinary * price["input"][tier]
        + cached * price["cached"][tier]
        + written * price["cache_write"][tier]
        + output_tokens * price["output"][tier]
    ) / 1_000_000
