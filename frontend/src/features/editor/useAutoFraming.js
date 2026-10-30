import { useEffect, useRef, useState } from "react";
import useApi from "../../api/useApi";

const RATIOS = { "9:16": 9 / 16, "1:1": 1, "4:5": 4 / 5, "16:9": 16 / 9, "4:3": 4 / 3 };
const POLL_MS = 1500;

// Does this edit crop the video? (Fill into a different shape than the clip's own)
export function needsFraming(state, info) {
  if (!state || !info || info.has_video === false || state.composition.mode !== "fill" || state.composition.ratio === "original") return false;
  return Math.abs(RATIOS[state.composition.ratio] - info.width / info.height) > 0.01;
}

// Fill (crop) exports need a "who is in the frame" analysis first, so the crop can follow people.
// When an edit crops and has no finished analysis yet, this starts one, checks on it, and stores its
// id in the edit with patch() (not an undo step) once it's ready.
//   returns { status: "idle" | "working" | "ready" | "error", progress: 0-1, message }
export default function useAutoFraming(projectId, clip, state, info, patch) {
  const api = useApi();
  const [framing, setFraming] = useState({ status: "idle", progress: 0, message: "" });
  const wanted = needsFraming(state, info) && !state.reframe.analysis_id;
  // The analysis doesn't depend on the exact crop position, so moving the sliders shouldn't restart it
  const composition = useRef(state?.composition);
  useEffect(() => {
    composition.current = state?.composition;
  });

  useEffect(() => {
    if (!wanted) return;
    let active = true;
    let timer = null;

    function check(analysisId) {
      api.getReframe(projectId, clip.job_id, clip.clip_index, analysisId)
        .then((record) => {
          if (!active) return;
          if (record.status === "ready") {
            setFraming({ status: "ready", progress: 1, message: "Automatic framing ready." });
            patch((s) => ({ ...s, reframe: { ...s.reframe, analysis_id: analysisId } }));
          } else if (record.status === "error") {
            setFraming({ status: "error", progress: 0, message: record.message || "Automatic framing failed." });
          } else {
            setFraming({ status: "working", progress: record.progress || 0, message: record.message || "Preparing automatic framing…" });
            timer = setTimeout(() => check(analysisId), POLL_MS);
          }
        })
        .catch((err) => active && setFraming({ status: "error", progress: 0, message: err.message }));
    }

    api.startReframe(projectId, clip.job_id, clip.clip_index, { composition: composition.current, focus: "auto", selection: null })
      .then((started) => active && check(started.analysis_id))
      .catch((err) => active && setFraming({ status: "error", progress: 0, message: err.message }));

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [wanted, api, projectId, clip.job_id, clip.clip_index, patch]);

  return wanted || framing.status === "error" ? framing : { status: "idle", progress: 0, message: "" };
}
