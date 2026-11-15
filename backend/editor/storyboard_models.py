"""A storyboard the AI Editor proposes before anything renders: one beat per transcript line."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class BoardModel(BaseModel):
    model_config = ConfigDict(extra='ignore', allow_inf_nan=False)


class Beat(BoardModel):
    n: int = Field(ge=0, le=999)                      # transcript line number (captions are keyed by it)
    keep: bool = True                                 # False cuts this line out
    caption: str = Field(default='', max_length=200)  # on-screen text; '' shows the spoken words
    emphasis: str = Field(default='', max_length=24)  # one big word for this beat
    zoom: Literal['none', 'punch', 'push'] = 'none'
    broll: str = Field(default='', max_length=80)     # stock/source footage to cut away to
    effect: Literal['none', 'flash', 'glitch'] = 'none'
    sfx: Literal['none', 'hit', 'whoosh'] = 'none'
    why: str = Field(default='', max_length=160)


class Storyboard(BoardModel):
    """What the planner returns; the server adds id/request/planner before saving."""
    reply: str = Field(default='', max_length=600)    # short answer to the user's sentence or note
    title: str = Field(default='', max_length=60)
    ratio: Literal['9:16', '1:1', '4:5', '16:9', 'original'] = '9:16'
    look: Literal['bw', 'sepia', 'warm', 'teal_orange', 'natural', 'vivid'] = 'natural'
    captions: Literal['none', 'clean', 'pop', 'karaoke'] = 'pop'
    caption_size: int = Field(default=40, ge=20, le=80)
    accent: str = Field(default='#e50914', pattern=r'^#[0-9a-fA-F]{6}$')
    music: Literal['none', 'Quiet reflection', 'Tension pulse', 'Reel pulse', 'Playful plucks'] = 'none'
    hook: str = Field(default='', max_length=40)      # HyperFrames hook card text; '' for none
    beats: list[Beat] = Field(default_factory=list, max_length=200)


class SavedStoryboard(Storyboard):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')
    request: str = Field(default='', max_length=2000)
    planner: str = Field(default='', max_length=300)
    style: str = Field(default='', max_length=60)
    notes: list[str] = Field(default_factory=list, max_length=50)
    thumbnails: dict[str, str] = Field(default_factory=dict)  # beat number -> small base64 JPEG
