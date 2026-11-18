import { clipKey, flattenClips } from "./clips";

// Remembers what the Editor and Export already loaded, for this browser tab, so moving between
// Studio Island, the Editor and Export shows the clip at once instead of a loading spinner.
//   index:  the Editor's picked-clip list for a project
//   drafts: one clip's { info, state, chat }, kept up to date as you edit (useClipDraft writes it back)
const indexes = new Map();
const drafts = new Map();

// Also kept in sessionStorage (this tab only), so a page refresh still opens the Editor straight away
const STORE = 'cascade.editorCache.v1';
function readStore() {
  try { return JSON.parse(sessionStorage.getItem(STORE)) || {}; } catch { return {}; }
}
function writeStore(kind, key, value) {
  try {
    const all = readStore();
    all[kind] = { ...all[kind], [key]: value };
    sessionStorage.setItem(STORE, JSON.stringify(all));
  } catch { /* storage full or blocked: memory still works */ }
}
const loading = new Map();
const prefetching = new Map();   // projectId -> the Studio prefetch still on its way

export const draftKey = (projectId, jobId, index) => `${projectId}:${jobId}:${index}`;

export function cachedIndex(projectId) {
  return indexes.get(projectId) ?? readStore().index?.[projectId] ?? null;
}

// The picked-clip list Studio started fetching, if it hasn't arrived yet (the Editor waits on it instead of asking again)
export function pendingIndex(projectId) {
  return prefetching.get(projectId) ?? null;
}

export function rememberIndex(projectId, index) {
  indexes.set(projectId, index);
  writeStore('index', projectId, index);
}

export function cachedDraft(key) {
  return drafts.get(key) ?? readStore().draft?.[key] ?? null;
}

let storeTimer = null;
export function rememberDraft(key, value) {
  const next = { ...cachedDraft(key), ...value };
  drafts.set(key, next);
  clearTimeout(storeTimer);   // edits come fast (dragging); write the tab copy once they pause
  storeTimer = setTimeout(() => writeStore('draft', key, next), 400);
}

// Load one clip's draft (once at a time) and remember it.
export function loadDraft(api, projectId, jobId, index) {
  const key = draftKey(projectId, jobId, index);
  if (!loading.has(key)) {
    const request = api.getDraft(projectId, jobId, index).then((result) => {
      const { draft, ...info } = result;
      rememberDraft(key, { info, state: draft.state, chat: draft.chat ?? [] });
      return result;
    });
    const done = () => loading.delete(key);
    request.then(done, done);
    loading.set(key, request);
  }
  return loading.get(key);
}

// Studio Island -> Editor: fetch the picked clips and the first one's draft while the waterfall is up.
export function prefetchEditor(api, projectId) {
  // waitForJoin: in demo mode, wait for the picked clips' joined clip, so the Editor opens straight on it
  const request = api.getEditorIndex(projectId, { selectedOnly: true, waitForJoin: true })
    .then((index) => { rememberIndex(projectId, index); return index; });
  prefetching.set(projectId, request);
  const done = () => { if (prefetching.get(projectId) === request) prefetching.delete(projectId); };
  request.then(done, done);
  return request.then((index) => loadFirstDraft(api, projectId, index));
}

// Studio picks changed: get the Editor ready a moment later (repeated picks restart the wait)
let warmTimer = null;
export function warmEditor(api, projectId) {
  clearTimeout(warmTimer);
  warmTimer = setTimeout(() => { prefetchEditor(api, projectId).catch(() => {}); }, 600);
}

async function loadFirstDraft(api, projectId, index) {
  const list = flattenClips(index);
  const first = (index.selection && list.find((clip) => clipKey(clip) === clipKey(index.selection))) || list[0];
  if (first) await loadDraft(api, projectId, first.job_id, first.clip_index).catch(() => {});
  return index;
}
