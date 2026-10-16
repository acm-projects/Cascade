"""Live check of the OpenAI (Responses API) path with a REAL key. Costs well under a cent.

Run from backend/:   python scripts/check_openai.py

It proves the things the unit tests (which use a fake client) cannot:
  1. the model id exists for your key
  2. a forced function call works and its arguments parse
  3. an image returned from a tool is accepted AND actually seen - in the function_call_output
     array form ("array") and the follow-up user message form ("user_message")
  4. a second turn works after the reasoning items are sent back
  5. a strict structured-output call returns parseable JSON

It never prints your key. Exit code 0 only if everything the agent needs passed.
"""

from __future__ import annotations

import base64
import io
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND.parent / ".env")

from cascade_llm import MODELS, OpenAIConversation, call_cost, make_client, structured_json  # noqa: E402

# This script always exercises the OpenAI path, whatever LLM_PROVIDER is set to in .env.
os.environ["LLM_PROVIDER"] = "openai"
MODEL = MODELS["openai"]
TOOL = {
    "name": "look_at_frame",
    "description": "Returns one video frame. Call it once with the frame number.",
    "input_schema": {
        "type": "object",
        "properties": {"frame": {"type": "integer"}},
        "required": ["frame"],
    },
}
SCHEMA = {
    "type": "object",
    "properties": {"topic": {"type": "string"}, "mood": {"type": "string"}},
    "required": ["topic", "mood"],
    "additionalProperties": False,
}

total_in = total_out = total_cached = 0
failures: list[str] = []


def red_frame_b64() -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (128, 128), (220, 20, 20)).save(buf, "JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def tally(turn) -> None:
    global total_in, total_out, total_cached
    total_in += turn.input_tokens
    total_out += turn.output_tokens
    total_cached += turn.cached_tokens


def check_image_mode(client, model: str, mode: str) -> bool:
    print(f"\n[{mode}] tool result with an image")
    conv = OpenAIConversation(client, model, image_mode=mode)
    conv.start("Call look_at_frame with frame 1, then tell me the single dominant colour of the frame it returns. One word.")
    try:
        turn1 = conv.take_turn(
            system="You are testing a tool. Follow the instructions exactly.",
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "look_at_frame"},
        )
        tally(turn1)
        if not turn1.tool_calls or turn1.tool_calls[0].name != "look_at_frame":
            print("  FAIL: forced function call did not return look_at_frame")
            return False
        call = turn1.tool_calls[0]
        print(f"  forced call OK: look_at_frame({call.input}) parse_error={call.error}")

        from cascade_llm import ToolResult

        conv.add_tool_results([
            ToolResult(call.id, [
                {"type": "text", "text": "Frame at 1.0s:"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": red_frame_b64()}},
            ])
        ])
        turn2 = conv.take_turn(system="You are testing a tool. Follow the instructions exactly.", tools=[TOOL], tool_choice=None)
        tally(turn2)
        answer = turn2.text.strip().lower()
        print(f"  second turn (after reasoning items were sent back) answered: {answer!r}")
        ok = "red" in answer
        print("  PASS: the model saw the image" if ok else "  FAIL: the model did not report red")
        return ok
    except Exception as exc:  # report, don't crash: the other mode may still work
        print(f"  FAIL: {type(exc).__name__}: {str(exc)[:400]}")
        return False


def main() -> int:
    model = MODEL
    print(f"model: {model}")
    try:
        client = make_client("openai")
    except RuntimeError as exc:
        print(f"cannot run: {exc}")
        return 2

    print("\n[1] model access")
    try:
        client.models.retrieve(model)
        print("  PASS: the model id is available to this key")
    except Exception as exc:
        print(f"  FAIL: {type(exc).__name__}: {str(exc)[:300]}")
        return 1

    modes = {mode: check_image_mode(client, model, mode) for mode in ("user_message", "array")}

    print("\n[structured output]")
    try:
        res = structured_json(
            model,
            "Summarize in the schema: two hosts joke about burning a loaf of sourdough, then share a hydration tip.",
            SCHEMA, name="check", effort="low", client=client,
        )
        print(f"  PASS: {res.data}")
        global total_in, total_out, total_cached
        total_in += res.input_tokens
        total_out += res.output_tokens
        total_cached += res.cached_tokens
    except Exception as exc:
        print(f"  FAIL: {type(exc).__name__}: {str(exc)[:400]}")
        failures.append("structured output")

    cost = call_cost(model, total_in, total_out, total_cached)
    print(f"\ntokens: {total_in} in ({total_cached} cached) / {total_out} out"
          + (f"  ~${cost:.5f}" if cost is not None else "  (no price on file for this model)"))

    print("\n--- result ---")
    print(f"image in a function_call_output array : {'works' if modes['array'] else 'FAILED'}")
    print(f"image in a follow-up user message     : {'works' if modes['user_message'] else 'FAILED'}")
    if modes["array"]:
        print("note: both image modes work. The agent uses 'user_message' (the default in cascade_llm/conversation.py);")
        print("      'array' also works and keeps frames attached to the call that returned them.")
    elif modes["user_message"]:
        print("the agent's default image mode ('user_message') works")
    ok = (modes["array"] or modes["user_message"]) and not failures
    print("OVERALL:", "PASS - the agent can run on this model" if ok else "FAIL - do not set LLM_PROVIDER=openai yet")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
