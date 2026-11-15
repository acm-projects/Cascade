import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('LinkedIn controls use authenticated, encoded backend routes and publish payload', async () => {
  const source = await readFile(new URL('./posting.js', import.meta.url), 'utf8');
  const client = new URL('./client.js', import.meta.url).href;
  const api = await import('data:text/javascript;base64,' + Buffer.from(source.replace('"./client"', JSON.stringify(client))).toString('base64'));
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (path, options) => {
    calls.push({ path, options });
    return new Response(JSON.stringify({ status: 'Ready' }), { headers: { 'content-type': 'application/json' } });
  };
  try {
    await api.getLinkedinConnection('fixture', 'project id');
    await api.connectLinkedin('fixture', 'project id');
    await api.getLinkedinStatus('fixture', 'project id', 'job/id', 2);
    const body = { title: 'Fixture', caption: 'Caption', hashtags: ['#Cascade'], edit: { start: 0, end: 5 }, submission_id: 'fixture' };
    await api.publishLinkedin('fixture', 'project id', 'job/id', 2, body);
    assert.deepEqual(calls.map(({ path, options }) => [path, options.method]), [
      ['/api/projects/project%20id/social/linkedin', 'GET'],
      ['/api/projects/project%20id/social/linkedin/connect', 'POST'],
      ['/api/projects/project%20id/editor/job%2Fid/2/publish/linkedin', 'GET'],
      ['/api/projects/project%20id/editor/job%2Fid/2/publish/linkedin', 'POST'],
    ]);
    for (const call of calls) assert.equal(call.options.headers.Authorization, 'Bearer fixture');
    assert.deepEqual(JSON.parse(calls[3].options.body), body);
  } finally { globalThis.fetch = original; }
});
