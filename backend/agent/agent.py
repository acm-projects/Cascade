"""The agent loop: Claude first calls get_overview (forced), then uses search_video /
inspect_clip / suggest_clip until it has committed to enough clips or runs out of turns."""

from __future__ import annotations

import os
from typing import Any, Callable

from .anthropic_client import call_cost, make_client
from .tools import OVERVIEW_ONLY_SCHEMAS, SUGGEST_ONLY_SCHEMAS, TOOL_SCHEMAS, ToolBox

# Working turns after the forced overview turn.
MAX_ITERATIONS = 5
TARGET_SUGGESTIONS = 3
AGENT_MODEL = os.environ.get("AGENT_MODEL", "claude-haiku-5-5")

SYSTEM_PROMPT = f"""You find the best short-form clips in a video for a given category (e.g. "funny", "interesting").

Your first action is always get_overview (it is called for you on the first turn). For a short video it gives you the full transcript; for a long one (a podcast, an interview) it gives you an outline: per-chunk summaries with notable lines and exact timestamps. Either way you also get a few sample frames. Read it carefully - it tells you what this video is about, who is speaking and where candidate moments might be. Base your searches on THIS video, not on generic ideas.

After the overview you have {MAX_ITERATIONS} turns and must end with up to {TARGET_SUGGESTIONS} distinct suggested clips.
Tools:
- search_video: embedding search over the video. Visual search (CLIP) understands concrete things on screen, NOT abstract words like "funny" - so write concrete queries about what you saw in the overview (e.g. "chef dropping a pan", "audience laughing"). Speech mode searches the transcript by meaning - good for punchlines, jokes, surprising statements and topics. For talk-heavy videos lean on speech mode.
- read_transcript: read the exact words (with speaker labels) for a time range, up to 10 minutes at a time. Use it on the stretches the outline or a search hit points to - the outline summarizes, this shows what was actually said.
- inspect_clip: look at frames and the transcript of a time range. Verify candidates before suggesting them.
- suggest_clip: commit a clip (5-60s) that starts and ends at natural sentence boundaries, with a little setup before the payoff. Give a specific reason.

Be efficient: call several tools in the same turn (e.g. multiple searches at once, or inspecting several candidates at once). Do not spend turns narrating. If your searches are returning weak or irrelevant results, say so honestly in your suggestions' scores instead of inventing a justification."""

LAST_TURN_NOTE = (
    "\n\nThis is your FINAL turn: only suggest_clip is available. Commit your best remaining "
    "candidates now using what you have learned."
)


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


def run_agent(
    toolbox: ToolBox,
    category: str,
    progress: Callable[[str], None] | None = None,
    client: Any = None,
) -> dict[str, Any]:
    emit = progress or (lambda msg: None)

    if client is None:
        client = make_client()

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                f"Find the top {TARGET_SUGGESTIONS} '{category}' clips in this video "
                f"(duration {toolbox.index.duration:.1f}s)."
            ),
        }
    ]
    final_text = ""
    # Start from what transcript summarization already spent (zero when cached / short video).
    prior = getattr(toolbox.index, "summary_usage", None) or {}
    usage = {
        "input_tokens": prior.get("input_tokens", 0),
        "output_tokens": prior.get("output_tokens", 0),
        "cost_usd": prior.get("cost_usd", 0.0),
        "cost_known": prior.get("cost_known", True),
        "transcription_cost_usd": getattr(toolbox.index, "transcription_cost_usd", 0.0),
    }

    def record_usage(response: Any) -> str:
        u = getattr(response, "usage", None)
        if u is None:
            return ""
        in_tok, out_tok = u.input_tokens, u.output_tokens
        usage["input_tokens"] += in_tok
        usage["output_tokens"] += out_tok
        cost = call_cost(AGENT_MODEL, in_tok, out_tok)
        if cost is None:
            usage["cost_known"] = False
        else:
            usage["cost_usd"] += cost
        return f" [{in_tok} in / {out_tok} out tokens]"

    def take_turn(label: str, tools: list, system: str, tool_choice: dict | None) -> bool:
        """One model call plus tool execution. Returns True if tools were run (loop continues)."""
        nonlocal final_text
        emit(label)
        kwargs: dict[str, Any] = {"tool_choice": tool_choice} if tool_choice else {}
        response = client.messages.create(
            model=AGENT_MODEL,
            max_tokens=2048,
            system=system,
            tools=tools,
            messages=messages,
            **kwargs,
        )
        emit(f"{label} done{record_usage(response)}")
        messages.append({"role": "assistant", "content": [_block_to_dict(b) for b in response.content]})
        text_parts = [b.text for b in response.content if b.type == "text"]
        if text_parts:
            final_text = " ".join(text_parts)

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_uses:
            return False

        results = []
        for block in tool_uses:
            emit(f"Tool call: {block.name}({_short_args(block.input)})")
            content, is_error = toolbox.call(block.name, block.input)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                    **({"is_error": True} if is_error else {}),
                }
            )
        messages.append({"role": "user", "content": results})
        return True

    # Turn 0: the overview is always the first call, and only the overview is offered.
    if not take_turn(
        "Agent: getting video overview",
        OVERVIEW_ONLY_SCHEMAS,
        SYSTEM_PROMPT,
        {"type": "tool", "name": "get_overview"},
    ):
        return {"suggestions": [], "summary": final_text, "iterations": 0, "usage": _usage_summary(usage)}

    iterations = 0
    for i in range(MAX_ITERATIONS):
        iterations = i + 1
        last_turn = i == MAX_ITERATIONS - 1
        keep_going = take_turn(
            f"Agent turn {iterations}/{MAX_ITERATIONS}",
            SUGGEST_ONLY_SCHEMAS if last_turn else TOOL_SCHEMAS,
            SYSTEM_PROMPT + (LAST_TURN_NOTE if last_turn else ""),
            {"type": "any"} if last_turn else None,
        )
        if not keep_going or len(toolbox.suggestions) >= TARGET_SUGGESTIONS:
            break

    suggestions = sorted(toolbox.suggestions, key=lambda s: s["score"], reverse=True)
    return {
        "suggestions": suggestions,
        "summary": final_text,
        "iterations": iterations,
        "usage": _usage_summary(usage),
    }


def _usage_summary(usage: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "model": AGENT_MODEL,
        # LLM cost + Deepgram transcription (this run only; 0 when the transcript was cached).
        # None when we have no price for the configured model.
        "estimated_cost_usd": (
            round(usage["cost_usd"] + usage["transcription_cost_usd"], 5) if usage["cost_known"] else None
        ),
        "transcription_cost_usd": round(usage["transcription_cost_usd"], 5),
    }


def _short_args(args: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in args.items() if k != "reason")
