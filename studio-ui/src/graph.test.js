import test from 'node:test';
import assert from 'node:assert/strict';
import {buildGraph} from './graph.js';
test('combining two references produces two actual incoming edges and stable positions',()=>{
  const first={job_id:'a',clips:[{},{},{},{}],state:'done'};
  const next={job_id:'b',clips:[{},{}],state:'done',parent_clips:[{job_id:'a',clip_index:0},{job_id:'a',clip_index:3}]};
  const session={source_job:'a',job_ids:['a','b'],positions:{'clip:a:0':{x:99,y:88}}};
  const {nodes,edges}=buildGraph(session,[first,next],{});
  assert.equal(nodes.filter(n=>n.type==='clip').length,6);
  assert.deepEqual(nodes.find(n=>n.id==='clip:a:0').position,{x:99,y:88});
  assert.deepEqual(edges.filter(e=>e.target==='generation:b').map(e=>e.source),['clip:a:0','clip:a:3']);
  assert.equal(new Set(nodes.map(n=>n.id)).size,nodes.length);
  assert.deepEqual(buildGraph(session,[first,next],{}),{nodes,edges});
});
test('session graph excludes generations belonging to other sessions',()=>{
  const graph=buildGraph({source_job:'a',job_ids:['b']},[{job_id:'b',clips:[],state:'queued'},{job_id:'other',clips:[{}]}],{});
  assert.equal(graph.nodes.filter(n=>n.type==='generation').length,1);
  assert.equal(graph.nodes.filter(n=>n.type==='clip').length,0);
});

test('a similar-clip update replaces its selected slot without adding a generation node',()=>{
  const first={job_id:'a',clips:[{title:'One'},{title:'Bedroom wrestling'},{title:'Three'}],state:'done'};
  const revision={job_id:'r',clips:[{title:'Similar one'},{title:'Similar two'}],state:'done',
    studio_revision_of:{job_id:'a',clip_index:1},parent_clips:[{job_id:'a',clip_index:1}]};
  const session={source_job:'a',job_ids:['a','r'],clip_revisions:{'a:1':'r'}};
  const {nodes}=buildGraph(session,[first,revision],{});
  assert.equal(nodes.filter(n=>n.type==='generation').length,1);
  assert.equal(nodes.filter(n=>n.type==='clip').length,4);
  assert.equal(nodes.some(n=>n.id==='clip:a:1'),false);
  assert.equal(nodes.find(n=>n.id==='clip:r:0').data.label,'2.1');
  assert.equal(nodes.find(n=>n.id==='clip:r:1').data.number,1);
  assert.equal(nodes.find(n=>n.id==='generation:a').data.group.displayed_clip_count,4);
});

test('pending, failed and empty updates preserve the original clip',()=>{
  const first={job_id:'a',clips:[{title:'Keep me'}],state:'done'};
  const session={source_job:'a',job_ids:['a','r'],clip_revisions:{'a:0':'r'}};
  for(const state of ['processing','error','done']){
    const revision={job_id:'r',clips:[],state,studio_revision_of:{job_id:'a',clip_index:0}};
    const {nodes}=buildGraph(session,[first,revision],{});
    assert.equal(nodes.filter(n=>n.type==='generation').length,1);
    assert.equal(nodes.find(n=>n.id==='clip:a:0').data.clip.title,'Keep me');
    assert.equal(nodes.find(n=>n.id==='clip:a:0').data.revision.state,state);
  }
});

test('a replacement clip can be refined again in the same original generation',()=>{
  const first={job_id:'a',clips:[{}],state:'done'};
  const revision={job_id:'r',clips:[{}],state:'done',studio_revision_of:{job_id:'a',clip_index:0}};
  const next={job_id:'s',clips:[{title:'Latest'}],state:'done',studio_revision_of:{job_id:'r',clip_index:0}};
  const {nodes}=buildGraph({source_job:'a',job_ids:['a','r','s'],clip_revisions:{'a:0':'r','r:0':'s'}},[first,revision,next],{});
  assert.equal(nodes.filter(n=>n.type==='generation').length,1);
  assert.equal(nodes.find(n=>n.type==='clip').id,'clip:s:0');
});

test('multiple checked clips share new alternatives without duplicating them or adding a generation',()=>{
  const first={job_id:'a',clips:[{},{}],state:'done'};
  const revision={job_id:'r',clips:[{},{},{},{}],state:'done',studio_revision_of:{job_id:'a',clip_index:0}};
  const session={source_job:'a',job_ids:['a','r'],clip_revisions:{
    'a:0':{job_id:'r',target_index:0,target_count:2},'a:1':{job_id:'r',target_index:1,target_count:2}}};
  const {nodes}=buildGraph(session,[first,revision],{});
  assert.equal(nodes.filter(n=>n.type==='generation').length,1);
  assert.equal(nodes.filter(n=>n.type==='clip').length,4);
  assert.equal(new Set(nodes.map(n=>n.id)).size,nodes.length);
  assert.deepEqual(nodes.filter(n=>n.type==='clip').map(n=>n.id),['clip:r:0','clip:r:2','clip:r:1','clip:r:3']);
});
