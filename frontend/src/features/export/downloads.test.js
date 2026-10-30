import test from 'node:test';
import assert from 'node:assert/strict';
import { downloadName, exportEdit, saveBlob } from './downloads.js';

test('export overrides preserve saved edit and filename has safe characters', () => {
  const state = {start: 2, end: 9, captions: {enabled:true,color:'#fff'}, broll:[{id:'stock'}]};
  const edit = exportEdit(state, {resolution:'720p',includeCaptions:false});
  assert.equal(state.captions.enabled,true);
  assert.equal(edit.captions.enabled,false);
  assert.equal(edit.start,2); assert.deepEqual(edit.broll,state.broll);
  assert.equal(edit.resolution,'720p');
  assert.equal(downloadName('../My Project!?',3),'my-project-selected-3.mp4');
});

test('Blob download clicks an attached link and revokes its URL after 30 seconds', t => {
  const calls=[];
  const link={click:()=>calls.push('click'),remove:()=>calls.push('remove')};
  t.mock.method(URL,'createObjectURL',()=> 'blob:download');
  t.mock.method(URL,'revokeObjectURL',url=>calls.push(url));
  t.mock.method(globalThis,'setTimeout',(callback,ms)=>{assert.equal(ms,30000);callback();});
  const previous=globalThis.document;
  globalThis.document={body:{appendChild:()=>calls.push('attach')},createElement:()=>link};
  t.after(()=>{ if(previous===undefined)delete globalThis.document;else globalThis.document=previous; });
  saveBlob(new Blob(['video']),'safe.mp4');
  assert.deepEqual(calls,['attach','click','remove','blob:download']);
  assert.equal(link.download,'safe.mp4');
});
