"""Reference edits: a shot list in the request becomes a plan with the reference's exact cut times."""
import unittest
from unittest.mock import patch

from backend.editor.ai_edit.cinema import reference

REQUEST = '''Make it exactly like my reference. Opening line: "I wish that I could STAY here..." It loops back at 0:15.12.
| Edit time | Source time | What to use |
| 0:00.08 | DJI 0013 · 0:02.36 | Hands in, us saying one two three (voice through 0.35) |
| 0:02.57 | IMG_6228 · 0:07.4 | Sun through the branches, whip |
| **0:03.85** | **IMG_6229 · 0:08.5** | Zoom blur into the crouch |
| 0:13.40 | DJI 0017 · 13:57.00 | Silhouette |
| 0:13.48 | DJI 0017 · 13:57.10 | Cut out in front of IMG_6233 5:52.20 |
'''


class ReferenceTests(unittest.TestCase):
    def test_rows_times_and_words(self):
        rows = reference.rows(REQUEST)
        self.assertEqual([r['at'] for r in rows], [.08, 2.57, 3.85, 13.4, 13.48])
        self.assertEqual((rows[3]['file'], rows[3]['src']), ('DJI 0017', 837.0))
        self.assertEqual(reference.ending(REQUEST, rows), 15.12)
        self.assertEqual(reference.line_of(REQUEST), 'I wish that I could STAY here...')

    def test_the_plan_keeps_every_cut_and_effect(self):
        footage = reference.Footage(['/x/Video_1_DJI_2026_0013_D.MP4', '/x/IMG_6228.MOV', '/x/IMG_6229.MOV',
                                     '/x/Video_9_DJI_2026_0017_D.MP4', '/x/IMG_6233.MOV'])
        self.assertTrue(str(footage.find('DJI 0017')).endswith('0017_D.MP4'))
        with patch.object(reference, 'gather', side_effect=lambda moments, *a, **k: [10.*i for i in range(len(moments))]):
            plan = reference.build(REQUEST, footage, '/tmp/x.mp4', end=15.12)
        lengths = [round(s.end-s.start, 2) for s in plan.shots]
        self.assertEqual(lengths, [2.49, 1.28, 9.55, .08, 1.64])
        self.assertEqual([s.effect for s in plan.shots], [None, 'whip', 'zoom', None, None])
        self.assertTrue(plan.shots[0].voice and plan.shots[0].voice_through == .35)
        self.assertTrue(plan.shots[3].silhouette)
        self.assertEqual(plan.shots[4].backdrop, 50.)   # the background moment, gathered after the shots
        self.assertTrue(plan.exact)


if __name__ == '__main__':
    unittest.main()
