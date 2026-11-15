"""Bounded AI sequence data; never executable model-authored project JSON.

The same saved structure is executed by either FableCut (legacy) or OpenChatCut.
OpenChatCut-only fields default to values that leave FableCut drafts unchanged.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

FABLECUT_ENGINE = 'fablecut-1.18.0'
OPENCHATCUT_ENGINE = 'openchatcut-0.2.17'

# Verified against the installed OpenChatCut library (browse_library) — the only
# effect/transition ids the planner may choose or the executor will place.
OCC_TRANSITIONS = {
    'fade': 'builtin:tr-cross-dissolve', 'whip': 'builtin:tr-whip-pan', 'blur': 'builtin:tr-radial-blur',
    'zoom': 'builtin:tr-anticipation-zoom', 'flash': 'builtin:tr-flash', 'shake': 'builtin:tr-impact-shake',
    'glitch': 'builtin:tr-glitch-cut', 'dip': 'builtin:tr-dip-to-black',
}
OCC_ZOOMS = {name: f'library:zoom:{name}' for name in ('punch', 'snap', 'pulse', 'whip-in', 'bounce', 'slow-push')}
OCC_LOOKS = {'teal-orange': 'builtin:look-teal-orange'}
OCC_SHAKE = 'builtin:fx-shake'
OCC_GRAIN = 'builtin:fx-film-grain'

Transition = Literal['none', 'fade', 'whip', 'blur', 'zoom', 'flash', 'shake', 'glitch', 'dip']
ZoomStyle = Literal['punch', 'snap', 'pulse', 'whip-in', 'bounce', 'slow-push']


class SequenceShot(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    rate_from: float = Field(default=1, ge=.5, le=2)
    rate_to: float = Field(default=1, ge=.5, le=2)
    zoom: float = Field(default=1, ge=1, le=1.3)
    zoom_at: float = Field(default=.15, ge=0, le=2)
    zoom_style: ZoomStyle = 'punch'
    shake: float = Field(default=0, ge=0, le=8)
    transition: Transition = 'none'
    reason: str = Field(default='', max_length=240)

    @model_validator(mode='after')
    def interval(self):
        if self.end-self.start < .25:
            raise ValueError('A sequence shot must retain at least 0.25 source seconds.')
        return self


class FablecutSequence(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    engine: Literal['fablecut-1.18.0', 'openchatcut-0.2.17'] = FABLECUT_ENGINE
    ratio: Literal['9:16', 'original'] = '9:16'
    shots: list[SequenceShot] = Field(min_length=1, max_length=16)
    music_asset_id: str | None = Field(default=None, pattern=r'^aud-[a-f0-9]{32}$')
    music_volume: float = Field(default=.14, ge=0, le=.35)
    sound_design: bool = True
    grade: float = Field(default=.05, ge=0, le=.15)
    beat_period: float = Field(default=.5, ge=.2, le=2)
    note: str = Field(default='', max_length=1000)
    look: Literal['none', 'teal-orange'] = 'none'
    film_grain: bool = False
    framing: Literal['blur', 'cover', 'fit'] = 'blur'
    title: str = Field(default='', max_length=60)

    @model_validator(mode='after')
    def engine_features(self):
        if self.engine == FABLECUT_ENGINE:
            if any(s.transition in ('flash', 'shake', 'glitch', 'dip') for s in self.shots):
                raise ValueError('That transition requires the OpenChatCut engine.')
        elif any(s.rate_from != s.rate_to for s in self.shots):
            # OpenChatCut clips have one playback rate; never claim an unexecuted ramp.
            raise ValueError('OpenChatCut shots use a constant speed per shot.')
        return self
