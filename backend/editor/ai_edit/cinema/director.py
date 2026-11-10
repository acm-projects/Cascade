"""The AI planner's job, written once for any model: read the transcript, look at the contact sheets and
return a CinemaPlan (plan.py). The instructions are the plain-text file prompts/director.md, so they can be
read, edited and versioned without touching code. Which model answers is planner.py's business."""
import json
from pathlib import Path

from .plan import CinemaPlan, check

PROMPT = Path(__file__).parent/'prompts'/'director.md'


def instructions():
    return PROMPT.read_text()


def images(prep_dir, prep):
    return [(name, (Path(prep_dir)/name).read_bytes()) for name in prep.get('sheets', [])[:6] if (Path(prep_dir)/name).is_file()]


def transcript(words, windows):
    """word_number:word@second, with [pause 0.8s] where the speaker stops, so the planner can hear the rhythm."""
    inside = lambda t: any(a <= t <= b for a, b in windows)
    out, last = [], None
    for w in words:
        if not inside(w['s']): continue
        if last is not None and w['s']-last > .6: out.append(f"[pause {w['s']-last:.1f}s]")
        out.append(f"{w['i']}:{w['w']}@{w['s']:.1f}")
        last = w['e']
    return ' '.join(out)


def new_edit(request, prep, windows, history):
    return (f"Request: {request}\n\nEarlier chat:\n{json.dumps(history[-8:])}\n\n"
            f"Clip: {prep['duration']:.1f} s. Usable source ranges: {windows}. Camera cuts at seconds: {[round(c, 1) for c in prep['cuts']][:200]}.\n"
            f"Transcript as word_number:word@second:\n{transcript(prep['words'], windows)}")


def change(note, current, prep, windows, history):
    return (f"Request (a change to the edit below): {note}\nChange only what this asks for and return the whole plan.\n\n"
            f"Current plan:\n{current.model_dump_json()}\n\nEarlier chat:\n{json.dumps(history[-8:])}\n\n"
            f"Transcript as word_number:word@second:\n{transcript(prep['words'], windows)}")


def direct(ask, prompt, words, tries=2):
    """Run `ask(prompt) -> dict` until it returns a plan that passes the checks (each failure is fed back)."""
    last = ''
    for _ in range(tries):
        answer = ask(prompt+last)
        try:
            plan = CinemaPlan.model_validate(answer)
            check(plan, words)
            return plan
        except ValueError as exc:
            last = f'\n\nYour previous plan was rejected, fix this and return the whole plan: {str(exc)[:600]}'
    raise ValueError('The planner did not return a usable edit plan: '+last[-300:])
