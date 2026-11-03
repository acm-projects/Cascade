import { useEffect, useState } from "react";
import { describeIndex } from "./progressModel.js";
import { StepList, TimingSummary } from "./GenerationProgress.jsx";

// Above the chat box while the project's video is being analysed (it starts when the project is
// created): a three-stage bar, the current step and a time estimate. Prompts can still be sent;
// they wait for the analysis. On failure: the error and a Retry button.
function IndexStatus({ index, onRetry }) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  const running = index && ["queued", "processing"].includes(index.state);

  // Tick the time estimate between status polls
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(timer);
  }, [running]);

  const status = describeIndex(index, now);
  if (!status) return null;
  if (status.ready) {
    return (
      <span className="index-status generation-progress">
        {status.summary && <TimingSummary summary={status.summary} prefix={`Video ready (${status.moments} moments) — analysed in`} />}
        {status.parallel && <span className="generation-progress-now">{status.parallel}</span>}
        {status.steps.length > 0 && <StepList steps={status.steps} title="Show analysis steps" />}
      </span>
    );
  }
  if (status.error) {
    return (
      <span className="index-status is-error" role="alert">
        {status.error}{" "}
        <button type="button" className="btn btn-small" onClick={onRetry}>Retry analysis</button>
      </span>
    );
  }
  return (
    <span className="index-status generation-progress" aria-live="polite">
      <b>Analysing your video</b>
      <span>You can send a prompt now; it starts when this finishes.</span>
      <span className="generation-progress-bar" role="list" aria-label="Video analysis">
        {status.stages.map((stage) => (
          <span key={stage.label} role="listitem" title={stage.label}
            className={`generation-progress-stage is-${stage.status}`}
            aria-label={`${stage.label}: ${stage.status === "done" ? "done" : stage.status === "active" ? "in progress" : "not started"}`}>
            <span style={{ width: `${stage.fill * 100}%` }} />
          </span>
        ))}
      </span>
      <span className="generation-progress-stage-name">
        <b>{status.stage}</b>
        {status.detail && <> · {status.detail}</>}
        {status.left && <span className="generation-progress-time"> · {status.left}</span>}
      </span>
      {status.now && <span className="generation-progress-now">{status.now}</span>}
      {status.steps.length > 0 && <StepList steps={status.steps} title="Show steps" />}
    </span>
  );
}

export default IndexStatus;
