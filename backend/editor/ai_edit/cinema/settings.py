"""The editing rules in style.json, loaded once. `get('dialogue.max_pause', .16)` reads one value."""
import json
from pathlib import Path

STYLE = json.loads((Path(__file__).parent/'style.json').read_text())


def get(path, default=None):
    node = STYLE
    for key in path.split('.'):
        if not isinstance(node, dict) or key not in node: return default
        node = node[key]
    return node
