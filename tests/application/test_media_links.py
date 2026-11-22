"""Signed media links: a <video> tag can stream a protected clip in pieces without the sign-in header."""
import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from backend.core import media_links
from tests.application import test_editor


class MediaLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_editor.EditorTests.setUpClass()

    def setUp(self):
        self.env = patch.dict(os.environ, {'CASCADE_MEDIA_SECRET': 'test-secret'}); self.env.start()
        self.fx = test_editor.EditorTests(); self.fx.setUp()
        self.media = self.fx.url+'/media'

    def tearDown(self):
        self.fx.tearDown(); self.env.stop()

    def link(self, path=None):
        response = self.fx.client.get('/api/media-link', params={'path': path or self.media}, headers=self.fx.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['url']

    def test_a_signed_link_streams_the_clip_in_pieces_without_the_header(self):
        url = self.link()
        whole = self.fx.client.get(url)
        self.assertEqual(whole.status_code, 200)
        self.assertEqual(whole.headers['accept-ranges'], 'bytes')
        piece = self.fx.client.get(url, headers={'Range': 'bytes=0-99'})
        self.assertEqual(piece.status_code, 206)
        self.assertEqual(len(piece.content), 100)
        self.assertEqual(piece.content, whole.content[:100])

    def test_a_link_only_works_for_its_own_file(self):
        token = parse_qs(urlsplit(self.link()).query)[media_links.PARAM][0]
        other = self.fx.url+'/thumbnail'
        self.assertEqual(self.fx.client.get(other, params={media_links.PARAM: token}).status_code, 401)
        tampered = token[:20]+('A' if token[20] != 'A' else 'B')+token[21:]
        self.assertEqual(self.fx.client.get(self.media, params={media_links.PARAM: tampered}).status_code, 401)
        self.assertEqual(self.fx.client.get(self.media).status_code, 401)   # no link, no header

    def test_a_link_never_grants_someone_elses_clip(self):
        token = media_links.sign(self.media, 'intruder')
        self.assertEqual(self.fx.client.get(self.media, params={media_links.PARAM: token}).status_code, 404)

    def test_only_media_addresses_are_signed(self):
        for path in ('/api/settings', '/api/projects/../settings', self.media+'?x=1'):
            response = self.fx.client.get('/api/media-link', params={'path': path}, headers=self.fx.headers)
            self.assertEqual(response.status_code, 422, path)

    def test_links_expire(self):
        token = media_links.sign(self.media, 'editor-user')
        with patch.object(media_links, 'LINK_HOURS', -1):
            self.assertIsNone(media_links.user_for(token, self.media))


if __name__ == '__main__':
    unittest.main()
