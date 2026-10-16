"""The agent loop: the model (Claude or OpenAI, chosen by LLM_PROVIDER) first calls get_overview
(forced), then gathers a pool of candidate
moments from across the whole video (search_video / read_transcript / inspect_clip /
add_candidate), compares them, and ranks them (rank_candidates). Code then picks the best
TARGET_CLIPS from that ranking, spread out through the video."""

from __future__ import annotations

import logging
from typing import Any, Callable

from backend.cascade_llm import ToolResult, call_cost, make_conversation, selected_model
from . import research
from .tools import (
    FINAL_SCHEMAS,
    MAX_CLIP_SECONDS,
    MIN_CLIP_SECONDS,
    OVERVIEW_ONLY_SCHEMAS,
    TARGET_CLIPS,
    TOOL_SCHEMAS,
    ToolBox,
)

logger = logging.getLogger("cascade_agent")

# Working turns after the forced overview turn.
MAX_ITERATIONS = 8
TARGET_SUGGESTIONS = TARGET_CLIPS  # final clips returned (set in tools.py)

SYSTEM_PROMPT = f"""You find the {TARGET_SUGGESTIONS} best clips of a whole video for a given category (e.g. "funny", "interesting"). They must be the best of the ENTIRE video and spread out through it - not four moments from the same stretch.

Your first action is always get_overview (it is called for you on the first turn). For a short video it gives you the full transcript; for a long one (a podcast, an interview) it gives you an outline: per-chunk summaries with notable lines and exact timestamps. Either way you also get a few sample frames. Read it carefully - it tells you what this video is about, who is speaking and where candidate moments might be. Base your searches on THIS video, not on generic ideas.

How to work (you have {MAX_ITERATIONS} turns after the overview):
1. FIND candidates across the whole video - aim for roughly {2 * TARGET_SUGGESTIONS}-{3 * TARGET_SUGGESTIONS}, from every part of it, not just the first stretch you look at. Verify promising ones, and ADD each one with add_candidate as soon as you have confirmed it - do not save all the adding for later. If add_candidate rejects a clip (too long, overlapping), fix it and add it again right away.
2. COMPARE them head-to-head: which is actually funnier / stronger, and why. Do not just rank by the order you found them.
3. RANK with rank_candidates (best first, with a short note on why each beats the one below it). Code then takes the top {TARGET_SUGGESTIONS} from your ranking, skipping any pick that is too close in time to a better-ranked one - so make sure your pool contains strong candidates from different parts of the video, and don't rely on a single region.

Tools:
- search_video: embedding search over the video. Visual search (CLIP) understands concrete things on screen, NOT abstract words like "funny" - so write concrete queries about what you saw in the overview (e.g. "chef dropping a pan", "audience laughing"). Speech mode searches the transcript by meaning - good for punchlines, jokes, surprising statements and topics. For talk-heavy videos lean on speech mode.
- read_transcript: read the exact words (with speaker labels) for a time range, up to 10 minutes at a time. Use it on the stretches the outline or a search hit points to - the outline summarizes, this shows what was actually said.
- If the request is about what is SAID (a quote, a topic someone mentions, "where he talks about X"), work from the transcript: search in speech mode and confirm with read_transcript, and pick the moments where it is actually said. If it is about what is SEEN, lean on visual search. Otherwise use both.
- inspect_clip: look at frames and the transcript of a time range. Verify candidates before adding them.
- add_candidate: add a clip ({MIN_CLIP_SECONDS:g}-{MAX_CLIP_SECONDS:g}s) to your pool - the clip is cut out of the video and shown on its own, so it must stand alone. Start and end at natural sentence boundaries, with a little setup before the payoff. Give a specific reason and an honest 0-1 score. Its result shows how your candidates are spread across the video - fill any empty regions.
- rank_candidates: finish by ranking your candidates, best first.

Be efficient: call several tools in the same turn (e.g. multiple searches at once, inspecting or adding several candidates at once). Do not spend turns narrating. If your searches are returning weak or irrelevant results, say so honestly in the scores instead of inventing a justification."""

def pacing_note(turn: int) -> str:
    """Per-turn reminder of how many turns are left, so ranking is never left to the last call."""
    left = MAX_ITERATIONS - turn  # turns remaining after this one
    if left >= 3:
        return ""
    if left == 0:
        return ""  # the final turn has its own note
    return (
        f"\n\nTurn {turn} of {MAX_ITERATIONS}: only {left} turn(s) remain after this one. Stop researching "
        "now - add any remaining candidates and call rank_candidates this turn or the next."
    )


LAST_TURN_NOTE = (
    "\n\nThis is your FINAL turn: only rank_candidates is available. Compare the candidates you have "
    "and rank them now. If you added fewer than needed, rank what exists - do not invent more."
)


