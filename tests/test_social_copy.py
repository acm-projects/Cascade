import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tests.test_editor import EditorTests
from backend.services import social_copy as service
from fastapi import HTTPException
import app1


class SocialCopyTests(unittest.TestCase):
    setUpClass = classmethod(EditorTests.setUpClass.__func__)
    tearDownClass = classmethod(EditorTests.tearDownClass.__func__)
    setUp = EditorTests.setUp
    tearDown = EditorTests.tearDown
    job = EditorTests.job
    get = EditorTests.get

    def output(self):
        return {'youtube':{'title':'An important insight '*30,'description':'First line\nSecond line','hashtags':['#Test','test','Two words']},
                'tiktok':{'caption':'😀 useful insight '*1000,'hashtags':['test']},
                'instagram':{'caption':'An insight '*1000,'hashtags':['test']},
                'linkedin':{'post':'Professional insight '*1000,'hashtags':['one','two','three','four']}}

    def test_all_platforms_validated_grounded_and_cached_by_trim_vibe(self):
        url=f'/api/projects/{self.pid}/clips/{self.jid}/0/social-copy'
        # Trim away the cue; social copy must not include text outside edited footage.
        draft=self.get()['draft'];draft['state'].update(start=0,end=.4)
        self.client.put(self.url,headers=self.headers,json=draft)
        body={'platforms':['youtube','tiktok','instagram','linkedin'],'vibe':'calm and educational'}
        with patch.object(service,'structured_json',return_value=SimpleNamespace(data=self.output())) as llm:
            response=self.client.post(url,headers=self.headers,json=body)
            self.assertEqual(response.status_code,200,response.text)
            data=response.json()
            self.assertLessEqual(len(data['youtube']['title']),100)
            self.assertIn('#Shorts',data['youtube']['hashtags'])
            for platform,field in [('tiktok','caption'),('instagram','caption'),('linkedin','post')]:
                self.assertLessEqual(service.units(data[platform][field]+' '+' '.join(data[platform]['hashtags'])),service.PLATFORM_RULES[platform]['limit'])
            self.assertLessEqual(len(data['linkedin']['hashtags']),3)
            prompt=llm.call_args.args[0]
            self.assertIn('Professional',prompt);self.assertIn(body['vibe'],prompt)
            self.assertNotIn('Hello world',prompt)
            self.assertEqual(self.client.post(url,headers=self.headers,json=body).json(),data)
            self.assertEqual(llm.call_count,1)
            self.client.post(url+'?refresh=true',headers=self.headers,json=body)
            self.assertEqual(llm.call_count,2)
            draft['state']['end']=1
            self.client.put(self.url,headers=self.headers,json=draft)
            self.client.post(url,headers=self.headers,json=body)
            self.assertEqual(llm.call_count,3)
            self.assertIn('Hello world',llm.call_args.args[0])
            self.assertEqual(self.client.post(url,headers={'Authorization':'Bearer stranger'},json=body).status_code,404)
            self.assertEqual(llm.call_count,3)

    def test_input_validation_and_provider_failures(self):
        url=f'/api/projects/{self.pid}/clips/{self.jid}/0/social-copy'
        for body in [{'platforms':[]},{'platforms':['invalid']},{'platforms':['youtube'],'vibe':'x'*301}]:
            self.assertEqual(self.client.post(url,headers=self.headers,json=body).status_code,422)
        with patch.object(service,'structured_json',side_effect=service.LLMConfigError('Missing key')):
            self.assertEqual(self.client.post(url,headers=self.headers,json={'platforms':['youtube']}).status_code,503)
        with patch.object(service,'structured_json',return_value=SimpleNamespace(data={'youtube':{'title':123}})):
            self.assertEqual(self.client.post(url,headers=self.headers,json={'platforms':['youtube']}).status_code,502)
