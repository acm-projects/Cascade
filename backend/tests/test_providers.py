"""Provider selection, pricing, kill switches and structured calls. No network."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cascade_llm as llm  # noqa: E402
from cascade_llm import clients  # noqa: E402
from cascade_llm.structured import structured_json  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_CALLS_DISABLED", "ANTHROPIC_API_KEY", "ANTHROPIC_CALLS_DISABLED"):
        monkeypatch.delenv(name, raising=False)


# ---------- provider selection ----------

@pytest.mark.parametrize(
    "model,expected",
    [
        ("claude-haiku-5-5", "anthropic"),
        ("claude-opus-5-5", "anthropic"),
        ("gpt-6-luna", "openai"),
        ("gpt-5.6-luna", "openai"),
        ("o3-mini", "openai"),
        ("some-other-model", "anthropic"),  # unknown falls back to the default provider
        ("", "anthropic"),
    ],
)
def test_provider_is_inferred_from_the_model_id(model, expected):
    assert llm.provider_for_model(model) == expected


def test_override_only_applies_to_unrecognized_ids(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert llm.provider_for_model("some-other-model") == "openai"
    # a recognized id always wins: a mismatched provider/model pair is impossible
    assert llm.provider_for_model("claude-haiku-5-5") == "anthropic"
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert llm.provider_for_model("gpt-6-luna") == "openai"
    monkeypatch.setenv("LLM_PROVIDER", "nonsense")
    assert llm.provider_for_model("some-other-model") == "anthropic"


# ---------- pricing ----------

def test_haiku_pricing_and_its_100k_tier():
    assert llm.call_cost("claude-haiku-5-5", 100_000, 0) == pytest.approx(100_000 * 0.10 / 1e6)  # at the line: small tier
    assert llm.call_cost("claude-haiku-5-5", 0, 1_000_000) == pytest.approx(0.50)
    assert llm.call_cost("claude-haiku-5-5", 100_001, 0) == pytest.approx(100_001 * 0.50 / 1e6)  # over: large tier
    assert llm.call_cost("claude-haiku-5-5", 1_000_000, 0) == pytest.approx(0.50)


def test_luna_pricing_cached_input_and_272k_tier():
    assert llm.call_cost("gpt-6-luna", 1000, 1000) == pytest.approx((1000 * 0.10 + 1000 * 0.50) / 1e6)
    # 900 of 1000 prompt tokens were served from OpenAI's prompt cache at $0.01/M
    assert llm.call_cost("gpt-6-luna", 1000, 0, cached_tokens=900) == pytest.approx(
        (100 * 0.10 + 900 * 0.01) / 1e6
    )
    # over 272K input tokens: 2x input/cache rates and 1.5x output for the whole request
    assert llm.call_cost("gpt-6-luna", 272_000, 1000) == pytest.approx((272_000 * 0.10 + 1000 * 0.50) / 1e6)
    big = llm.call_cost("gpt-6-luna", 272_001, 1000, cached_tokens=1000)
    assert big == pytest.approx((271_001 * 0.20 + 1000 * 0.02 + 1000 * 0.75) / 1e6)
    # Anthropic's tier boundary (100K) does not apply to Luna
    assert llm.call_cost("gpt-6-luna", 150_000, 0) == pytest.approx(150_000 * 0.10 / 1e6)


def test_unknown_model_has_no_price():
    assert llm.call_cost("some-other-model", 1000, 1000) is None


# ---------- clients and kill switches ----------

def test_missing_key_and_kill_switch_per_provider(monkeypatch):
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not set"):
        llm.make_client("anthropic")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        llm.make_client("openai")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_CALLS_DISABLED", "true")
    with pytest.raises(RuntimeError, match=r"OpenAI API calls are disabled \(OPENAI_CALLS_DISABLED=true"):
        llm.make_client("openai")
    # one provider's kill switch does not affect the other
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert type(llm.make_client("anthropic")).__name__ == "Anthropic"

    monkeypatch.setenv("ANTHROPIC_CALLS_DISABLED", "true")
    with pytest.raises(RuntimeError, match=r"Anthropic API calls are disabled \(ANTHROPIC_CALLS_DISABLED=true"):
        llm.make_client("anthropic")
    monkeypatch.delenv("OPENAI_CALLS_DISABLED")
    assert type(llm.make_client("openai")).__name__ == "OpenAI"


def test_keys_are_read_at_call_time(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-first")
    first = llm.make_client("openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-second")
    assert llm.make_client("openai").api_key == "sk-second" and first.api_key == "sk-first"


# ---------- structured_json ----------

SCHEMA = {
    "type": "object",
    "properties": {"topic": {"type": "string"}},
    "required": ["topic"],
    "additionalProperties": False,
}


def usage(i=10, o=5, cached=0):
    return SimpleNamespace(input_tokens=i, output_tokens=o, input_tokens_details=SimpleNamespace(cached_tokens=cached))


def oa_response(text, status="completed", usage_=None, parts=None):
    content = parts or [SimpleNamespace(type="output_text", text=text)]
    return SimpleNamespace(
        status=status,
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        output=[
            SimpleNamespace(type="reasoning", id="rs_1", summary=[]),
            SimpleNamespace(type="message", role="assistant", content=content),
        ],
        usage=usage_ or usage(),
    )


class FakeOpenAI:
    def __init__(self, *responses):
        self.scripted = list(responses)
        self.calls = []
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.scripted.pop(0)


def test_openai_structured_request_shape_and_parsing():
    client = FakeOpenAI(oa_response(json.dumps({"topic": "bread"}), usage_=usage(100, 20, cached=40)))
    result = structured_json(
        "gpt-6-luna", "summarize", SCHEMA, name="chunk_summary", effort="low", max_output_tokens=4096,
        images=[{"media_type": "image/jpeg", "data": "QUJD"}], client=client,
    )
    assert result.data == {"topic": "bread"}
    assert (result.input_tokens, result.output_tokens, result.cached_tokens) == (100, 20, 40)
    call = client.calls[0]
    assert call["text"] == {"format": {"type": "json_schema", "name": "chunk_summary", "schema": SCHEMA, "strict": True}}
    assert call["reasoning"] == {"effort": "low"} and call["max_output_tokens"] == 4096
    content = call["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "summarize"}
    assert content[1] == {"type": "input_image", "image_url": "data:image/jpeg;base64,QUJD"}


def test_openai_structured_refusal_and_cutoff_raise():
    refusal = [SimpleNamespace(type="refusal", refusal="I can't help with that")]
    with pytest.raises(RuntimeError, match="refused"):
        structured_json("gpt-6-luna", "p", SCHEMA, name="n", client=FakeOpenAI(oa_response("", parts=refusal)))
    with pytest.raises(RuntimeError, match="cut off"):
        structured_json("gpt-6-luna", "p", SCHEMA, name="n", client=FakeOpenAI(oa_response("{", status="incomplete")))


def test_anthropic_structured_unchanged_and_supports_images():
    calls = []

    class A:
        messages = None

        def create(self, **kw):
            calls.append(kw)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(type="thinking", thinking="hmm", signature="s"),
                    SimpleNamespace(type="text", text=json.dumps({"topic": "bread"})),
                ],
                usage=SimpleNamespace(input_tokens=7, output_tokens=3),
            )

    a = A()
    a.messages = a
    result = structured_json("claude-haiku-5-5", "summarize", SCHEMA, name="n", images=[{"media_type": "image/png", "data": "QQ=="}], client=a)
    assert result.data == {"topic": "bread"} and (result.input_tokens, result.output_tokens) == (7, 3)
    kw = calls[0]
    assert kw["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert kw["messages"][0]["content"][0]["source"] == {"type": "base64", "media_type": "image/png", "data": "QQ=="}
    assert kw["messages"][0]["content"][-1] == {"type": "text", "text": "summarize"}


def _strict_ok(schema, path="schema"):
    """OpenAI strict mode: every object has additionalProperties=false and lists all its properties."""
    problems = []
    if schema.get("type") == "object":
        if schema.get("additionalProperties") is not False:
            problems.append(f"{path}: additionalProperties must be false")
        if set(schema.get("required", [])) != set(schema.get("properties", {})):
            problems.append(f"{path}: required must list every property")
        for k, v in schema.get("properties", {}).items():
            problems += _strict_ok(v, f"{path}.{k}")
    if schema.get("type") == "array":
        problems += _strict_ok(schema["items"], f"{path}[]")
    return problems


def test_schemas_sent_to_openai_satisfy_strict_mode():
    from agent.summaries import SUMMARY_SCHEMA
    from trends.pipeline import TAG_SCHEMA

    assert _strict_ok(SUMMARY_SCHEMA) == []
    assert _strict_ok(TAG_SCHEMA) == []
