"""Trends on the Claude plan: never touches a paid provider while the plan is active."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend import cascade_llm
from backend.trends import claude_route, pipeline


class ClaudeRoute(unittest.TestCase):
    def test_tags_go_through_the_plan_with_every_field_present(self):
        with TemporaryDirectory() as folder, patch.object(claude_route, 'active', return_value=True), \
                patch.object(pipeline, 'TAGS_CACHE_DIR', Path(folder)), \
                patch.object(pipeline, 'make_client', side_effect=AssertionError('paid client must not be created')), \
                patch('backend.editor.claude_code.ask', return_value={'pacing': 'very fast', 'tone': 'dry', 'surprise': 1}) as ask:
            frame = Path(folder)/'frame.jpg'; frame.write_bytes(b'jpeg')
            tags = pipeline.extract_tags([frame], 'hello')
        self.assertEqual(tags['tone'], 'dry')
        self.assertEqual(tags['pacing'], 'medium')  # outside the schema's choices
        self.assertEqual(tags['visual_style'], [])
        self.assertNotIn('surprise', tags)
        self.assertEqual(ask.call_args.args[2], [('frame.jpg', b'jpeg')])

    def test_synthesis_goes_through_the_plan_only_when_it_is_active(self):
        with patch.object(claude_route, 'active', return_value=True), patch('backend.editor.claude_code.ask', return_value={'summary': 'x'}), \
                patch.object(cascade_llm, 'structured_json', side_effect=AssertionError('paid provider must not be called')):
            self.assertEqual(claude_route.structured_json('prompt', {}, name='n', max_output_tokens=10).data, {'summary': 'x'})
        with patch.object(claude_route, 'active', return_value=False), patch.object(cascade_llm, 'structured_json', return_value='configured') as configured:
            self.assertEqual(claude_route.structured_json('prompt', {}, name='n', max_output_tokens=10), 'configured')
        self.assertEqual(configured.call_args.kwargs['max_output_tokens'], 10)

    def test_transcripts_are_youtube_captions_and_never_the_paid_service(self):
        with TemporaryDirectory() as folder, patch.object(claude_route, 'active', return_value=True), \
                patch.object(pipeline, 'transcribe_media', side_effect=AssertionError('paid transcription must not be called')):
            reference = Path(folder)/'abcdefghijk'; reference.mkdir()
            with patch.object(claude_route, 'captions', return_value='spoken words') as captions:
                self.assertEqual(pipeline.transcribe(reference/'audio.wav'), 'spoken words')
            captions.assert_called_once_with('abcdefghijk')
        self.assertEqual(claude_route.captions('not-a-video-id-because-too-long'), '')

    def test_caption_files_become_plain_text_without_rolling_repeats(self):
        vtt = 'WEBVTT\nKind: captions\nLanguage: en\n\n00:00.000 --> 00:01.000\nhello<00:00.500><c> world</c>\n\n00:01.000 --> 00:02.000\nhello world\n\n00:02.000 --> 00:03.000\nnext line\n'
        self.assertEqual(claude_route._caption_text(vtt), 'hello world next line')


if __name__ == '__main__':
    unittest.main()
