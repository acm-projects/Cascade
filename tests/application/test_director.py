"""AI Director routing and recipes, offline: no Gemini, YouTube, Ollama or Pexels calls."""
import unittest
from unittest.mock import patch

from backend.editor.director_models import Analysis, DirectorPlan
from backend.editor.models import Edit
from backend.editor.style_requests import parse_request, wants_director


class FakeAudio:
    def library(self):
        return [{'id': 'aud-'+'a'*32, 'kind': 'music', 'name': 'Quiet reflection', 'tags': [], 'duration': 30}]


class FakeStock:
    def search(self, query): return {'results': []}


class DirectorTests(unittest.TestCase):
    def test_open_requests_go_to_the_director_and_fan_edits_stay_explicit(self):
        for message in ('edit this video', 'make this viral', 'make it a dramatic edit', 'you decide', 'make a memorial edit'):
            self.assertTrue(wants_director(message), message)
        for message in ('make this a spiderman fan edit', 'make captions yellow', 'remove the fan edit', 'trim the first 3 seconds'):
            self.assertFalse(wants_director(message), message)
        self.assertEqual(parse_request('make this a spiderman fan edit, edited by Manila')['options'].end_card, 'Cascade')

    def test_memorial_recipe_is_clean_and_ends_with_cascade(self):
        from backend.editor.director_recipes import apply_plan
        plan = DirectorPlan(style='memorial', look='bw', pacing='slow', captions='clean', music='Quiet reflection',
                            emphasis=[{'text': 'shot three times', 'at': 4}, {'text': 'racial incident', 'at': 11}],
                            key_moments=[{'at': 3, 'importance': .9}, {'at': 29, 'importance': 1}])
        state, notes = apply_plan(Edit(start=0, end=45), plan, {'cues': []}, FakeStock(), FakeAudio())
        kinds = [e.kind for e in state.stylize.events]
        self.assertIn('film', kinds)
        self.assertEqual(state.stylize.events[-1].text, 'Cascade')
        self.assertEqual([e.text for e in state.stylize.events if e.kind == 'text'], ['SHOT THREE TIMES', 'RACIAL INCIDENT'])
        self.assertTrue(all(e.size < .7 and not e.behind for e in state.stylize.events if e.kind == 'text'))  # clean, not kinetic
        self.assertEqual((len(state.motion), state.audio[0].volume, state.transition.fade_in), (2, .1, .8))
        self.assertIn('ends with "Edited by Cascade"', notes)

    def test_podcast_recipe_tightens_pauses(self):
        from backend.editor.director_recipes import apply_plan
        cues = [{'start': 0, 'end': 4, 'text': 'a'}, {'start': 6, 'end': 9, 'text': 'b'}, {'start': 9.2, 'end': 12, 'text': 'c'}]
        plan = DirectorPlan(style='podcast', captions='karaoke', tighten_pauses=True)
        state, notes = apply_plan(Edit(start=0, end=12), plan, {'cues': cues}, FakeStock(), FakeAudio())
        self.assertEqual([(s.start, s.end) for s in state.timeline], [(0, 4.15), (5.85, 12)])
        self.assertEqual(state.captions.animation, 'karaoke')

    def test_without_any_model_the_genre_still_picks_a_fitting_edit(self):
        from backend.editor import director
        cues = [{'start': 1, 'end': 4, 'text': 'The soldiers in our army camp were shot'}]
        with patch.object(director, '_gemini', side_effect=director.HTTPException(503)), \
                patch.object(director, '_local', side_effect=OSError()), patch.object(director, '_proxy', side_effect=OSError()):
            analysis, how = director.analyze('missing.mp4', Edit(start=0, end=10), {'cues': cues}, [], 'War story')
            chosen, source = director.plan(analysis, {'references': []}, 'edit this', Edit(start=0, end=10))
        self.assertEqual((analysis.genre, chosen.style, chosen.look, source), ('documentary_history', 'memorial', 'bw', 'genre defaults'))
        self.assertIsInstance(analysis, Analysis)


if __name__ == '__main__':
    unittest.main()
