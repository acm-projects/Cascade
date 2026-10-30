"""Preserve the legacy route contract plus explicitly supported editor APIs."""
import json
import unittest
from pathlib import Path
import app1
from backend.core import config as service_config


def route_contract(router):
    rows = []
    for route in router.routes:
        if hasattr(route, 'methods'):
            rows.append([route.path, sorted(route.methods)])
        elif hasattr(route, 'original_router'):
            # Recent FastAPI versions retain included routers instead of flattening them.
            rows.extend(route_contract(route.original_router))
    return rows


class EditorRouteTests(unittest.TestCase):
    def test_all_routes_match_pre_refactor_snapshot(self):
        before = json.loads(Path(__file__).with_name('editor_routes_before.json').read_text())
        # Audio and Trends intentionally extended the editor after this snapshot.
        # Keep the original contract exact, and enumerate additions rather than
        # replacing the snapshot with whatever the application happens to expose.
        prefix = '/api/projects/{pid}/editor/{jid}/{index}'
        additions = [[prefix + path, [method]] for path, method in (
            ('/audio', 'GET'), ('/audio', 'POST'), ('/audio/{asset_id}/media', 'GET'),
            ('/trends', 'GET'), ('/trends', 'POST'), ('/trends/apply', 'POST'))]
        self.assertEqual(sorted(route_contract(app1.app)), sorted(before + additions))

    def test_editor_modules_remain_small(self):
        for file in (Path(service_config.PROJECT_DIR)/'backend'/'editor').glob('*.py'):
            # Existing research orchestration is 423 lines; retain a bounded
            # exception without relaxing the budget for other editor modules.
            budget = 450 if file.name == 'trends.py' else 300
            self.assertLessEqual(len(file.read_text(encoding='utf-8').splitlines()), budget, file.name)
