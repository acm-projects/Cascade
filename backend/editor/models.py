"""Editor models; extracted without changing media behavior."""
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend import broll as stocklib


class Captions(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    enabled: bool = True
    font: Literal['Arial', 'Georgia', 'Verdana'] = 'Arial'
    size: int = Field(default=32, ge=12, le=80)
    color: str = Field(default='#ffffff', pattern=r'^#[0-9a-fA-F]{6}$')
    stroke: str = Field(default='#000000', pattern=r'^#[0-9a-fA-F]{6}$')
    thickness: float = Field(default=2, ge=0, le=8)
    background: str = Field(default='#000000', pattern=r'^#[0-9a-fA-F]{6}$')
    opacity: float = Field(default=0, ge=0, le=1)
    position: Literal['top', 'middle', 'bottom'] = 'bottom'
    bold: bool = False


class Composition(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    ratio: Literal['original','9:16','1:1','4:5','16:9','4:3'] = 'original'
    mode: Literal['fit','fill'] = 'fit'
    x: float = Field(default=.5, ge=0, le=1)
    y: float = Field(default=.5, ge=0, le=1)
    background: str = Field(default='#06110d', pattern=r'^#[0-9a-fA-F]{6}$')


class Effects(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    brightness: float = Field(default=1, ge=0.5, le=1.5)
    contrast: float = Field(default=1, ge=0.5, le=1.5)
    saturation: float = Field(default=1, ge=0, le=2)
    grayscale: bool = False


class SubjectSelection(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    t: float = Field(ge=0,le=300)
    box: list[float] = Field(min_length=4,max_length=4)

    @model_validator(mode='after')
    def bounds(self):
        x,y,w,h=self.box
        if not all(math.isfinite(v) for v in self.box) or min(x,y)<0 or min(w,h)<.01 or x+w>1.000001 or y+h>1.000001:
            raise ValueError('Select a valid region inside the source video.')
        return self


class Reframe(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = False
    focus: Literal['auto','speaker','both','left','right'] = 'auto'
    selection: SubjectSelection | None = None
    analysis_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


class ReframePlanInput(BaseModel):
    composition: Composition
    focus: Literal['auto','speaker','both','left','right'] = 'auto'
    selection: SubjectSelection | None = None


class Edit(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    captions: Captions = Field(default_factory=Captions)
    composition: Composition = Field(default_factory=Composition)
    effects: Effects = Field(default_factory=Effects)
    reframe: Reframe = Field(default_factory=Reframe)
    texts: dict[str, str] = Field(default_factory=dict, max_length=1000)
    broll: list[stocklib.Segment] = Field(default_factory=list, max_length=30)


class Message(BaseModel):
    role: Literal['user', 'assistant']
    text: str = Field(max_length=4000)


class Draft(BaseModel):
    state: Edit
    chat: list[Message] = Field(default_factory=list, max_length=200)
    updated_at: int = Field(default=0, ge=0)


class ChatInput(BaseModel):
    state: Edit
    chat: list[Message] = Field(default_factory=list, max_length=200)
    message: str = Field(min_length=1, max_length=2000)
    result_ids: list[str] = Field(default_factory=list, max_length=120)
    selected_segment: str | None = Field(default=None, max_length=32)


class Action(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    type: Literal['trim_first', 'keep_first', 'reset_trim', 'captions_enabled', 'caption_color', 'caption_bold', 'caption_position', 'caption_text', 'caption_settings', 'reframe_focus', 'broll_search', 'broll_insert', 'broll_update', 'broll_remove']
    focus: Literal['speaker','both','left','right','off'] | None = None
    settings: Captions | None = None
    seconds: float | None = Field(default=None, gt=0)
    enabled: bool | None = None
    color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    position: Literal['top', 'middle', 'bottom'] | None = None
    cue_index: int | None = Field(default=None, ge=0)
    text: str | None = Field(default=None, max_length=2000)

    query: str | None = Field(default=None, min_length=1, max_length=160)
    asset_id: str | None = Field(default=None, max_length=80)
    segment_id: str | None = Field(default=None, max_length=32)
    start: float | None = Field(default=None, ge=0)
    duration: float | None = Field(default=None, ge=.05)
    offset: float | None = Field(default=None, ge=0)
    mode: Literal['fit', 'fill'] | None = None
    time_basis: Literal['generated', 'preview'] | None = None


class Proposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message: str = Field(min_length=1, max_length=2000)
    actions: list[Action] = Field(max_length=10)


class CaptionImage(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    png: str = Field(max_length=4_000_000)


class ExportInput(Edit):
    resolution: Literal['original', '1080p', '720p'] = 'original'
    overlays: list[CaptionImage] | None = Field(default=None, max_length=1000)


class BatchEntry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    job_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    clip_index: int = Field(ge=0)
    edit: ExportInput


class BatchExport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    clips: list[BatchEntry] = Field(min_length=1, max_length=100)
