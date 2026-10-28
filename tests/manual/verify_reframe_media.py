"""Opt-in local-model verification. Controlled turn-taking uses real speaking-face
video opposite a frozen listener, then swaps their roles. This is constructed test
footage, not a natural-conversation benchmark. No output camera path is supplied
to the analyzer. Public source: TaoRuijie/TalkNet-ASD demo/001.avi.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from pathlib import Path
import subprocess
import argparse,json
parser=argparse.ArgumentParser(description='Build controlled human movement/turn-taking fixtures and run real local inference; no paid calls.')
parser.add_argument('--source',type=Path,required=True,help='Official TalkNet demo 001.avi, kept outside the repo')
parser.add_argument('--output',type=Path,default=Path('/tmp/cascade-tracking-fixtures'))
args=parser.parse_args()
root=args.output;root.mkdir(parents=True,exist_ok=True)
def ff(args):subprocess.run(['ffmpeg','-v','error','-y',*args],check=True)
# Both human tracks are real video; one freezes while the other speaks. This is a
# controlled turn-taking fixture, not a claim of natural conversation evaluation.
ff(['-ss','0','-t','6','-i',str(args.source),'-vf','crop=310:360:330:0,scale=480:540','-c:v','libx264','-c:a','aac',str(root/'talk.mp4')])
ff(['-i',str(root/'talk.mp4'),'-vf',"select=eq(n\\,25)",'-frames:v','1',str(root/'still.png')])
ff(['-i',str(root/'talk.mp4'),'-loop','1','-i',str(root/'still.png'),'-filter_complex','[0:v]setsar=1[a];[1:v]setsar=1,hflip[b];[a][b]hstack[v]','-map','[v]','-map','0:a','-t','6','-c:v','libx264','-c:a','aac',str(root/'turn1.mp4')])
ff(['-i',str(root/'talk.mp4'),'-loop','1','-i',str(root/'still.png'),'-filter_complex','[1:v]setsar=1[a];[0:v]setsar=1,hflip[b];[a][b]hstack[v]','-map','[v]','-map','0:a','-t','6','-c:v','libx264','-c:a','aac',str(root/'turn2.mp4')])
(root/'concat.txt').write_text("file 'turn1.mp4'\nfile 'turn2.mp4'\n")
ff(['-f','concat','-safe','0','-i',str(root/'concat.txt'),'-c:v','libx264','-pix_fmt','yuv420p','-g','25','-c:a','aac','-movflags','+faststart',str(root/'conversation.mp4')])
# A real speaking face moves across a canvas; camera path is not provided to analysis.
ff(['-i',str(root/'talk.mp4'),'-f','lavfi','-i','color=c=#18251e:s=960x540:r=25:d=6','-filter_complex',"[1:v][0:v]overlay=x='(W-w)*t/6':y=0:shortest=1[v]",'-map','[v]','-map','0:a','-t','6','-c:v','libx264','-c:a','aac',str(root/'moving.mp4')])
print('Controlled test videos ready in',root)

from backend.reframe import analyze,plan
from backend.editor import composition_geometry,Composition
for name,duration in [('conversation',12),('moving',6)]:
 analysis=analyze(root/(name+'.mp4'),{'width':960,'height':540,'duration':duration})
 motion=plan(analysis,composition_geometry(960,540,Composition(mode='fill',ratio='9:16')))
 (root/(name+'-analysis.json')).write_text(json.dumps(analysis));(root/(name+'-plan.json')).write_text(json.dumps(motion))
 points=motion['points']
 assert max(p['x']for p in points)-min(p['x']for p in points)>.5
 assert max(abs(a['x']-b['x'])for a,b in zip(points,points[1:]))<.15
 if name=='conversation':
  assert min(points,key=lambda p:abs(p['t']-3))['x']<.3
  assert min(points,key=lambda p:abs(p['t']-10))['x']>.7
 print(name+': real inference passed; bounded, smooth crop movement verified.')
