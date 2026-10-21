"""Summarize repeated profiles and compare actual crop trajectories."""
import argparse,json,statistics
from pathlib import Path

def summarize(before,after):
 def stage(row,key):
  if row.get('timings'):
   t=row['timings']
   if key=='tracking':return t.get('subject_tracking_including_detection',{}).get('seconds',0)-t.get('object_detection',{}).get('seconds',0)+t.get('manual_tracking',{}).get('seconds',0)+t.get('face_tracking',{}).get('seconds',0)
   return t.get(key,{}).get('seconds',0)
  p=row['profile']
  if key in ('video_preparation','audio_preparation'):return row['preparation'].get(key,0)
  if key=='object_detection':return sum(v['cumulative'] for v in p if v['function']=='detect' and v['file'].endswith('subject_tracking.py'))
  if key=='face_detection':return sum(v['cumulative'] for v in p if 'FaceDetectorYN' in v['function'] and 'detect' in v['function'])
  if key=='active_speaker':return sum(v['cumulative'] for v in p if v['function']=='infer_batch')
  if key=='tracking':return sum(v['cumulative'] for v in p if v['function']=='update' and v['file'].endswith('subject_tracking.py'))-stage(row,'object_detection')
  return 0
 old=json.loads((before/'results.json').read_text());new=json.loads((after/'results.json').read_text());out={'method':'One cold cycle plus two warm cycles; medians of the warm cycles; sequential runs with cProfile enabled on both versions.','platform':old['platform'],'hardware':'Apple M4 Pro, 14 CPU cores, 24 GiB unified memory; CPU FP32','fixtures':[]}
 for name in ['person','dog','object','conversation']:
  b=[r for r in old['runs'] if r['name']==name];a=[r for r in new['runs'] if r['name']==name]
  assert b[0]['sha256']==a[0]['sha256']
  row={'name':name,'duration':b[0]['info']['duration'],'sha256':b[0]['sha256'],'before_runs':[r['total_seconds'] for r in b],'after_runs':[r['total_seconds'] for r in a]}
  row['before']=statistics.median(row['before_runs'][1:]);row['after']=statistics.median(row['after_runs'][1:]);row['speedup']=row['before']/row['after']
  row['stages']={key:{'before':statistics.median([stage(r,key) for r in b[1:]]),'after':statistics.median([stage(r,key) for r in a[1:]])} for key in ['video_preparation','audio_preparation','object_detection','face_detection','active_speaker','tracking']}
  row['stages']['planning']={'before':statistics.median([r['planning_seconds'] for r in b[1:]]),'after':statistics.median([r['planning_seconds'] for r in a[1:]])}
  bp=json.loads((before/f'{name}-1-plan.json').read_text())['points'];ap=json.loads((after/f'{name}-1-plan.json').read_text())['points']
  assert len(bp)==len(ap)
  row['trajectory']={'max_x_difference':max(abs(x['x']-y['x']) for x,y in zip(ap,bp)),'max_step_before':max(abs(x['x']-y['x']) for x,y in zip(bp,bp[1:])),'max_step_after':max(abs(x['x']-y['x']) for x,y in zip(ap,ap[1:]))}
  out['fixtures'].append(row)
 return out
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args();result=summarize(args.before,args.after);args.output.write_text(json.dumps(result,indent=2))
 for r in result['fixtures']:print(r['name'],f"{r['before']:.3f}s → {r['after']:.3f}s ({r['speedup']:.2f}×)",r['stages'])
