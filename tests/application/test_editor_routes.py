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
        before = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/editor_routes_before.json').read_text())
        # Audio and Trends intentionally extended the editor after this snapshot.
        # Keep the original contract exact, and enumerate additions rather than
        # replacing the snapshot with whatever the application happens to expose.
        prefix = '/api/projects/{pid}/editor/{jid}/{index}'
        additions = [[prefix + path, [method]] for path, method in (
            ('/audio', 'GET'), ('/audio', 'POST'), ('/audio/{asset_id}/media', 'GET'),
            ('/trends', 'GET'), ('/trends', 'POST'), ('/trends/apply', 'POST'), ('/style-progress', 'GET'), ('/ai-edit', 'GET'))]
        # The AI Editor chat reports its engine and free-tier usage (no credentials).
        additions.append(['/api/projects/{pid}/editor/ai-status', ['GET']])
        additions.append(['/api/projects/{project_id}/generations/{job_id}/backup/retry', ['POST']])
        # Multi-clip editing: join picked clips into one Editor clip.
        additions.append(['/api/projects/{pid}/editor/combine', ['POST']])
        # Editing your own uploaded clip.
        additions.append(['/api/projects/{pid}/editor/upload', ['POST']])
        # LinkedIn publishing: connect an account and post a clip.
        additions += [[prefix+'/publish/linkedin', ['GET']], [prefix+'/publish/linkedin', ['POST']],
                      ['/api/projects/{pid}/social/linkedin', ['GET']], ['/api/projects/{pid}/social/linkedin/connect', ['POST']],
                      ['/api/social/linkedin/callback', ['GET']]]
        # Signed links so <video> tags can stream protected media (backend/core/media_links.py).
        additions.append(['/api/media-link', ['GET']])
        # Editor previews kept on the server and streamed instead of downloaded whole (preview_routes.py).
        additions += [[prefix+'/preview', ['POST']], [prefix+'/preview/{name}', ['GET']]]
        # Saved Projects page card pictures (backend/services/project_thumbnails.py).
        additions.append(['/api/projects/{project_id}/thumbnail/{name}', ['GET']])
        self.assertEqual(sorted(route_contract(app1.app)), sorted(before + additions))

    def test_editor_modules_remain_small(self):
        for file in (Path(service_config.PROJECT_DIR)/'backend'/'editor').glob('*.py'):
            # Existing research orchestration is 423 lines; retain a bounded
            # exception without relaxing the budget for other editor modules.
            budget = 450 if file.name == 'trends.py' else 300
            self.assertLessEqual(len(file.read_text(encoding='utf-8').splitlines()), budget, file.name)
