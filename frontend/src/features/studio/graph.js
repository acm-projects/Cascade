// Turn the studio document + generation groups into React Flow boxes and vines.
// Ported from Kashmine's studio-ui/src/graph.js so both studios lay out the same way; spacing is
// tuned for our box sizes and every line is a leafy "vine" edge.
//
//   session - one studio session: { source_job, job_ids, positions, clip_revisions }
//   groups  - from api.listGenerations(): [{ job_id, state, message, prompt, clips: [...], parent_clips?, ... }]
//   actions - functions/values every box gets in its data (toggle a clip, preview, retry, ...)
//
// Box ids match what the backend accepts for saved positions:
//   "source:<job>" (or "source:upload" before a video), "generation:<job>", "clip:<job>:<index>"

const GENERATION_X = 480;   // first prompt column
const CLIP_X = 900;         // first clip column
const DEPTH_GAP = 1050;     // extra room for each "more like this" step to the right
const CLIP_HEIGHT = 300;    // clip box height + gap

export const clipKey = (ref) => `${ref.job_id}:${ref.clip_index}`;
export const sameRef = (a, b) => clipKey(a) === clipKey(b);

// "Find more like this clip" replaces that clip's slot with the new alternatives, so the canvas
// stays one generation wide. Pending, failed or empty updates keep showing the original clip.
export function displayClips(session, groups, group) {
  const byId = new Map(groups.map((g) => [g.job_id, g]));
  const expand = (clip, ref, label, seen = new Set()) => {
    const key = clipKey(ref);
    const replacement = session.clip_revisions?.[key];
    const revision = byId.get(typeof replacement === "string" ? replacement : replacement?.job_id);
    if (revision && !seen.has(key) && revision.state === "done" && revision.clips.length) {
      const visited = new Set(seen);
      visited.add(key);
      const choices = revision.clips
        .map((next, index) => ({ next, index }))
        .filter(({ index }) => typeof replacement === "string" || index % replacement.target_count === replacement.target_index);
      if (choices.length) {
        return choices.flatMap(({ next, index }, slot) =>
          expand(next, { job_id: revision.job_id, clip_index: index },
            choices.length === 1 ? label : `${label}.${slot + 1}`, visited));
      }
    }
    return [{ clip, ref, label, revision: revision || null }];
  };
  return group.clips.flatMap((clip, index) => expand(clip, { job_id: group.job_id, clip_index: index }, String(index + 1)));
}

// The generations shown as their own prompt box (revisions live inside their original's slots)
export function sessionGroups(session, groups) {
  const byId = new Map(groups.map((group) => [group.job_id, group]));
  const revisions = new Set(Object.values(session.clip_revisions || {})
    .map((value) => (typeof value === "string" ? value : value.job_id)));
  return session.job_ids
    .map((id) => byId.get(id))
    .filter((group) => group && !group.studio_revision_of && !revisions.has(group.job_id));
}

export function buildGraph(session, groups, actions) {
  const nodes = [];
  const edges = [];
  const placed = new Map();   // clip key -> position, so follow-ups sit next to their parents
  const depths = new Map();   // job id -> how many "more like this" steps from the video
  const bottoms = new Map();  // depth -> lowest y used so far in that column
  const sourceId = `source:${session.source_job || "upload"}`;
  const position = (id, fallback) => session.positions?.[id] || fallback;

  nodes.push({ id: sourceId, type: "source", position: position(sourceId, { x: 0, y: 320 }), data: { session, ...actions } });

  for (const [number, group] of sessionGroups(session, groups).entries()) {
    const refs = group.parent_clips?.length ? group.parent_clips : group.parent_clip?.job_id ? [group.parent_clip] : [];
    const depth = refs.length ? 1 + Math.max(0, ...refs.map((ref) => depths.get(ref.job_id) || 0)) : 0;
    depths.set(group.job_id, depth);

    // Stack this generation's clips in one column, level with its parents when it has some
    const parents = refs.map((ref) => placed.get(clipKey(ref))).filter(Boolean);
    const entries = displayClips(session, groups, group);
    const height = Math.max(1, entries.length) * CLIP_HEIGHT;
    const desired = parents.length ? parents.reduce((sum, p) => sum + p.y, 0) / parents.length - height / 2 : 0;
    const top = Math.max(0, desired, bottoms.get(depth) || 0);
    bottoms.set(depth, top + height + 100);

    const hubId = `generation:${group.job_id}`;
    const isUpdated = entries.some((entry) => entry.ref.job_id !== group.job_id);
    nodes.push({
      id: hubId,
      type: "generation",
      position: position(hubId, { x: GENERATION_X + depth * DEPTH_GAP, y: top + height / 2 - 60 }),
      data: { group: { ...group, displayed_clip_count: entries.length, is_updated: isUpdated }, number: number + 1, ...actions },
    });

    // Vines in: from the video, or from each clip it was "more like"
    const sources = refs.length ? refs.map((ref) => `clip:${clipKey(ref)}`) : [sourceId];
    for (const source of sources) {
      edges.push({ id: `${source}>${hubId}`, source, target: hubId, type: "vine",
        animated: ["queued", "processing"].includes(group.state) });
    }

    // Vines out: to each clip
    for (const [index, entry] of entries.entries()) {
      const { clip, ref, label, revision } = entry;
      const id = `clip:${clipKey(ref)}`;
      const pos = position(id, { x: CLIP_X + depth * DEPTH_GAP, y: top + index * CLIP_HEIGHT });
      placed.set(clipKey(ref), pos);
      nodes.push({ id, type: "clip", position: pos, data: { clip, ref, label, revision, number: number + 1, ...actions } });
      edges.push({ id: `${hubId}>${id}`, source: hubId, target: id, type: "vine" });
    }
  }

  // Don't draw a vine to a box that isn't there (e.g. an old reference that was deleted)
  const ids = new Set(nodes.map((node) => node.id));
  return { nodes, edges: edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)) };
}
