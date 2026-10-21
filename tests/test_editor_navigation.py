import unittest
from backend.editor_navigation import label_waves

class NavigationTests(unittest.TestCase):
    def test_sessions_follow_ancestry_and_variable_waves(self):
        rows=[{'job_id':'root','prompt':'Sad moments'},
              {'job_id':'other','prompt':'Funny moments'},
              {'job_id':'follow','parent_clip':{'job_id':'root'}},
              {'job_id':'deeper','parent_clip':{'job_id':'follow'}},
              {'job_id':'sibling','parent_clip':{'job_id':'root'}}]
        result=label_waves(rows)
        self.assertEqual([(r['session_number'],r['wave_number']) for r in result],[(1,1),(2,1),(1,2),(1,3),(1,4)])
        self.assertEqual(result[-1]['session_prompt'],'Sad moments')
        self.assertEqual(result[-1]['session_id'],'root')

    def test_missing_parent_does_not_attach_to_another_session(self):
        rows=label_waves([{'job_id':'a'},{'job_id':'b','parent_clip':{'job_id':'gone'}}])
        self.assertEqual([r['session_number'] for r in rows],[1,2])

    def test_same_source_prompt_uses_one_session_distinct_real_waves(self):
        rows=label_waves([{'job_id':'root','source_job':'root','prompt':'Find sad moments'},
                         {'job_id':'again','source_job':'root','prompt':' Find  sad moments '},
                         {'job_id':'new','source_job':'root','prompt':'Find funny moments'}])
        self.assertEqual([(r['session_number'],r['wave_number'])for r in rows],[(1,1),(1,2),(2,1)])

    def test_explicit_wave_variants_do_not_create_an_extra_wave(self):
        rows=label_waves([{'job_id':'a','session_id':'session','wave_id':'one'},
                         {'job_id':'b','session_id':'session','wave_id':'one'},
                         {'job_id':'c','session_id':'session','wave_id':'two'}])
        self.assertEqual([r['wave_number']for r in rows],[1,1,2])
