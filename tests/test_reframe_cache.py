"""Cache identity/invalidation and duplicate-job behavior; inference is stubbed here only."""
import json,os,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from backend import reframe, editor
from tests import test_editor as fixture

class AnalysisKeyTests(unittest.TestCase):
 def test_focus_capabilities_and_selection_invalidate(self):
  info={'width':640,'height':360,'duration':5,'context':'A person speaks','source_revision':[1]}
  key=reframe.analysis_key(info,'auto')
  self.assertEqual(key,reframe.analysis_key(info,'speaker'))
  self.assertNotEqual(key,reframe.analysis_key(info,'left'))
  self.assertNotEqual(key,reframe.analysis_key({**info,'context':'A dog runs'},'auto'))
  self.assertNotEqual(key,reframe.analysis_key({**info,'source_revision':[2]},'auto'))
  self.assertNotEqual(key,reframe.analysis_key(info,'auto',{'t':1,'box':[.1,.1,.2,.2]}))
 def test_model_revision_invalidates_relevant_profiles(self):
  import tempfile
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'CASCADE_REFRAME_MODELS':folder}):
   info={'width':640,'height':360,'duration':5,'context':'A dog runs'};key=reframe.analysis_key(info)
   Path(folder,'yolox.onnx').write_bytes(b'new weights')
   self.assertNotEqual(key,reframe.analysis_key(info))
   manual={'t':0,'box':[.1,.1,.2,.2]};key=reframe.analysis_key(info,selection=manual)
   Path(folder,'yolox.onnx').write_bytes(b'another model')
   self.assertEqual(key,reframe.analysis_key(info,selection=manual))
   self.assertEqual(key,reframe.analysis_key({**info,'context':'Changed title'},selection=manual))
   with patch.dict(os.environ,{'CASCADE_REFRAME_DEVICE':'mps'}):self.assertEqual(key,reframe.analysis_key(info,selection=manual))

class JobCacheTests(unittest.TestCase):
 setUpClass=classmethod(fixture.EditorTests.setUpClass.__func__)
 tearDownClass=classmethod(fixture.EditorTests.tearDownClass.__func__)
 setUp=fixture.EditorTests.setUp
 tearDown=fixture.EditorTests.tearDown
 job=fixture.EditorTests.job
 get=fixture.EditorTests.get
 def test_duplicate_ready_geometry_and_source_revision(self):
  entered=threading.Event();release=threading.Event()
  def inference(source,info,progress,selection=None,focus='auto'):
   entered.set();release.wait(5)
   return {'version':reframe.VERSION,'duration':info['duration'],'selection':selection,'frames':[{'t':0,'faces':[],'subjects':[],'audio':False}],'context':info['context']}
  body={'composition':{'ratio':'9:16','mode':'fill'},'focus':'auto'}
  with patch.object(reframe,'analyze',side_effect=inference) as infer:
   first=self.client.post(self.url+'/reframe',headers=self.headers,json=body).json();self.assertTrue(entered.wait(2))
   second=self.client.post(self.url+'/reframe',headers=self.headers,json=body).json();self.assertEqual(first['analysis_id'],second['analysis_id'])
   release.set()
   for _ in range(100):
    status=self.client.get(self.url+'/reframe/'+first['analysis_id'],headers=self.headers).json()
    if status['status']=='ready':break
    time.sleep(.01)
   self.assertEqual(status['status'],'ready');self.assertEqual(infer.call_count,1)
   changed={**body,'composition':{'ratio':'1:1','mode':'fill'},'focus':'speaker'}
   cached=self.client.post(self.url+'/reframe',headers=self.headers,json=changed).json();self.assertTrue(cached['cache_hit']);self.assertEqual(cached['analysis_id'],first['analysis_id'])
   import app1
   from backend.core import jobs as core_jobs
   results=core_jobs.JOBS_DIR/self.jid/'results.json';data=json.loads(results.read_text());data['unrelated_note']='metadata edit';results.write_text(json.dumps(data))
   unchanged=self.client.post(self.url+'/reframe',headers=self.headers,json=body).json();self.assertEqual(unchanged['analysis_id'],first['analysis_id']);self.assertTrue(unchanged['cache_hit'])
   source=core_jobs.JOBS_DIR/self.jid/'clip_1.mp4';os.utime(source,ns=(source.stat().st_atime_ns,source.stat().st_mtime_ns+1000000))
   invalid=self.client.get(self.url+'/reframe/'+first['analysis_id']+'/subjects',headers=self.headers)
   self.assertEqual(invalid.status_code,409)
   renewed=self.client.post(self.url+'/reframe',headers=self.headers,json=body).json();self.assertNotEqual(renewed['analysis_id'],first['analysis_id'])
   # Wait for the stubbed worker to finish before its patch/fixture is released.
   for _ in range(100):
    if self.client.get(self.url+'/reframe/'+renewed['analysis_id'],headers=self.headers).json()['status']=='ready':break
    time.sleep(.01)
