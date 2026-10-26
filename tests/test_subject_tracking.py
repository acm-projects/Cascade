"""Subject policy tests; real model/footage checks live in manual verification."""
import unittest
from backend import reframe
from backend.editor_backend import Composition,composition_geometry,SubjectSelection
from backend.subject_tracking import context_classes
from pydantic import ValidationError

class SubjectPolicyTests(unittest.TestCase):
 def geometry(self):return composition_geometry(640,360,Composition(mode='fill',ratio='9:16'))
 def analysis(self):
  rows=[]
  for i in range(125):
   rows.append({'t':i/25,'faces':[],'audio':False,'subjects':[{'id':1,'label':'dog','confidence':.9,'box':[.1+i*.003,.3,.15,.3]},{'id':2,'label':'car','confidence':.99,'box':[.8-i*.004,.2,.2,.4]}]})
  return {'duration':5,'context':'Follow the puppy','frames':rows}
 def test_prompt_subject_not_unrelated_motion(self):
  a=self.analysis();p=reframe.plan(a,self.geometry(),'auto')['points']
  self.assertLess(p[0]['x'],.2);self.assertGreater(p[-1]['x'],p[0]['x']+.25)
  self.assertLess(max(abs(a['x']-b['x']) for a,b in zip(p,p[1:])),.15)
  self.assertIn('dog',context_classes('a puppy runs'))
 def test_lost_selected_subject_holds(self):
  a=self.analysis();a['selection']={'t':0,'box':[.1,.3,.15,.3]}
  for i,row in enumerate(a['frames']):row['region']={'box':[.1+i*.003,.3,.15,.3]} if i<50 else None
  p=reframe.plan(a,self.geometry(),'auto')['points'];tail=[r['x'] for r in p if r['t']>2.2]
  self.assertEqual(len(set(tail)),1)
 def test_no_subject_replacement_after_loss(self):
  a=self.analysis()
  for row in a['frames'][50:]:row['subjects']=[{'id':3,'label':'dog','confidence':.99,'box':[.8,.3,.1,.3]}]
  p=reframe.plan(a,self.geometry(),'auto')['points'];self.assertLess(p[-1]['x'],.5)
 def test_invalid_region_rejected(self):
  for box in ([.9,.2,.4,.3],[0,0,0,.3],[0,0,float('nan'),.3]):
   with self.assertRaises(ValidationError):SubjectSelection(t=0,box=box)
