"""Bounded AI Director data: what the clip is, and the edit the Director chose for it."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from .style_profile_models import ProfileChoices

Genre = Literal['fan_action', 'documentary_history', 'podcast_interview', 'vlog_lifestyle', 'sports_hype',
                'tutorial_explainer', 'comedy', 'music_performance', 'other']
EditStyle = Literal['fan_edit', 'memorial', 'podcast', 'hype', 'cinematic', 'clean']
MUSIC = ('none', 'Quiet reflection', 'Tension pulse', 'Reel pulse', 'Playful plucks')


class DirectorModel(BaseModel):
    model_config = ConfigDict(extra='ignore', allow_inf_nan=False)


class Moment(DirectorModel):
    at: float = Field(ge=0)
    why: str = Field(default='', max_length=200)
    importance: float = Field(default=.5, ge=0, le=1)


class Emphasis(DirectorModel):
    text: str = Field(min_length=1, max_length=24)
    at: float = Field(ge=0)


class BrollIdea(DirectorModel):
    query: str = Field(min_length=2, max_length=80)
    at: float = Field(ge=0)
    duration: float = Field(default=2, ge=.8, le=4)
    source: Literal['source_video', 'stock'] = 'source_video'


class Analysis(DirectorModel):
    """Stage 1: what the Director saw and heard in the clip."""
    genre: Genre = 'other'
    summary: str = Field(default='', max_length=500)
    mood: str = Field(default='', max_length=60)
    era: str = Field(default='', max_length=40)
    speakers: int = Field(default=1, ge=0, le=10)
    search_query: str = Field(default='', max_length=80)
    key_moments: list[Moment] = Field(default_factory=list, max_length=8)
    emphasis: list[Emphasis] = Field(default_factory=list, max_length=8)
    broll: list[BrollIdea] = Field(default_factory=list, max_length=8)


class DirectorPlan(DirectorModel):
    """Stage 2: the edit, chosen with the analysis and real reference edits in mind."""
    style: EditStyle = 'clean'
    look: Literal['bw', 'sepia', 'warm', 'teal_orange', 'natural', 'vivid'] = 'natural'
    pacing: Literal['slow', 'medium', 'fast'] = 'medium'
    captions: Literal['none', 'clean', 'pop', 'karaoke'] = 'clean'
    music: Literal['none', 'Quiet reflection', 'Tension pulse', 'Reel pulse', 'Playful plucks'] = 'none'
    tighten_pauses: bool = False
    emphasis: list[Emphasis] = Field(default_factory=list, max_length=6)
    broll: list[BrollIdea] = Field(default_factory=list, max_length=6)
    key_moments: list[Moment] = Field(default_factory=list, max_length=8)
    rationale: str = Field(default='', max_length=600)
    inspiration: str = Field(default='', max_length=600)
    genre: Genre = 'other'
    my_style: ProfileChoices | None = None  # the style learned from the user's reference reels
