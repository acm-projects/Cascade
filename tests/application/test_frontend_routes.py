"""Guard the public URL contract when frontend files are reorganized."""
from html.parser import HTMLParser
from urllib.parse import urlsplit
import unittest

from fastapi.testclient import TestClient
import app1
from backend.core import config as service_config


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ('src', 'href') and value:
                self.urls.append(value)


class FrontendRoutesTests(unittest.TestCase):
    def test_every_public_page_and_local_asset_resolves(self):
        with TestClient(app1.app) as client:
            for filename in sorted(service_config.FRONTEND_FILES):
                with self.subTest(filename=filename):
                    response = client.get('/' + filename)
                    self.assertEqual(response.status_code, 200)
                    if not filename.endswith('.html'):
                        continue
                    parser = References()
                    parser.feed(response.text)
                    for url in parser.urls:
                        parsed = urlsplit(url)
                        if parsed.scheme or parsed.netloc or not parsed.path:
                            continue
                        path = '/' + parsed.path.lstrip('/')
                        self.assertEqual(client.get(path).status_code, 200, (filename, url))

    def test_source_and_configuration_remain_private(self):
        with TestClient(app1.app) as client:
            for path in ('/.env', '/.env.example', '/login.html', '/app1.py',
                         '/backend/editor_backend.py', '/web/editor_C.html', '/web/index.html',
                         '/docs/setup.md'):
                with self.subTest(path=path):
                    self.assertEqual(client.get(path).status_code, 404)
