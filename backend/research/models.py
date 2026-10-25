"""Validated research results; scores are computed from the rubric in code."""
from pydantic import BaseModel, ConfigDict, Field


class Short(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    video_id: str
    title: str
    channel: str
    url: str
    thumbnail: str = ''
    views: int = Field(ge=0)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    published_at: str
    duration_s: float = Field(gt=0, le=180)
    views_per_day: float = Field(ge=0)


class Rubric(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    hook: float = Field(ge=0, le=10)
    pacing: float = Field(ge=0, le=10)
    length_fit: float = Field(ge=0, le=10)
    clarity: float = Field(ge=0, le=10)
    captions: float = Field(ge=0, le=10)
    trend_fit: float = Field(ge=0, le=10)


class Suggestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=1000)
    action_hint: str = Field(min_length=1, max_length=200)


class Grade(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    score: int = Field(ge=0, le=100)
    letter: str
    rubric: Rubric
    summary: str = Field(min_length=1, max_length=2000)
    suggestions: list[Suggestion] = Field(max_length=5)
    comparables: list[Short]
    graded_at: float
    cache_key: str
