// Turns a running generation's live status (from GET /api/projects/{id}/generations) into what the
// chat shows: five stages, the step happening now, and a readable step list.
// The backend sends: timing_stage (the StageTimer name), timings ({stage: seconds} for finished
// stages), timing_stage_started_at (epoch seconds), steps_log + steps_elapsed, ready_clip_count.

// Stage names must match the StageTimer.start() calls in backend/routers/clips.py and
// backend/agent/website.py.
export const STAGES = [
  { key: "Video inspection", label: "Preparing video" },
  { key: "Transcript and search index", label: "Transcribing & indexing" },
  { key: "Transcript summaries", label: "Reading the video" },
  { key: "AI agent selection", label: "Picking moments" },
  { key: "Video rendering and storage", label: "Rendering clips" },
];

const time = (seconds) => {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

// A duration: "0.4s", "12s", "1:05"
export const duration = (seconds) => {
  const s = Math.max(0, Number(seconds) || 0);
  return s < 10 ? `${s.toFixed(1)}s` : s < 60 ? `${Math.round(s)}s` : time(s);
};

// Each step lasts until the next one starts; the last step has no duration yet. The longest
// step (of at least a second) is marked slowest, so the bottleneck stands out.
function timedSteps(log = [], elapsed = []) {
  const steps = log.map((text, i) => ({
    text, label: stepLabel(text), atSeconds: elapsed[i],
    took: elapsed[i] !== undefined && elapsed[i + 1] !== undefined ? elapsed[i + 1] - elapsed[i] : undefined,
  }));
  const slowest = steps.reduce((best, s, i) => (s.took >= 1 && s.took > (steps[best]?.took ?? 0) ? i : best), -1);
  return steps.map((s, i) => ({
    text: s.text, label: s.label, at: s.atSeconds === undefined ? "" : time(s.atSeconds),
    took: s.took === undefined ? "" : duration(s.took), slowest: i === slowest,
  }));
}

// Finished stages, slowest first: { total: "18s", parts: [{ label, took, slowest }] }. The total is
// the wall time (the last step's time) when known: it includes the short gaps between stages.
export function timingSummary(timings, labels, wallSeconds) {
  const entries = Object.entries(timings ?? {}).filter(([, s]) => Number(s) > 0).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return null;
  return {
    total: duration(wallSeconds ?? entries.reduce((sum, [, s]) => sum + Number(s), 0)),
    parts: entries.map(([key, s], i) => ({ label: labels[key] ?? key, took: duration(s), slowest: i === 0 && entries.length > 1 })),
  };
}

const STAGE_LABELS = { ...Object.fromEntries(STAGES.map((s) => [s.key, s.label])), "Waiting for video analysis": "Waiting for analysis" };

const arg = (text, name) => text.match(new RegExp(`${name}=(?:'([^']*)'|"([^"]*)"|([^,)]+))`))?.slice(1).find((v) => v !== undefined);

// One step-log line in plain words ("Tool call: inspect_clip(start_time=62.0, ...)" -> "Checking 1:02-1:20").
export function stepLabel(step) {
  const call = step.match(/^Tool call: (\w+)\((.*)\)$/s);
  if (!call) return step;
  const [, tool, args] = call;
  const range = () => `${time(arg(args, "start_time"))}–${time(arg(args, "end_time"))}`;
  switch (tool) {
    case "search_video": return `Searching: ${arg(args, "query") ?? "the video"}`;
    case "inspect_clip": return `Checking ${range()}`;
    case "read_transcript": return `Reading transcript ${range()}`;
    case "add_candidate": return `Shortlisting ${range()}`;
    case "rank_candidates": return "Ranking the shortlist";
    case "get_overview": return "Getting an overview";
    default: return step;
  }
}

// How far through the current stage we are (0-1), and a short "3 of 8" style detail, from the newest
// step line that carries a count.
function stageDetail(stageKey, steps, group) {
  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i];
    let m;
    if (stageKey === "Transcript summaries" && (m = step.match(/Summarizing transcript: (\d+)\/(\d+) chunks/)))
      return { fraction: m[1] / m[2], detail: `${m[1]} of ${m[2]} sections` };
    if (stageKey === "AI agent selection" && (m = step.match(/Agent turn (\d+)\/(\d+)|pass (\d+)\/(\d+)/))) {
      const [done, total] = m[1] ? [m[1], m[2]] : [m[3], m[4]];
      return { fraction: (done - 1) / total, detail: `step ${done} of ${total}` };
    }
    if (stageKey === "Video rendering and storage" && (m = step.match(/(?:Cutting|Saving) clip \d+\/(\d+)/))) {
      const ready = group.ready_clip_count ?? 0;
      return { fraction: ready / m[1], detail: `${ready} of ${m[1]} clips ready` };
    }
  }
  return { fraction: 0, detail: "" };
}

