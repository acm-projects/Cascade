"""Shared Anthropic client factory for the agent and the transcript summarizer.

Honors the same ANTHROPIC_CALLS_DISABLED kill switch as trends/pipeline.py, and
reads the key at call time so a key added to .env applies to the next job.
"""

from __future__ import annotations

import os

import anthropic


def calls_disabled() -> bool:
    return os.environ.get("ANTHROPIC_CALLS_DISABLED", "").lower() in ("1", "true", "yes")


def make_client() -> anthropic.Anthropic:
    if calls_disabled():
        raise RuntimeError("Anthropic API calls are disabled (ANTHROPIC_CALLS_DISABLED=true in .env).")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=api_key)


# USD per million tokens: (input, output) for prompts <=100k tokens and >100k tokens.
PRICING_PER_MTOK = {
    "claude-haiku-5-5": {"small": (0.10, 0.50), "large": (0.50, 2.50)},
}
LARGE_PROMPT_TOKENS = 100_000


def call_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimated USD for one API call, or None if we have no price for the model."""
    rates = PRICING_PER_MTOK.get(model)
    if rates is None:
        return None
    r_in, r_out = rates["large" if input_tokens > LARGE_PROMPT_TOKENS else "small"]
    return (input_tokens * r_in + output_tokens * r_out) / 1_000_000
