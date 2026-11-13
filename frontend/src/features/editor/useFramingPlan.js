import { useEffect, useState } from "react";
import useApi from "../../api/useApi";
import { needsFraming } from "./useAutoFraming";

const POLL_MS = 1200;

// Where a Fill crop should sit over time so it follows whoever is talking, for the instant preview.
// Waits for the "who is talking" analysis (usually already done: it starts when the clip opens), then asks
// for the crop path. Returns [{ t, x, y }] (source seconds, 0-1 crop positions), or null while it isn't ready.
export default function useFramingPlan(projectId, clip, state, info) {
  const api = useApi();
  const [plan, setPlan] = useState(null);
  const wanted = needsFraming(state, info);
  const { ratio, mode } = state.composition;
  const analysisId = state.reframe?.analysis_id || null;
  const focus = state.reframe?.focus || "auto";

  useEffect(() => {
    if (!wanted) return undefined;
    let live = true;
    let timer = null;
    const body = { composition: { ...state.composition, x: 0.5, y: 0.5 }, focus, selection: state.reframe?.selection || null };

    async function run() {
      try {
        let id = analysisId;
        if (!id) id = (await api.startReframe(projectId, clip.job_id, clip.clip_index, body)).analysis_id;
        for (;;) {
          const record = await api.getReframe(projectId, clip.job_id, clip.clip_index, id);
          if (!live) return;
          if (record.status === "ready") break;
          if (record.status === "error") return; // no speaker tracking: the preview keeps a steady centered crop
          await new Promise((resolve) => { timer = setTimeout(resolve, POLL_MS); });
          if (!live) return;
        }
        const result = await api.getReframePlan(projectId, clip.job_id, clip.clip_index, id, body);
        if (live && result?.points?.length) setPlan({ ratio, points: result.points });
      } catch {
        /* the preview just stays on the steady crop */
      }
    }
    run();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  // Only the shape and the analysis decide the path; dragging the crop or editing captions must not restart it
  }, [wanted, ratio, mode, analysisId, focus, api, projectId, clip.job_id, clip.clip_index]); // eslint-disable-line react-hooks/exhaustive-deps

  return wanted && plan?.ratio === ratio ? plan.points : null;
}

/** The crop position at source second t, interpolated between the plan's points (same rule the export uses). */
export function framingAt(points, t) {
  if (!points?.length) return null;
  if (t <= points[0].t) return { x: points[0].x, y: points[0].y };
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    if (t <= b.t) {
      const k = b.t > a.t ? Math.min(1, Math.max(0, (t - a.t) / (b.t - a.t))) : 1;
      return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k };
    }
  }
  const last = points[points.length - 1];
  return { x: last.x, y: last.y };
}
