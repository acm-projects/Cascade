"""Shared, bounded timeline state for manual controls, AI, preview and export."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class TimelineModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class AudioSegment(TimelineModel):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')
    asset_id: str = Field(pattern=r'^aud-[a-f0-9]{32}$')
    track: Literal['music', 'sfx'] = 'music'
    start: float = Field(ge=0)
    duration: float = Field(ge=.05, le=1200)
    offset: float = Field(default=0, ge=0)
    volume: float = Field(default=.18, ge=0, le=2)
    fade_in: float = Field(default=.3, ge=0, le=30)
    fade_out: float = Field(default=.5, ge=0, le=30)
    duck: bool = True
    duck_gain: float = Field(default=.25, ge=0, le=1)
    loop: bool = True

class Motion(TimelineModel):
    start: float = Field(ge=0)
    duration: float = Field(ge=.05, le=300)
    scale_from: float = Field(default=1, ge=1, le=3)
    scale_to: float = Field(default=1.25, ge=1, le=3)
    shake: float = Field(default=0, ge=0, le=.05)

class TextOverlay(TimelineModel):
    start: float = Field(ge=0)
    duration: float = Field(ge=.05, le=300)
    text: str = Field(min_length=1, max_length=300)
    size: int = Field(default=48, ge=12, le=100)
    color: str = Field(default='#ffffff', pattern=r'^#[0-9a-fA-F]{6}$')
    position: Literal['top', 'middle', 'bottom'] = 'top'
    animate: bool = True

class Transition(TimelineModel):
    fade_in: float = Field(default=0, ge=0, le=5)
    fade_out: float = Field(default=0, ge=0, le=5)

class TimelineSpan(TimelineModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

class SpeedRamp(TimelineModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    rate_from: float = Field(default=1, ge=.75, le=2.5)
    rate_to: float = Field(default=1.8, ge=.75, le=2.5)

class CutAccent(TimelineModel):
    start: float = Field(ge=0)
    duration: float = Field(default=.12, ge=.05, le=.25)
    kind: Literal['blur'] = 'blur'
    strength: float = Field(default=2, ge=.5, le=5)

StyleKind = Literal['bg_swap','color_pop','shape_reveal','outline','glitch','ink','zoom_blur','whip','flash','title_card','text','film','motion_card']
StyleBackground = Literal['comic','halftone','speedlines','neon','paper','blur']
StylePalette = Literal['spider','neon','gold','mono']

class StyleEvent(TimelineModel):
    """One timed subject-matte or frame effect, in generated-clip seconds."""
    start: float = Field(ge=0)
    duration: float = Field(ge=.05, le=30)
    kind: StyleKind
    background: StyleBackground = 'comic'
    shape: Literal['x','star','slash'] = 'x'
    strength: float = Field(default=1, ge=.2, le=2)
    text: str = Field(default='', max_length=40)
    font: Literal['impact','typewriter','poster','grunge','script','war','ancient'] = 'impact'
    animate: Literal['slam','glitch','type','flicker'] = 'slam'
    behind: bool = True
    size: float = Field(default=1, ge=.25, le=1.2)
    place: Literal['center','upper','lower'] = 'center'
    tone: Literal['bw','sepia','warm'] = 'bw'
    color: str = Field(default='', pattern=r'^(#[0-9a-fA-F]{6})?$')  # motion_card accent; '' uses the palette

class StyleInfo(TimelineModel):
    palette: StylePalette = 'spider'
    events: list[StyleEvent] = Field(default_factory=list, max_length=80)
    note: str = Field(default='', max_length=300)

class StoryboardInfo(TimelineModel):
    """What the last rendered storyboard added, so the next one replaces it and manual edits stay."""
    audio_ids: list[str] = Field(default_factory=list, max_length=24)
    broll_ids: list[str] = Field(default_factory=list, max_length=30)
    motion: list[Motion] = Field(default_factory=list, max_length=30)
    text_keys: list[str] = Field(default_factory=list, max_length=1000)

class StyleOptions(TimelineModel):
    """Preset request: the executor measures beats/cuts and lays out the events."""
    palette: StylePalette = 'spider'
    effects: list[StyleKind] = Field(default_factory=list, max_length=10)
    backgrounds: list[StyleBackground] = Field(default_factory=list, max_length=6)
    intensity: Literal['subtle','high'] = 'high'
    end_card: str = Field(default='Cascade', max_length=30)
    texts: bool = True
    words: list[str] = Field(default_factory=list, max_length=8)
    broll_query: str = Field(default='', max_length=80)

class ReelInfo(TimelineModel):
    style: Literal['high-energy-v1'] = 'high-energy-v1'
    music_asset_id: str
    beats: list[float] = Field(default_factory=list, max_length=3000)
    bpm: float | None = None
    beat_confidence: float = Field(default=0, ge=0, le=1)
    beat_sync_current: bool = True
    hook_reason: str = Field(default='', max_length=500)
    intensity: Literal['high-energy','flashy'] = 'high-energy'

    # Ownership lets a later AI style preserve manually added or subsequently modified events.
    generated_motion: list[Motion] = Field(default_factory=list, max_length=30)
    generated_accents: list[CutAccent] = Field(default_factory=list, max_length=30)
    generated_audio_ids: list[str] = Field(default_factory=list, max_length=30)
    generated_broll_ids: list[str] = Field(default_factory=list, max_length=30)
    generated_speed: list[SpeedRamp] = Field(default_factory=list, max_length=8)
    last_motion_index: int | None = Field(default=None, ge=0, le=29)