export function describeProgress(group, nowSeconds = Date.now() / 1000) {
  const steps = timedSteps(group.steps_log, group.steps_elapsed);
  const finished = Object.keys(group.timings ?? {});
  const reached = [...finished, group.timing_stage].map((key) => STAGES.findIndex((s) => s.key === key));
  // A prompt sent while the project video is still being analysed waits before any stage starts.
  const waiting = group.timing_stage === "Waiting for video analysis";
  const current = group.state === "queued" || waiting ? -1 : Math.max(-1, ...reached);
  const { fraction, detail } = current >= 0 ? stageDetail(STAGES[current].key, group.steps_log ?? [], group) : { fraction: 0, detail: "" };

  // Finished stages plus the running one (the server clock stamps when it started).
  const running = group.timing_stage && group.timing_stage_started_at ? Math.max(0, nowSeconds - group.timing_stage_started_at) : 0;
  const elapsed = Object.values(group.timings ?? {}).reduce((sum, s) => sum + Number(s || 0), 0) + running;

  return {
    stages: STAGES.map((stage, i) => ({
      label: stage.label,
      status: i < current ? "done" : i === current ? "active" : "pending",
      fill: i < current ? 1 : i === current ? Math.min(1, Math.max(0, fraction)) : 0,
    })),
    stage: waiting ? "Queued — starts when video analysis finishes" : current >= 0 ? STAGES[current].label : "Waiting to start",
    detail,
    now: steps.at(-1)?.label ?? "",
    elapsed: time(elapsed),
    steps,
    summary: group.state === "done" ? timingSummary(group.timings, STAGE_LABELS, group.steps_elapsed?.at(-1)) : null,
  };
}

// ---------- The project video's analysis (GET /api/projects/{id}/studio -> index) ----------
// Stage names must match the StageTimer.start() calls in backend/indexing.py.
export const INDEX_STAGES = [
  { key: "Preparing video", label: "Preparing video" },
  { key: "Transcript and search index", label: "Transcribing & scanning frames" },
  { key: "Moment cards", label: "Writing moment cards" },
];

// Rough analysis time from the video length, fitted to past runs: frames take ~2.7s per minute
// (capped at 300 frames, ~60s); transcript + cards ~1.9s per minute; both run side by side.
const INDEX_LABELS = { ...Object.fromEntries(INDEX_STAGES.map((s) => [s.key, s.label])),
  "Finishing video conversion": "Waiting for the video conversion" };

export function estimateIndexSeconds(videoSeconds, hasVideo = true) {
  const minutes = (Number(videoSeconds) || 0) / 60;
  const frames = hasVideo ? Math.min(60, minutes * 2.7) : 0;
  return 5 + Math.max(frames, minutes * 1.9);
}

export function describeIndex(index, nowSeconds = Date.now() / 1000) {
  if (!index) return null;
  const steps = timedSteps(index.steps_log, index.steps_elapsed);
  if (index.state === "done") {
    // Transcript and frames run side by side inside one stage: show both, so the slower one is visible.
    const t = index.index_timings ?? {};
    const parallel = t.transcript_index_seconds !== undefined && t.visual_index_seconds !== undefined
      ? `transcript ${duration(t.transcript_index_seconds)} and frames ${duration(t.visual_index_seconds)} ran side by side` : "";
    return { ready: true, moments: index.moment_count ?? 0, summary: timingSummary(index.timings, INDEX_LABELS, index.steps_elapsed?.at(-1)), parallel, steps };
  }
  if (index.state === "error") return { error: index.message || "Video analysis failed." };
  const finished = Object.keys(index.timings ?? {});
  // After the analysis, a slow upload (HEVC, WebM...) may still be converting: every bar is full then.
  const converting = index.timing_stage === "Finishing video conversion";
  const current = index.state === "queued" ? -1 : converting ? INDEX_STAGES.length
    : Math.max(-1, ...[...finished, index.timing_stage].map((key) => INDEX_STAGES.findIndex((s) => s.key === key)));
  const cards = (index.steps_log ?? []).map((s) => s.match(/Writing moment cards: (\d+)\/(\d+)/)).filter(Boolean).at(-1);
  const fraction = current === 2 && cards ? cards[1] / cards[2] : 0;
  let left = "";
  if (index.duration && index.started_at) {
    const remaining = estimateIndexSeconds(index.duration, index.media_kind !== "audio") - (nowSeconds - index.started_at);
    left = remaining > 60 ? `about ${Math.round(remaining / 60)} min left` : remaining > 0 ? `about ${Math.ceil(remaining / 5) * 5}s left` : "almost done";
  }
  return {
    stages: INDEX_STAGES.map((stage, i) => ({
      label: stage.label,
      status: i < current ? "done" : i === current ? "active" : "pending",
      fill: i < current ? 1 : i === current ? Math.min(1, fraction) : 0,
    })),
    stage: converting ? "Finishing the video conversion" : current >= 0 ? INDEX_STAGES[current].label
      : index.state === "processing" ? index.message || "Starting" : "Waiting to start",
    detail: cards && current === 2 ? `${cards[1]} of ${cards[2]} moments` : "",
    now: stepLabel(index.steps_log?.at(-1) ?? ""),
    left,
    steps,
  };
}
