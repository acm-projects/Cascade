"""Single-template routing must preserve isolated page documents and auth fallback."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import os
import re
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import app1
from backend import frontend


class Document(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.bodies=[];self.scripts=[];self.heads=0
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if 'id' in values:self.ids.append(values['id'])
        if tag=='body':self.bodies.append(values.get('data-page','home'))
        if tag=='head':self.heads+=1
        if tag=='script':self.scripts.append(values.get('src'))


class FrontendViewsTests(unittest.TestCase):
    def test_one_html_file_and_isolated_view_per_legacy_route(self):
        self.assertEqual(list(app1.FRONTEND_DIR.glob('*.html')),[app1.FRONTEND_DIR/'index.html'])
        # Legacy root pages may remain for compatibility; only the web template is served.
        self.assertEqual(app1.FRONTEND_DIR,app1.PROJECT_DIR/'web')
        with TestClient(app1.app) as client:
            for filename,view in frontend.PAGES.items():
                response=client.get('/'+filename)
                self.assertEqual(response.status_code,200)
                document=Document();document.feed(response.text)
                self.assertEqual(document.bodies,[view],filename)
                self.assertEqual(document.heads,1,filename)
                self.assertFalse([id for id,count in Counter(document.ids).items() if count>1],filename)
                self.assertNotIn('<!--%',response.text)
                self.assertEqual(document.scripts.count('flow_C.js'),0 if view=='home' else 1)
                self.assertEqual('editor_C.js' in document.scripts,view=='editor')
                self.assertEqual('canvas_branches.js' in document.scripts,view=='canvas')
            self.assertEqual(client.get('/').text,client.get('/index_C.html').text)
            self.assertEqual(client.get('/login').text,client.get('/login_C.html').text)
            self.assertEqual(client.get('/settings').text,client.get('/settings_C.html').text)

    def test_legacy_fallback_is_preserved_without_serving_template_configuration(self):
        source=(app1.FRONTEND_DIR/'index.html').read_text(encoding='utf-8')
        expected=re.search(r'legacy_clerk_publishable_key\s*=\s*"([^"]+)"',source).group(1)
        with patch.dict(os.environ,{'CLERK_PUBLISHABLE_KEY':''}):
            self.assertEqual(app1.clerk_configuration()[0],expected)
        with TestClient(app1.app) as client:
            for filename in frontend.PAGES:
                self.assertNotIn('legacy_clerk_publishable_key',client.get('/'+filename).text)

    def test_unknown_views_cannot_render_template_source(self):
        for name in ['../.env','login.html','index.html?view=editor','arbitrary']:
            with self.assertRaises(ValueError):frontend.render_page(name,app1.FRONTEND_DIR)
