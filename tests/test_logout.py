"""Real cookie fallback cleanup and auth requirements; no external identity requests."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
import app1

class LogoutTests(unittest.TestCase):
    def test_cookie_fallback_cleared_without_removing_projects_or_drafts(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(app1,'JOBS_DIR',Path(folder)), \
             patch.object(app1,'verify_clerk_token',return_value='logout-user'), \
             patch.object(app1,'authorized_parties',return_value=['http://testserver']):
            client=TestClient(app1.app)
            client.cookies.set('__session','fixture-token',domain='testserver.local',path='/')
            pid=client.post('/api/projects',json={'name':'Preserve my project'}).json()['id']
            from backend import integration
            draft=integration.project_dir('logout-user')/'editor'/pid/'fixture.json'
            draft.parent.mkdir(parents=True);draft.write_text('{"saved":"draft"}')
            # MLK records the Clerk user on the first authenticated session check.
            self.assertEqual(client.get('/api/session').status_code,200)
            before={str(p.relative_to(folder)):p.read_bytes() for p in Path(folder).rglob('*') if p.is_file()}
            response=client.post('/api/logout',headers={'Origin':'http://testserver'})
            self.assertEqual(response.status_code,200);self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertIn('Max-Age=0',response.headers['set-cookie'])
            self.assertNotIn('__session',client.cookies)
            for path in ['/api/session','/api/projects','/api/my-clips','/api/projects/'+pid+'/editor']:
                self.assertEqual(client.get(path).status_code,401,path)
            after={str(p.relative_to(folder)):p.read_bytes() for p in Path(folder).rglob('*') if p.is_file()}
            self.assertEqual(before,after)
            self.assertEqual(client.post('/api/logout').status_code,200) # retry after revocation
            self.assertEqual(client.post('/api/logout',headers={'Origin':'https://evil.invalid'}).status_code,403)
            self.assertEqual(client.post('/api/logout',headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)

if __name__=='__main__':unittest.main()
