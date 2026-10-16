const assert = require('node:assert/strict');
const {History, normalize, cueAt, defaultComposition, compositionGeometry} = require('../editor_state.js');
const initial = {start:0,end:12,composition:{...defaultComposition},texts:{},captions:{enabled:true,color:'#ffffff',bold:false,font:'Arial',size:32,position:'bottom',stroke:'#000000',thickness:2,background:'#000000',opacity:0}};
const a = new History(initial), b = new History(initial);
a.commit({...initial,start:2});
assert.equal(a.undoStack.length,1); assert.equal(b.state.start,0);
a.commit({...a.state,captions:{...a.state.captions,color:'#ffff00'},end:10}); // one AI transaction
assert.equal(a.undoStack.length,2);
a.undo(); assert.equal(a.state.end,12); assert.equal(a.state.captions.color,'#ffffff');
a.redo(); assert.equal(a.state.captions.color,'#ffff00');
a.undo(); a.commit({...a.state,end:8}); assert.equal(a.redoStack.length,0);
assert.deepEqual(normalize({...initial,start:-4,end:99},12),initial);
const normalized = normalize({...initial,start:11.99,end:2},12);
assert.ok(normalized.start>=0 && normalized.end<=12 && normalized.end>normalized.start);
const cues=[{start:1,end:3,text:'one'},{start:3,end:6,text:'two'}];
const trimmed={...initial,start:2,end:5};
assert.equal(cueAt(cues,1.5,trimmed),''); assert.equal(cueAt(cues,2,trimmed),'one');
assert.equal(cueAt(cues,3,trimmed),'two'); assert.equal(cueAt(cues,5,trimmed),'');
assert.equal(cueAt(cues,3,{...trimmed,captions:{enabled:false}}),'');
// Gesture previews mutate current state; committing from the captured baseline yields one entry.
const drag = new History(initial), baseline=JSON.parse(JSON.stringify(drag.state));
for(let i=1;i<=20;i++) drag.state.start=i/10;
const final=drag.state; drag.state=baseline; drag.commit(final);
assert.equal(drag.undoStack.length,1); drag.undo(); assert.equal(drag.state.start,0);
console.log('Editor state/history/timing checks passed');

assert.equal(cueAt(cues,2,{...trimmed,texts:{0:'Edited text'}}),'Edited text');
assert.throws(()=>normalize({...initial,texts:{bad:'invalid'}},12));

for(const ratio of ['original','9:16','1:1','4:5','16:9','4:3']) {
 const g=compositionGeometry(640,360,{...defaultComposition,ratio});
 assert.equal(g.width%2,0); assert.equal(g.height%2,0);
 if(ratio!=='original') {const [a,b]=ratio.split(':').map(Number);assert.equal(g.width/g.height,a/b);}
}
const fit=compositionGeometry(640,360,{...defaultComposition,ratio:'9:16'});
assert.ok(fit.scaledWidth<=fit.width && fit.scaledHeight<fit.height && fit.y>0);
const fill=compositionGeometry(640,360,{...defaultComposition,ratio:'9:16',mode:'fill',x:1});
assert.ok(fill.scaledWidth>fill.width && fill.x===fill.scaledWidth-fill.width);
assert.throws(()=>normalize({...initial,composition:{...defaultComposition,x:2}},12));
