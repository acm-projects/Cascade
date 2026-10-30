"""No external requests: safe stage diagnostics, filters, and stronger style mapping."""
import os,json,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from backend.trends.diagnostics import stage,failure,safe_text,StageError,ResearchFailure
from backend.trends import pipeline
from backend.trends import youtube_trends
from tests.test_clip_trends import ClipTrendsTests

class DiagnosticsTests(unittest.TestCase):
    def test_missing_data_key_uses_real_public_discovery_adapter(self):
        with patch.dict(os.environ,{'YOUTUBE_API_KEY':''}),patch.object(youtube_trends,'YOUTUBE_API_KEY',None),patch.object(youtube_trends,'public_search',return_value=[{'video_id':'abcdefghijk'}]) as public:
            result=youtube_trends.get_trending_videos('dialogue editing',limit=2)
        self.assertEqual(result,[{'video_id':'abcdefghijk'}]);public.assert_called_once_with('dialogue editing',2)
    def test_secrets_and_query_urls_never_reach_diagnostics(self):
        with patch.dict(os.environ,{'YOUTUBE_API_KEY':'fake-private-key-value'}):
            text=safe_text('request https://service.test/search?key=fake-private-key-value Token fake-private-key-value')
        self.assertNotIn('fake-private-key-value',text);self.assertNotIn('?key=',text)
    def test_failure_categories_and_synthesis_keyword_forwarding(self):
        class Error(Exception):pass
        for status,label,expected in [(401,'ai_tagging','authentication'),(404,'ai_tagging','model_unavailable'),(429,'transcription','rate_limited'),(402,'transcription','quota_or_credit_exhausted')]:
            error=Error('provider failure');error.status_code=status
            self.assertEqual(failure(error,label)['code'],expected)
        error=Error('quota');error.resp=type('Response',(),{'status':403})();error.content=json.dumps({'error':{'errors':[{'reason':'quotaExceeded'}]}}).encode()
        self.assertEqual(failure(error,'discovery')['code'],'quota_or_credit_exhausted')
        self.assertEqual(failure(Error('Sign in to confirm you are not a bot'),'download')['code'],'youtube_bot_challenge')
        self.assertEqual(failure(Error('This video is unavailable'),'download')['code'],'video_unavailable')
        self.assertEqual(failure(Error('\x1b[0;31mERROR:\x1b[0m This video is not available'),'discovery_metadata')['code'],'video_unavailable')
        self.assertNotIn('\x1b',safe_text('\x1b[0;31mERROR:\x1b[0m This video is not available'))
        self.assertEqual(stage('ai_synthesis',lambda **kw:kw['name'],name='schema_name'),'schema_name')
    def test_original_stage_and_partial_references_survive_wrapping(self):
        def inner():raise StageError({'stage':'transcription','code':'authentication','reason':'Rejected'})
        with self.assertRaises(StageError) as context:stage('reference_analysis',inner)
        self.assertEqual(context.exception.detail['stage'],'transcription')
        def partial():raise ResearchFailure('Synthesis unavailable',[{'stage':'ai_synthesis'}],[{'url':'https://www.youtube.com/watch?v=abcdefghijk'}])
        with self.assertRaises(ResearchFailure) as context:stage('discovery',partial)
        self.assertTrue(context.exception.references)
    def test_long_reference_has_explicit_error_not_missing_file(self):
        with tempfile.TemporaryDirectory() as d,patch.object(pipeline.yt_dlp,'YoutubeDL') as mock:
            options=[]
            def make(config):options.append(config);return mock.return_value
            mock.side_effect=make
            def download(urls):options[0]['match_filter']({'duration':601})
            mock.return_value.__enter__.return_value.download.side_effect=download
            with self.assertRaisesRegex(RuntimeError,'600s analysis limit'):pipeline.download_video('abcdefghijk',Path(d))

class StrongStyleTests(ClipTrendsTests):
    # Reuse the existing real HTTP/FFmpeg fixture; only add a profile comparison.
    def test_flashy_profile_is_visibly_stronger_than_default(self):
        record=self.analyze()
        with patch('backend.broll.Store.search',return_value={'results':[]}):
            normal=self.client.post(self.base+'/apply',headers=self.headers,json={'state':self.state,'research_id':record['id']}).json()
            flashy=self.client.post(self.base+'/apply',headers=self.headers,json={'state':self.state,'research_id':record['id'],'intensity':'flashy'}).json()
        self.assertGreater(max(m['scale_to'] for m in flashy['state']['motion']),max(m['scale_to'] for m in normal['state']['motion']))
        self.assertEqual(flashy['state']['captions']['max_words'],3)
        self.assertEqual(flashy['state']['reel']['intensity'],'flashy')
        self.assertEqual(flashy['state']['dialogue_volume'],normal['state']['dialogue_volume'])

if __name__=='__main__':unittest.main()
