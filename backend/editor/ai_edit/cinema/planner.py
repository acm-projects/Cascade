"""Which mind plans an edit. The engine never depends on a particular model: every planner returns the same
CinemaPlan, and the deterministic engine renders it.

Choose with environment variables (put them in .env):

  CASCADE_EDIT_PLANNER   auto (default) | claude | command | rules
  CASCADE_EDIT_MODEL     passed to the Claude CLI as --model, e.g. opus, sonnet, or a full model id.
                         Unset = whatever model your Claude subscription uses by default.
  CASCADE_EDIT_PLANNER_CMD   for "command": any program that reads {"system", "prompt"} as JSON on stdin and
                         prints a plan as JSON (a local model through Ollama, another CLI, a script).

auto tries claude, then command, then rules. "rules" is plan.auto(): no model at all, always available.
To add a planner, write a function (system, prompt, images) -> dict and register it in BACKENDS."""
import json
import os
import shlex
import subprocess

from . import director, plan as plans


class Unavailable(Exception):
    """No AI planner can answer right now (not installed, not signed in, usage limit, or it failed)."""


def choice():
    return os.getenv('CASCADE_EDIT_PLANNER', 'auto').strip().lower() or 'auto'


def model():
    return os.getenv('CASCADE_EDIT_MODEL', '').strip()


def _claude(system, prompt, images):
    from ... import claude_code
    return claude_code.ask(system, prompt, images, timeout=900, model=model() or None)


def _command(system, prompt, images):
    command = os.getenv('CASCADE_EDIT_PLANNER_CMD', '').strip()
    if not command: raise Unavailable('CASCADE_EDIT_PLANNER_CMD is not set.')
    run = subprocess.run(shlex.split(command), input=json.dumps({'system': system, 'prompt': prompt}), capture_output=True, text=True, timeout=900)
    text = run.stdout
    start, end = text.find('{'), text.rfind('}')
    if run.returncode or start < 0 or end <= start: raise Unavailable('The planner command failed: '+(run.stderr or text)[-200:])
    return json.loads(text[start:end+1])


BACKENDS = {'claude': _claude, 'command': _command}


def _ready(name):
    if name == 'claude':
        from ... import claude_code
        return bool(claude_code.signed_in())
    if name == 'command': return bool(os.getenv('CASCADE_EDIT_PLANNER_CMD', '').strip())
    return False


def ai():
    """The AI planners to try, in order, for the current configuration."""
    picked = choice()
    names = ['claude', 'command'] if picked == 'auto' else [picked] if picked in BACKENDS else []
    return [n for n in names if _ready(n)]


def label(name):
    return f'{name}:{model()}' if name == 'claude' and model() else name


def _direct(prompt, prep_dir, prep):
    system, images = director.instructions(), director.images(prep_dir, prep)
    problem = 'No AI planner is set up (sign in to Claude Code, or set CASCADE_EDIT_PLANNER_CMD).'
    for name in ai():
        try:
            return director.direct(lambda p: BACKENDS[name](system, p, images), prompt, prep['words']), label(name)
        except Exception as exc:   # try the next planner; the caller decides what to do when none is left
            problem = str(getattr(exc, 'detail', None) or exc)[:300]
    raise Unavailable(problem)


def plan_edit(request, prep_dir, prep, windows, history):
    """(plan, who planned it). Falls back to the rule-based director, so a first edit always succeeds."""
    if choice() != 'rules':
        try:
            return _direct(director.new_edit(request, prep, windows, history), prep_dir, prep)
        except Unavailable:
            pass
    return plans.auto(prep['words']), 'rules'


def revise(note, current, prep_dir, prep, windows, history):
    """(plan, who). Raises Unavailable when no AI planner can take a creative change."""
    if choice() == 'rules': raise Unavailable('The planner is set to "rules", which cannot take creative changes.')
    return _direct(director.change(note, current, prep, windows, history), prep_dir, prep)
