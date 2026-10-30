"""One structured-JSON call (a prompt, optional images, a JSON schema) on either provider.

Used by generation features, summaries, social copy, and editor chat.
OpenAI schemas must satisfy strict mode: additionalProperties=false and every property required.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .clients import OPENAI, MODELS, LLMConfigError, make_client, selected_model, selected_provider


@dataclass
class StructuredResult:
    data: dict[str, Any]
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0


def structured_json(
    prompt: str,
    schema: dict[str, Any],
    *,
    name: str,
    images: list[dict[str, str]] | None = None,  # [{"media_type": "image/jpeg", "data": <base64>}]
    effort: str = "low",
    max_output_tokens: int = 4096,  # reasoning tokens count against this on both providers
    client: Any = None,
    provider: str | None = None,
) -> StructuredResult:
    # Per-call overrides never mutate the process environment or affect other jobs.
    model = selected_model() if provider is None else MODELS.get(provider)
    provider = provider or selected_provider()
    if model is None:
        raise LLMConfigError('Provider must be anthropic or openai.')
    client = client or make_client(provider)
    if provider == OPENAI:
        return _openai(client, model, prompt, schema, name, images or [], effort, max_output_tokens)
    return _anthropic(client, model, prompt, schema, images or [], effort, max_output_tokens)


def _anthropic(client, model, prompt, schema, images, effort, max_tokens) -> StructuredResult:
    content: Any = prompt
    if images:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": i["media_type"], "data": i["data"]}}
            for i in images
        ] + [{"type": "text", "text": prompt}]
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": content}],
    )
    # Haiku 5.5 thinks by default, so the JSON is the text block - skip thinking blocks.
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise ValueError("model returned no text block")
    usage = getattr(response, "usage", None)
    return StructuredResult(
        data=json.loads(text),
        input_tokens=getattr(usage, "input_tokens", 0),
        output_tokens=getattr(usage, "output_tokens", 0),
    )


def _openai(client, model, prompt, schema, name, images, effort, max_output_tokens) -> StructuredResult:
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    content += [
        {"type": "input_image", "image_url": f"data:{i['media_type']};base64,{i['data']}"} for i in images
    ]
    response = client.responses.create(
        model=model,
        store=False,
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
        reasoning={"effort": effort},
        max_output_tokens=max_output_tokens,
    )
    status = getattr(response, "status", None)
    if status == "incomplete":
        details = getattr(response, "incomplete_details", None)
        raise RuntimeError(f"OpenAI response was cut off ({getattr(details, 'reason', None) or 'incomplete'}).")

    text = None
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "refusal":
                raise RuntimeError(f"OpenAI refused the request: {getattr(part, 'refusal', '')}")
            if getattr(part, "type", None) == "output_text":
                text = part.text
    if text is None:
        raise ValueError("model returned no text output")

    usage = getattr(response, "usage", None)
    details = getattr(usage, "input_tokens_details", None)
    return StructuredResult(
        data=json.loads(text),
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cached_tokens=getattr(details, "cached_tokens", 0) or 0,
    )
