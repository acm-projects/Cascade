"""Provider selection, client factories, kill switches and pricing for every LLM call site.

The provider is inferred from the model id, so a mismatched provider/model pair is impossible:
`claude-*` -> Anthropic, `gpt-*` / `o1` / `o3` / `o4` -> OpenAI. An unrecognized id falls back to
LLM_PROVIDER if set, else Anthropic (the default).
"""

from __future__ import annotations

import os
from typing import Any

ANTHROPIC = "anthropic"
OPENAI = "openai"

_OPENAI_PREFIXES = ("gpt-", "chatgpt", "o1", "o3", "o4", "codex")


def provider_for_model(model: str) -> str:
    name = (model or "").strip().lower()
    if name.startswith(_OPENAI_PREFIXES):
        return OPENAI
    if name.startswith("claude"):
        return ANTHROPIC
    override = os.environ.get("LLM_PROVIDER", "").strip().lower()
    return override if override in (ANTHROPIC, OPENAI) else ANTHROPIC


def _env_names(provider: str) -> tuple[str, str]:
    return (f"{provider.upper()}_API_KEY", f"{provider.upper()}_CALLS_DISABLED")


def provider_label(provider: str) -> str:
    return "OpenAI" if provider == OPENAI else "Anthropic"


def calls_disabled(provider: str) -> bool:
    """Per-provider kill switch (ANTHROPIC_CALLS_DISABLED / OPENAI_CALLS_DISABLED), read at call time."""
    return os.environ.get(_env_names(provider)[1], "").lower() in ("1", "true", "yes")


def make_client(provider: str) -> Any:
    """Build a client, reading the key now (not at import) so a key added to .env applies to the
    next job. Raises RuntimeError with a message that is safe to show the user."""
    key_name, disabled_name = _env_names(provider)
    if calls_disabled(provider):
        raise RuntimeError(f"{provider_label(provider)} API calls are disabled ({disabled_name}=true in .env).")
    api_key = os.environ.get(key_name, "").strip()
    if not api_key:
        raise RuntimeError(f"{key_name} is not set")
    if provider == OPENAI:
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise RuntimeError("The openai package is not installed (pip install openai).") from exc
        return openai.OpenAI(api_key=api_key)
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


# USD per million tokens. Each entry: the prompt size above which the "large" rates apply, and
# (<=threshold, >threshold) pairs for input, output and cached input. Cached input is OpenAI's
# automatic prompt-cache discount; Anthropic's is listed for completeness (we do not use it).
PRICING: dict[str, dict[str, Any]] = {
    "claude-haiku-5-5": {
        "threshold": 100_000,
        "input": (0.10, 0.50),
        "output": (0.50, 2.50),
        "cached": (0.01, 0.05),
    },
    "gpt-6-luna": {
        # per developers.openai.com: prompts over 272K input tokens cost 2x input/cache, 1.5x output
        "threshold": 272_000,
        "input": (0.10, 0.20),
        "output": (0.50, 0.75),
        "cached": (0.01, 0.02),
    },
}


def call_cost(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float | None:
    """Estimated USD for one API call, or None when we have no price for the model.

    `input_tokens` is the total prompt size; `cached_tokens` of it are billed at the cached rate.
    """
    price = PRICING.get(model)
    if price is None:
        return None
    tier = 1 if input_tokens > price["threshold"] else 0
    cached = max(0, min(cached_tokens, input_tokens))
    uncached = input_tokens - cached
    return (
        uncached * price["input"][tier] + cached * price["cached"][tier] + output_tokens * price["output"][tier]
    ) / 1_000_000
