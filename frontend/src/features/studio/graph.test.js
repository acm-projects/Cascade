import test from 'node:test';
import assert from 'node:assert/strict';
import {buildGraph,displayClips,sessionGroups} from './graph.js';

test('clips 4 5 6 branch directly from clip 3 and can branch again',()=>{
 const groups=[{job_id:'a',clips:[{},{},{}],state:'done'},
 {job_id:'b',clips:[{},{},{}],state:'done',parent_clips:[{job_id:'a',clip_index:2}]},
 {job_id:'c',clips:[{},{}],state:'done',parent_clips:[{job_id:'b',clip_index:1}]}];
 const session={source_job:'a',job_ids:['a','b','c']};
 const {nodes,edges}=buildGraph(session,groups,{});
 assert.equal(nodes.filter(n=>n.type==='clip').length,8);
 assert.equal(nodes.filter(n=>n.type==='generation').length,1);
 for(let i=0;i<3;i++)assert.ok(edges.some(e=>e.source==='clip:a:2'&&e.target==='clip:b:'+i));
 for(let i=0;i<2;i++)assert.ok(edges.some(e=>e.source==='clip:b:1'&&e.target==='clip:c:'+i));
 assert.deepEqual(nodes.filter(n=>n.type==='clip').map(n=>n.data.label),['1','2','3','4','5','6','7','8']);
 assert.equal(new Set(nodes.map(n=>n.id)).size,nodes.length);
});
test('pending and failed child requests preserve all original clips',()=>{
 for(const state of ['queued','error','done']){
 const {nodes,edges}=buildGraph({source_job:'a',job_ids:['a','b']},[
 {job_id:'a',clips:[{}],state:'done'},
 {job_id:'b',clips:[],state,parent_clips:[{job_id:'a',clip_index:0}]}],{});
 assert.ok(nodes.some(n=>n.id==='clip:a:0'));
 assert.ok(edges.some(e=>e.source==='clip:a:0'&&e.target==='generation:b'));
 }
});
test('legacy replacement data preserves parents and multiple references connect to each child',()=>{
 const {nodes,edges}=buildGraph({source_job:'a',job_ids:['a','b'],clip_revisions:{'a:0':'b'}},[
 {job_id:'a',clips:[{},{}],state:'done'},
 {job_id:'b',clips:[{}],state:'done',studio_revision_of:{job_id:'a',clip_index:0},parent_clips:[{job_id:'a',clip_index:0},{job_id:'a',clip_index:1}]}],{});
 assert.equal(nodes.filter(n=>n.type==='clip').length,3);
 assert.deepEqual(edges.filter(e=>e.target==='clip:b:0').map(e=>e.source),['clip:a:0','clip:a:1']);
});
test('a session with no prompts yet shows only the source box',()=>{
 const {nodes,edges}=buildGraph({source_job:null,job_ids:[]},[],{});
 assert.deepEqual(nodes.map(n=>n.id),['source:upload']);
 assert.equal(edges.length,0);
});
test('one prompt with 4 clips: a prompt card, 4 clips and 5 vines',()=>{
 const {nodes,edges}=buildGraph({source_job:'a',job_ids:['a']},[{job_id:'a',clips:[{},{},{},{}],state:'done'}],{});
 assert.equal(nodes.filter(n=>n.type==='generation').length,1);
 assert.equal(nodes.filter(n=>n.type==='clip').length,4);
 assert.equal(edges.length,5);
 assert.ok(edges.some(e=>e.source==='source:a'&&e.target==='generation:a'));
 for(let i=0;i<4;i++)assert.ok(edges.some(e=>e.source==='generation:a'&&e.target==='clip:a:'+i));
});
test('the vine into a running prompt is animated, a finished one is not',()=>{
 for(const [state,animated] of [['queued',true],['processing',true],['done',false],['error',false]]){
 const {edges}=buildGraph({source_job:'a',job_ids:['a']},[{job_id:'a',clips:[],state}],{});
 assert.equal(edges.find(e=>e.target==='generation:a').animated,animated,state);
 }
});
test('two first prompts are stacked without overlapping',()=>{
 const {nodes}=buildGraph({source_job:'a',job_ids:['a','b']},[
 {job_id:'a',clips:[{},{},{}],state:'done'},{job_id:'b',clips:[{},{}],state:'done'}],{});
 const y=id=>nodes.find(n=>n.id===id).position.y;
 assert.ok(y('clip:b:0')>y('clip:a:2'),'second prompt starts below the first one\'s last clip');
 assert.equal(nodes.find(n=>n.id==='clip:a:0').position.x,nodes.find(n=>n.id==='clip:b:0').position.x);
});
test('a box the user moved stays where they put it',()=>{
 const {nodes}=buildGraph({source_job:'a',job_ids:['a'],positions:{'clip:a:0':{x:5,y:7}}},
 [{job_id:'a',clips:[{}],state:'done'}],{});
 assert.deepEqual(nodes.find(n=>n.id==='clip:a:0').position,{x:5,y:7});
});
test('references to a clip that no longer exists do not crash or leave loose vines',()=>{
 const {nodes,edges}=buildGraph({source_job:'a',job_ids:['b']},[
 {job_id:'b',clips:[{}],state:'done',parent_clips:[{job_id:'gone',clip_index:3}]}],{});
 assert.ok(nodes.some(n=>n.id==='clip:b:0'));
 const ids=new Set(nodes.map(n=>n.id));
 for(const e of edges)assert.ok(ids.has(e.source)&&ids.has(e.target));
});
test('sessionGroups keeps the session order and skips unknown jobs; displayClips numbers every clip',()=>{
 const groups=[{job_id:'b',clips:[{}]},{job_id:'a',clips:[{},{}]}];
 assert.deepEqual(sessionGroups({job_ids:['a','missing','b']},groups).map(g=>g.job_id),['a','b']);
 assert.deepEqual(displayClips({},groups,groups[1]).map(c=>[c.label,c.ref.clip_index]),[['1',0],['2',1]]);
});
test('every clip card gets the page actions and its prompt number',()=>{
 const onToggle=()=>{};
 const {nodes}=buildGraph({source_job:'a',job_ids:['a','b']},[
 {job_id:'a',clips:[{}],state:'done'},{job_id:'b',clips:[{}],state:'done'}],{onToggle});
 const clip=nodes.find(n=>n.id==='clip:b:0');
 assert.equal(clip.data.onToggle,onToggle);
 assert.equal(clip.data.number,2);
 assert.deepEqual(clip.data.ref,{job_id:'b',clip_index:0});
});
