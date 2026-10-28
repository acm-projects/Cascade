"""CAS-43 preserves the complete public route contract and module size budget."""
import json
import unittest
from pathlib import Path
import app1


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
        self.assertEqual(sorted(route_contract(app1.app)), before)

    def test_editor_modules_remain_small(self):
        for file in (Path(app1.PROJECT_DIR)/'backend'/'editor').glob('*.py'):
            self.assertLessEqual(len(file.read_text(encoding='utf-8').splitlines()), 300, file.name)
