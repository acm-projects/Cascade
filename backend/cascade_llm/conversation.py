"""One conversation class per provider.

The agent loop (agent.py) owns the policy - which tools to offer, pacing, the forced final
turn, the guard against tools that were not offered - and is provider-agnostic. Each class
here owns its provider's wire format and history:

  start(user_text)                      begin with the first user message
  take_turn(system, tools, tool_choice) one model call -> Turn
  add_tool_results(results)             feed tool outputs back

Tools are given in Anthropic's shape ({name, description, input_schema}); `tool_choice` is
None (auto), {"type": "any"} (must call a tool) or {"type": "tool", "name": X}.
AnthropicConversation sends exactly the history the agent always sent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .clients import ANTHROPIC, make_client, selected_model, selected_provider


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]
    error: str | None = None  # set when the model's arguments could not be parsed


@dataclass
class ToolResult:
    id: str
    blocks: list[dict[str, Any]]  # Anthropic-style: {"type": "text", ...} / {"type": "image", ...}
    is_error: bool = False


@dataclass
class Turn:
    text: str
    tool_calls: list[ToolCall]
    continue_loop: bool  # True if the model asked for tools and the loop should go on
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


# ---------------------------------------------------------------- Anthropic

def _block_to_dict(block: Any) -> dict[str, Any]:
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    if block.type == "thinking":
        # Must be passed back unchanged (signature included) when continuing a tool-use turn.
        return {"type": "thinking", "thinking": block.thinking, "signature": block.signature}
    if block.type == "redacted_thinking":
        return {"type": "redacted_thinking", "data": block.data}
    raise ValueError(f"Unexpected content block type: {block.type}")


class AnthropicConversation:
    def __init__(self, client: Any, model: str, max_tokens: int = 2048):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.messages: list[dict[str, Any]] = []

    def start(self, user_text: str) -> None:
        self.messages.append({"role": "user", "content": user_text})

    def take_turn(self, *, system: str, tools: list[dict], tool_choice: dict | None) -> Turn:
        kwargs: dict[str, Any] = {"tool_choice": tool_choice} if tool_choice else {}
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=tools,
            messages=self.messages,
            **kwargs,
        )
        self.messages.append({"role": "assistant", "content": [_block_to_dict(b) for b in response.content]})
        text = " ".join(b.text for b in response.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, b.input) for b in response.content if b.type == "tool_use"]
        usage = getattr(response, "usage", None)
        return Turn(
            text=text,
            tool_calls=calls,
            continue_loop=response.stop_reason == "tool_use" and bool(calls),
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
        )

    def add_tool_results(self, results: list[ToolResult]) -> None:
        self.messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.id,
                        "content": r.blocks,
                        **({"is_error": True} if r.is_error else {}),
                    }
                    for r in results
                ],
            }
        )


# ------------------------------------------------------------------- OpenAI

def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from an SDK object or a plain dict (tests use both)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _image_url(block: dict[str, Any]) -> str:
    source = block.get("source", {})
    if source.get("type") == "url":
        return source["url"]
    return f"data:{source.get('media_type', 'image/jpeg')};base64,{source['data']}"


def blocks_to_openai_content(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anthropic-style blocks -> OpenAI input_text / input_image items, order preserved."""
    content: list[dict[str, Any]] = []
    for b in blocks:
        if b.get("type") == "text":
            content.append({"type": "input_text", "text": b["text"]})
        elif b.get("type") == "image":
            content.append({"type": "input_image", "image_url": _image_url(b)})
    return content


def _tool_to_openai(tool: dict[str, Any]) -> dict[str, Any]:
    # strict=False: our schemas have optional fields and no additionalProperties=false.
    return {
        "type": "function",
        "name": tool["name"],
        "description": tool.get("description", ""),
        "parameters": tool["input_schema"],
        "strict": False,
    }


def _choice_to_openai(choice: dict | None) -> Any:
    if not choice:
        return "auto"
    if choice.get("type") == "tool":
        return {"type": "function", "name": choice["name"]}
    return "required"  # {"type": "any"}


