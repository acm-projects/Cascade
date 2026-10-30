import test from 'node:test';
import assert from 'node:assert/strict';
import { insertBroll, updateBroll, validateBroll, dragBroll } from './brollTiming.js';
const asset = { id:'px-12-25',duration:10 };
const seg = (id,start,duration,offset=0) => ({id,asset,start,duration,offset,mode:'fill'});

test('insert at source playhead with three second default, bounded by trim, stock and next segment',()=>{
 const state={start:2,end:12,broll:[seg('later',7,2)]};
 assert.deepEqual(insertBroll(state,asset,3,'new').broll.at(-1),seg('new',3,3));
 assert.equal(insertBroll(state,asset,6,'new').broll.at(-1).duration,1);
 assert.equal(insertBroll(state,{...asset,duration:.2},3,'new').broll.at(-1).duration,.2);
 assert.equal(insertBroll(state,asset,0,'new').broll.at(-1).start,2);
 assert.throws(()=>insertBroll(state,asset,8,'new'),/overlap/);
 assert.throws(()=>insertBroll(state,asset,12,'new'),/earlier/);
 assert.equal(state.broll.length,1);
});

test('updates reject overlaps, unavailable stock ranges, non-finite timings, and duplicate IDs',()=>{
 const state={broll:[seg('a',1,2),seg('b',5,2)]};
 assert.throws(()=>updateBroll(state,'a',{duration:5},10),/overlap/);
 assert.throws(()=>updateBroll(state,'a',{offset:9},10),/stock/);
 assert.throws(()=>updateBroll(state,'a',{start:NaN},10),/stock/);
 assert.throws(()=>validateBroll([seg('a',0,1),seg('a',2,1)],10),/unique/);
 assert.throws(()=>validateBroll(Array.from({length:31},(_,i)=>seg(String(i),i,1)),40),/30/);
 assert.equal(updateBroll(state,'a',{offset:2,mode:'fit'},10).broll[0].offset,2);
});

test('drag moves stop at neighboring segments and clip boundaries',()=>{
 const segments=[seg('a',0,2),seg('b',4,2),seg('c',8,2)];
 assert.equal(dragBroll(segments[1],'move',100,segments,12).start,6);
 assert.equal(dragBroll(segments[1],'move',-100,segments,12).start,2);
 for(const delta of [-100,-2,-.1,0,.1,2,100]){
  const moved=dragBroll(segments[1],'move',delta,segments,12);
  validateBroll(segments.map(s=>s.id==='b'?moved:s),12);
 }
});

test('resize maintains stock offsets and minimum duration without overlap',()=>{
 const segment=seg('b',4,2,2);const segments=[seg('a',0,2),segment,seg('c',8,2)];
 const start=dragBroll(segment,'start',-100,segments,12);
 assert.deepEqual([start.start,start.duration,start.offset],[2,4,0]);
 const end=dragBroll(segment,'end',100,segments,12);
 assert.equal(end.duration,4);
 for(const kind of ['start','end'])for(const delta of [-100,-2,-.1,0,.1,2,100]){
  const resized=dragBroll(segment,kind,delta,segments,12);
  validateBroll(segments.map(s=>s.id==='b'?resized:s),12);
 }
});
