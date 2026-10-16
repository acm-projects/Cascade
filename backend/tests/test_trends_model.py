"""The Trends tab uses the one LLM_PROVIDER switch, and a provider change must not serve old cached results."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.trends import pipeline  # noqa: E402
from backend.trends import router as trends_router  # noqa: E402


@pytest.fixture(autouse=True)
def default_provider(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


def test_result_cache_key_changes_with_the_provider(monkeypatch):
    claude = trends_router._result_cache_key("Fitness ", "abc")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    openai_key = trends_router._result_cache_key("Fitness ", "abc")
    assert claude != openai_key
    # still normalizes the topic, so case/whitespace don't defeat the cache
    assert trends_router._result_cache_key("fitness", "abc") == openai_key
    monkeypatch.delenv("LLM_PROVIDER")
    assert trends_router._result_cache_key("fitness", "abc") == claude


def test_tag_cache_key_changes_with_the_provider(monkeypatch, tmp_path):
    frame = tmp_path / "f.jpg"
    frame.write_bytes(b"\xff\xd8jpeg")
    claude = pipeline._tags_cache_key([frame], "hello")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert pipeline._tags_cache_key([frame], "hello") != claude
