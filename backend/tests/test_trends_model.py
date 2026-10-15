"""The trends tab tags videos with Haiku 5.5, and a model change must not serve old cached results."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trends import pipeline  # noqa: E402
from trends import router as trends_router  # noqa: E402


def test_default_tagging_model_is_haiku_5_5():
    assert pipeline.TAGGING_MODEL == "claude-haiku-5-5"


def test_result_cache_key_changes_with_the_model(monkeypatch):
    monkeypatch.setattr(pipeline, "TAGGING_MODEL", "claude-haiku-5-5")
    new = trends_router._result_cache_key("Fitness ", "abc")
    monkeypatch.setattr(pipeline, "TAGGING_MODEL", "claude-haiku-4-5-20251001")
    old = trends_router._result_cache_key("Fitness ", "abc")
    assert new != old
    # still normalizes the topic, so case/whitespace don't defeat the cache
    monkeypatch.setattr(pipeline, "TAGGING_MODEL", "claude-haiku-5-5")
    assert trends_router._result_cache_key("fitness", "abc") == new
