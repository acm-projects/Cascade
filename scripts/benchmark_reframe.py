"""Local real-footage benchmark. No provider calls; keeps analysis/trajectories for comparison."""
import argparse,cProfile,json,platform,pstats,subprocess,sys,time,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import reframe
from backend.editor_backend import Composition,composition_geometry

def main():
 p=argparse.ArgumentParser();p.add_argument('--only',nargs='*');p.add_argument('--baseline',type=Path);p.add_argument('--fixtures',type=Path,default=Path('/tmp/cascade-tracking-fixtures'));p.add_argument('--output',type=Path,required=True);p.add_argument('--runs',type=int,default=2);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
 global reframe
 if args.baseline:
  import importlib.util,backend
  for name in ['subject_tracking','reframe']:
   spec=importlib.util.spec_from_file_location('backend.'+name,args.baseline/(name+'.py'));module=importlib.util.module_from_spec(spec);sys.modules['backend.'+name]=module;setattr(backend,name,module);spec.loader.exec_module(module)
  reframe=backend.reframe
 results={'platform':platform.platform(),'machine':platform.machine(),'runs':[]}
 for repeat in range(args.runs):
  for name,filename,context,focus,selection in [('person','pedestrian.mp4','Follow a walking person','auto',None),('dog','dog.mp4','Follow the dog','auto',None),('object','bag.mp4','Follow the bag','auto',{'t':0,'box':[.64,.36,.25,.36]}),('conversation','conversation.mp4','Conversation','speaker',None)]:
   if args.only and name not in args.only:continue
   source=args.fixtures/filename;probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height','-of','json',str(source)]));v=next(s for s in probe['streams'] if 'width'in s);info={'duration':float(probe['format']['duration']),'width':v['width'],'height':v['height'],'context':context,'has_audio':any(s.get('codec_type')=='audio' for s in probe['streams'])}
   prepare={};original_run=subprocess.run
   def timed_run(command,*a,**kw):
    stamp=time.perf_counter()
    try:return original_run(command,*a,**kw)
    finally:
     phase='video_preparation' if '-an' in command else 'audio_preparation'
     prepare[phase]=prepare.get(phase,0)+time.perf_counter()-stamp
   subprocess.run=timed_run
   profiler=cProfile.Profile();start=time.perf_counter();profiler.enable()
   import inspect
   kwargs={'selection':selection}
   if 'focus' in inspect.signature(reframe.analyze).parameters:kwargs['focus']=focus
   analysis=reframe.analyze(source,info,**kwargs);profiler.disable();analysis_seconds=time.perf_counter()-start;subprocess.run=original_run
   start=time.perf_counter();motion=reframe.plan(analysis,composition_geometry(info['width'],info['height'],Composition(mode='fill',ratio='9:16')),focus);planning=time.perf_counter()-start
   profiler.dump_stats(str(args.output/f'{name}-{repeat}.prof'));stats=pstats.Stats(profiler)
   calls=[{'file':key[0],'line':key[1],'function':key[2],'calls':value[1],'self':value[2],'cumulative':value[3]} for key,value in stats.stats.items()]
   row={'name':name,'repeat':repeat,'info':info,'focus':focus,'selection':selection,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'analysis_seconds':analysis_seconds,'planning_seconds':planning,'total_seconds':analysis_seconds+planning,'timings':analysis.get('timings'),'preparation':prepare, 'profile':sorted(calls,key=lambda x:x['cumulative'],reverse=True)[:100]}
   results['runs'].append(row);(args.output/f'{name}-{repeat}-analysis.json').write_text(json.dumps(analysis));(args.output/f'{name}-{repeat}-plan.json').write_text(json.dumps(motion));(args.output/'results.json').write_text(json.dumps(results,indent=2));print(name,repeat,round(row['total_seconds'],3),flush=True)
if __name__=='__main__':main()
