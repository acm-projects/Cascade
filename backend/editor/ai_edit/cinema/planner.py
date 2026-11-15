"""OpenAI plans Cinema edits through Cascade's shared structured client. Rules are explicit/offline only."""
import os
from fastapi import HTTPException
from ... import openai_edit
from . import director, plan as plans

class Unavailable(Exception):
    """No plan could be produced; preserve the existing edit."""

def choice():
    return 'rules' if os.getenv('CASCADE_EDIT_PLANNER', '').strip().lower() == 'rules' else 'openai'

def model():
    from backend.cascade_llm.clients import MODELS, OPENAI
    return MODELS[OPENAI]

def ai():
    return [] if choice() == 'rules' else ['openai']

def label(name):
    return openai_edit.label() if name == 'openai' else name

def _direct(prompt, prep_dir, prep, windows):
    system, images = director.instructions(), director.images(prep_dir, prep)
    # Local word alignment can overshoot the physical file by a few milliseconds.
    # Clamp only to the media boundary; manual trim windows remain strict.
    words = [{**w, 'e': min(w['e'], prep['duration'])} for w in prep['words']]
    try:
        return director.direct(lambda p: openai_edit.ask(system, p, openai_edit.strict_schema(plans.CinemaPlan), images,
                                                       name='cinema_edit', tokens=16000), prompt, words, windows=windows), label('openai')
    except HTTPException as exc:
        raise Unavailable(str(exc.detail)) from None
    except ValueError:
        raise Unavailable('OpenAI did not return a usable edit plan. Try the request again.') from None

def plan_edit(request, prep_dir, prep, windows, history):
    if choice() == 'rules': return plans.auto(prep['words']), 'rules'
    return _direct(director.new_edit(request, prep, windows, history), prep_dir, prep, windows)

def revise(note, current, prep_dir, prep, windows, history):
    if choice() == 'rules': raise Unavailable('The planner is set to rules, which cannot take creative changes.')
    return _direct(director.change(note, current, prep, windows, history), prep_dir, prep, windows)
