"""Render exactly one existing page view from the single website template.

Native document navigation is intentional: URLs, Back/Forward, per-page CSS,
Clerk initialization and media teardown keep their existing behavior.
"""
from pathlib import Path
import hashlib

from jinja2 import Environment, FileSystemLoader, StrictUndefined

PAGES = {
    'index.html': 'home',
    'index_C.html': 'home',
    'login_C.html': 'login',
    'projects_C.html': 'projects',
    'canvas_C.html': 'canvas',
    'editor_C.html': 'editor',
    'exports_C.html': 'exports',
    'settings_C.html': 'settings',
}


def render_page(filename: str, directory: Path) -> str:
    if filename not in PAGES:
        raise ValueError('Unknown website view')
    # HTML-comment delimiters avoid interpreting literal CSS/JS braces.
    environment = Environment(
        loader=FileSystemLoader(str(directory)),
        autoescape=True, undefined=StrictUndefined, keep_trailing_newline=True,
        block_start_string='<!--%', block_end_string='%-->',
    )
    build = hashlib.sha256()
    for asset in ('flow_C.js', 'studio/studio.js', 'studio/studio.css'):
        path = directory / asset
        if path.is_file():
            build.update(path.read_bytes())
    return environment.get_template('index.html').render(view=PAGES[filename], studio_build=build.hexdigest()[:16])
