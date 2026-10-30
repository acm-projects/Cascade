import test from 'node:test';
import assert from 'node:assert/strict';
import {buildGraph} from './graph.js';

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
