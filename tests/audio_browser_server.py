"""Opt-in isolated React audio smoke fixture; mocks AI/identity, uses real media."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import app1
from tests.test_audio_media import AudioMediaTests


if __name__ == '__main__':
    AudioMediaTests.setUpClass()
    fixture = AudioMediaTests('test_mp3_podcast_through_generation_editor_and_native_exports')
    fixture.setUp()
    try:
        app1.DEV_AUTH = True
        app1.DEV_USER_ID = 'audio-user'
        # Existing localhost Clerk cookies also apply across ports. This fixture
        # has its own temporary identity and never reads a real user's projects.
        app1.is_dev_auth_request = lambda request: request.client.host in app1.LOCAL_HOSTS
        app1.authorized_parties = lambda: ['http://127.0.0.1:8768']
        os.environ['CASCADE_WARM_MODELS'] = '0'
        os.environ['SOCIAL_DATABASE_PATH'] = str(fixture.root/'social.sqlite3')
        jid, clip = fixture.generate(fixture.audio)
        fixture.client.put(f'/api/projects/{fixture.pid}/studio/editor-selection', headers=fixture.headers,
                           json={'clips':[{'job_id':jid,'clip_index':0}]})
        app1.select_with_agent = lambda *args, **kwargs: ([],[],{'selection_note':'Offline fixture; upload paid AI is disabled.'})
        dist = Path(app1.PROJECT_DIR)/'frontend'/'dist'
        app1.app.mount('/assets', StaticFiles(directory=dist/'assets'))
        @app1.app.get('/projects/{path:path}')
        def frontend(path: str):
            return FileResponse(dist/'index.html')
        print(f'AUDIO_FIXTURE_URL=http://127.0.0.1:8768/projects/{fixture.pid}/editor', flush=True)
        uvicorn.run(app1.app, host='127.0.0.1', port=8768, log_level='warning')
    finally:
        fixture.doCleanups()
        AudioMediaTests.tearDownClass()
