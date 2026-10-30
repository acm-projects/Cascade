import test from 'node:test';
import assert from 'node:assert/strict';
import { isSupportedMedia, isAudioClip, MEDIA_ACCEPT } from './media.js';
import { downloadName } from '../features/export/downloads.js';

test('supported media uses extensions even when browsers omit MIME metadata', () => {
  for(const ext of ['mp4','MOV','webm','mkv','mp3','wav','m4a','flac']) {
    assert.ok(isSupportedMedia({name:'recording.'+ext,type:''}));
    assert.ok(MEDIA_ACCEPT.includes('.'+ext.toLowerCase()));
  }
  assert.equal(isSupportedMedia({name:'malware.exe',type:'audio/mpeg'}),false);
  assert.equal(isSupportedMedia({name:'no-extension'}),false);
});

test('audio clips use MP3 names while existing video downloads retain MP4', () => {
  assert.equal(isAudioClip({clip_url:'/clips/job/clip_1.mp3'}),true);
  assert.equal(isAudioClip({media_kind:'audio'}),true);
  assert.equal(isAudioClip({clip_url:'/clips/job/clip_1.mp4'}),false);
  assert.equal(downloadName('Podcast',2,true),'podcast-selected-2.mp3');
  assert.equal(downloadName('Video',2),'video-selected-2.mp4');
});