def run_agent(
    toolbox: ToolBox,
    category: str,
    progress: Callable[[str], None] | None = None,
    client: Any = None,
    conversation: Any = None,
    target_seconds: float | None = None,
) -> dict[str, Any]:
    """`conversation` (or the provider chosen by LLM_PROVIDER, using `client` if given) supplies
    the wire format; everything below - tool guard, pacing, forced final turn - is provider-neutral."""
    emit = progress or (lambda msg: None)

    conv = conversation or make_conversation(client)
    model = selected_model()
    first_message = (
        f"Find the {TARGET_SUGGESTIONS} best '{category}' moments of this whole video, spread out "
        f"through it (duration {toolbox.index.duration:.1f}s)."
    )
    if toolbox.min_clip_seconds != MIN_CLIP_SECONDS or toolbox.max_clip_seconds != MAX_CLIP_SECONDS or target_seconds:
        first_message += (
            f" For this request every clip must be between {toolbox.min_clip_seconds:g} and "
            f"{toolbox.max_clip_seconds:g} seconds long"
            + (f" (aim for about {target_seconds:g}s)." if target_seconds else ".")
        )
    conv.start(first_message)
    final_text = ""
    # Start from what transcript summarization already spent (zero when cached / short video).
    prior = getattr(toolbox.index, "summary_usage", None) or {}
    usage = {
        "input_tokens": prior.get("input_tokens", 0),
        "output_tokens": prior.get("output_tokens", 0),
        "cached_tokens": 0,
        "cost_usd": prior.get("cost_usd", 0.0),
        "cost_known": prior.get("cost_known", True),
        "transcription_cost_usd": getattr(toolbox.index, "transcription_cost_usd", 0.0),
        "model": model,
    }

    def record_usage(turn: Any) -> str:
        if not (turn.input_tokens or turn.output_tokens):
            return ""
        usage["input_tokens"] += turn.input_tokens
        usage["output_tokens"] += turn.output_tokens
        usage["cached_tokens"] += turn.cached_tokens
        cost = call_cost(model, turn.input_tokens, turn.output_tokens, turn.cached_tokens, turn.cache_write_tokens)
        if cost is None:
            usage["cost_known"] = False
        else:
            usage["cost_usd"] += cost
        return f" [{turn.input_tokens} in / {turn.output_tokens} out tokens]"

    def take_turn(label: str, tools: list, tool_choice: dict | None, note: str | None = None) -> bool:
        """One model call plus tool execution. Returns True if tools were run (loop continues).

        The instructions are identical on every turn (so prompt caching keeps working); per-turn
        reminders travel as `note`, appended to the end of the conversation instead."""
        nonlocal final_text
        emit(label)
        turn = conv.take_turn(system=SYSTEM_PROMPT, tools=tools, tool_choice=tool_choice, note=note)
        emit(f"{label} done{record_usage(turn)}")
        if turn.text:
            final_text = turn.text
        if not turn.continue_loop:
            return False

        offered = {t["name"] for t in tools}
        results = []
        for call in turn.tool_calls:
            emit(f"Tool call: {call.name}({_short_args(call.input)})")
            if call.error:
                # The arguments were not valid JSON: tell the model instead of guessing.
                content = [{"type": "text", "text": call.error}]
                is_error = True
            elif call.name not in offered:
                # The model asked for a tool it was not given this turn (it can still see earlier
                # calls in the history). Never run it.
                content = [{"type": "text", "text": f"Tool '{call.name}' is not available this turn. "
                            f"Available: {', '.join(sorted(offered))}."}]
                is_error = True
            else:
                content, is_error = toolbox.call(call.name, call.input)
            results.append(ToolResult(call.id, content, is_error))
        conv.add_tool_results(results)
        return True

    # Turn 0: the overview is always the first call, and only the overview is offered.
    if not take_turn(
        "Agent: getting video overview",
        OVERVIEW_ONLY_SCHEMAS,
        {"type": "tool", "name": "get_overview"},
    ):
        return {"suggestions": [], "summary": final_text, "iterations": 0, "usage": _usage_summary(usage)}

    iterations = 0
    for i in range(MAX_ITERATIONS):
        iterations = i + 1
        last_turn = i == MAX_ITERATIONS - 1
        keep_going = take_turn(
            f"Agent turn {iterations}/{MAX_ITERATIONS}",
            FINAL_SCHEMAS if last_turn else TOOL_SCHEMAS,
            {"type": "any"} if last_turn else None,
            note=(LAST_TURN_NOTE if last_turn else pacing_note(iterations)).strip() or None,
        )
        # The agent ends the search itself by ranking; otherwise it runs to the turn limit.
        if not keep_going or toolbox.finalized:
            break

    # If the agent never ranked (ran out of turns / stopped talking), the selection falls back to
    # its own candidate scores - still spread out through the video.
    suggestions = toolbox.final_selection()

    # Remember what this run found, per video, so later prompts on the same video can build on it.
    # (Stored only; nothing reads it back into a prompt yet.) Never let this break a finished run.
    try:
        research.save_run(
            getattr(toolbox.index, "video_key", ""), category, toolbox.candidates, suggestions,
            toolbox.index.duration,
        )
    except Exception:
        logger.exception("Could not save research for this video")

    return {
        "suggestions": suggestions,
        "candidates_considered": len(toolbox.candidates),
        "ranked_by_agent": toolbox.finalized,
        "spacing_relaxed": toolbox.spacing_relaxed,
        "summary": final_text,
        "iterations": iterations,
        "usage": _usage_summary(usage),
    }


def _usage_summary(usage: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cached_input_tokens": usage["cached_tokens"],  # part of input_tokens served from the prompt cache
        "model": usage["model"],
        # LLM cost + Deepgram transcription (this run only; 0 when the transcript was cached).
        # None when we have no price for the configured model.
        "estimated_cost_usd": (
            round(usage["cost_usd"] + usage["transcription_cost_usd"], 5) if usage["cost_known"] else None
        ),
        "transcription_cost_usd": round(usage["transcription_cost_usd"], 5),
    }


def _short_args(args: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in args.items() if k != "reason")
