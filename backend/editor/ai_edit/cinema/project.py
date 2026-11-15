"""A saved edit. Every version of an AI edit is one folder holding:

  project.json   the whole edit as data: the creative plan (story order, cuts, keywords, moments, b-roll,
                 music mood, message, switches), who planned it, and the resolved timeline it rendered to
  edited.mp4     the render of that project

A project re-renders with `engine.make` and no AI model, and any model (or a person) can change it by
editing the plan. `plan.json` (the first releases' file) is still read."""
import json
import time
from pathlib import Path

from .plan import CinemaPlan

SCHEMA = 1


def save(folder, plan, report=None, planner='', request='', source=None):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    report = dict(report or {})
    data = {'schema': SCHEMA, 'engine': 'cinema', 'saved': time.time(), 'planner': planner, 'request': request[:500],
            'source': source or {}, 'plan': plan.model_dump(), 'timeline': report.pop('timeline', None), 'report': report}
    (folder/'project.json').write_text(json.dumps(data, indent=1))
    (folder/'plan.json').write_text(json.dumps(plan.model_dump()))   # kept for older code that reads it
    return data


def load(folder):
    """The CinemaPlan saved in `folder`, or None when it holds no Cinema project."""
    folder = Path(folder)
    for name, key in (('project.json', 'plan'), ('plan.json', None)):
        try:
            data = json.loads((folder/name).read_text())
            data = data[key] if key else data
            if 'story' in data: return CinemaPlan.model_validate(data)
        except (OSError, ValueError, KeyError):
            continue
    return None


def read(folder):
    try:
        return json.loads((Path(folder)/'project.json').read_text())
    except (OSError, ValueError):
        return None