class OpenAIConversation:
    """Responses API conversation. History is our own list of input items: every response item
    (including reasoning items) is appended and sent back, then one function_call_output per call.

    Images in tool results: `image_mode="user_message"` (fixed default) sends the tool's text as the
    output and the frames in a following user message; `"array"` puts input_image items inside the
    function_call_output instead (only used by tests and scripts/check_openai.py).
    """

    REASONING_EFFORT = "low"

    def __init__(
        self,
        client: Any,
        model: str,
        image_mode: str = "user_message",
        max_output_tokens: int = 16000,  # reasoning tokens count against this
    ):
        self.client = client
        self.model = model
        self.image_mode = image_mode
        if self.image_mode not in ("array", "user_message"):
            raise ValueError("image_mode must be 'array' or 'user_message'")
        self.max_output_tokens = max_output_tokens
        self.input: list[Any] = []

    def start(self, user_text: str) -> None:
        self.input.append({"role": "user", "content": user_text})

    def take_turn(self, *, system: str, tools: list[dict], tool_choice: dict | None) -> Turn:
        response = self.client.responses.create(
            model=self.model,
            instructions=system,
            input=self.input,
            tools=[_tool_to_openai(t) for t in tools],
            tool_choice=_choice_to_openai(tool_choice),
            reasoning={"effort": self.REASONING_EFFORT},
            max_output_tokens=self.max_output_tokens,
        )
        status = _get(response, "status")
        if status == "incomplete":
            reason = _get(_get(response, "incomplete_details"), "reason") or "incomplete"
            raise RuntimeError(f"OpenAI response was cut off ({reason}).")
        if status == "failed":
            message = _get(_get(response, "error"), "message") or "unknown error"
            raise RuntimeError(f"OpenAI request failed: {message}")

        output = list(_get(response, "output") or [])
        self.input.extend(output)  # reasoning items must go back with the tool outputs

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for item in output:
            kind = _get(item, "type")
            if kind == "function_call":
                call = ToolCall(id=_get(item, "call_id"), name=_get(item, "name"), input={})
                try:
                    parsed = json.loads(_get(item, "arguments") or "{}")
                    if not isinstance(parsed, dict):
                        raise ValueError("arguments must be a JSON object")
                    call.input = parsed
                except ValueError as exc:
                    call.error = f"Invalid JSON arguments for {call.name}: {exc}"
                calls.append(call)
            elif kind == "message":
                for part in _get(item, "content") or []:
                    ptype = _get(part, "type")
                    if ptype == "output_text":
                        text_parts.append(_get(part, "text") or "")
                    elif ptype == "refusal":
                        text_parts.append(_get(part, "refusal") or "")

        usage = _get(response, "usage")
        details = _get(usage, "input_tokens_details")
        return Turn(
            text=" ".join(t for t in text_parts if t),
            tool_calls=calls,
            continue_loop=bool(calls),
            input_tokens=_get(usage, "input_tokens", 0) or 0,
            output_tokens=_get(usage, "output_tokens", 0) or 0,
            cached_tokens=_get(details, "cached_tokens", 0) or 0,
        )

    def add_tool_results(self, results: list[ToolResult]) -> None:
        followup: list[dict[str, Any]] = []
        for r in results:
            content = blocks_to_openai_content(r.blocks)
            has_images = any(c["type"] == "input_image" for c in content)
            prefix = "ERROR: " if r.is_error else ""
            if has_images and self.image_mode == "array":
                if prefix:
                    content.insert(0, {"type": "input_text", "text": prefix.strip()})
                output: Any = content
            else:
                text = "\n".join(c["text"] for c in content if c["type"] == "input_text")
                if has_images:
                    text += "\n(The frames from this call are attached in the next message.)"
                    followup.append({"type": "input_text", "text": f"Frames returned by call {r.id}:"})
                    followup.extend(content)
                output = (prefix + text) or "(no output)"
            self.input.append({"type": "function_call_output", "call_id": r.id, "output": output})
        if followup:
            self.input.append({"role": "user", "content": followup})


def make_conversation(client: Any = None) -> AnthropicConversation | OpenAIConversation:
    """Conversation for the provider chosen by LLM_PROVIDER. An injected `client` is used as-is."""
    provider = selected_provider()
    model = selected_model()
    if provider == ANTHROPIC:
        return AnthropicConversation(client or make_client(provider), model)
    return OpenAIConversation(client or make_client(provider), model)
