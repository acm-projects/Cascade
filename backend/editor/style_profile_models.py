"""Bounded data for a user's learned editing style, built from their own reference reels."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

HEX = r'^#[0-9a-fA-F]{6}$'


class StyleModel(BaseModel):
    model_config = ConfigDict(extra='ignore', allow_inf_nan=False)


class ReferenceInfo(StyleModel):
    """What was measured on one reference video."""
    label: str = Field(max_length=120)
    duration: float = Field(ge=0)
    cuts_per_minute: float = Field(ge=0)
    flash_bursts: int = Field(default=0, ge=0)
    saturation: float = Field(default=0, ge=0, le=1)
    mono: float = Field(default=0, ge=0, le=1)
    brightness: float = Field(default=0, ge=0, le=1)
    accent: str = Field(default='', pattern=r'^(#[0-9a-fA-F]{6})?$')


class ProfileChoices(StyleModel):
    """The editable style sheet. Every field maps onto an existing timeline feature."""
    name: str = Field(default='My style', min_length=1, max_length=40)
    look: Literal['bw', 'sepia', 'warm', 'teal_orange', 'natural', 'vivid'] = 'natural'
    pacing: Literal['slow', 'medium', 'fast'] = 'medium'
    captions: Literal['none', 'clean', 'pop', 'karaoke'] = 'pop'
    caption_words: int = Field(default=3, ge=1, le=4)
    caption_color: str = Field(default='#ffffff', pattern=HEX)
    accent: str = Field(default='#e50914', pattern=HEX)
    emphasis_font: Literal['impact', 'poster', 'typewriter', 'script', 'grunge'] = 'impact'
    words_behind: bool = True
    transitions: Literal['cut', 'flash', 'dissolve'] = 'cut'
    glitch_accents: bool = False
    punch_ins: bool = True
    sound_fx: bool = True
    music: Literal['none', 'Quiet reflection', 'Tension pulse', 'Reel pulse', 'Playful plucks'] = 'Reel pulse'
    tighten_pauses: bool = True
    broll: Literal['low', 'medium', 'high'] = 'medium'
    motion_cards: bool = True
    summary: list[str] = Field(default_factory=list, max_length=12)


class StyleProfile(StyleModel):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')
    status: Literal['draft', 'approved'] = 'draft'
    created: float = 0
    chosen_by: str = Field(default='', max_length=80)
    source_key: str = Field(default='', max_length=80)  # which reference set it was learned from
    references: list[ReferenceInfo] = Field(default_factory=list, max_length=8)
    choices: ProfileChoices = Field(default_factory=ProfileChoices)
