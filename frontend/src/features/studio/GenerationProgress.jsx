import { useEffect, useState } from "react";
import { describeProgress } from "./progressModel.js";

// Inside a generation's chat bubble: a five-stage bar and the current step while it runs, and a
// "Show steps" list (running or finished) built from the job's step log.
function GenerationProgress({ group }) {
  const running = ["queued", "processing"].includes(group.state);
  const [now, setNow] = useState(() => Date.now() / 1000);

  // Tick the elapsed timer between status polls
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(timer);
  }, [running]);

  const progress = describeProgress(group, now);
  if (!running && !progress.steps.length) return null;

  return (
    <div className="generation-progress">
      {running && <>
        <div className="generation-progress-bar" role="list" aria-label="Progress">
          {progress.stages.map((stage) => (
            <div key={stage.label} role="listitem" title={stage.label}
              className={`generation-progress-stage is-${stage.status}`}
              aria-label={`${stage.label}: ${stage.status === "done" ? "done" : stage.status === "active" ? "in progress" : "not started"}`}>
              <span style={{ width: `${stage.fill * 100}%` }} />
            </div>
          ))}
        </div>
        <p className="generation-progress-stage-name">
          <b>{progress.stage}</b>
          {progress.detail && <> · {progress.detail}</>}
          <span className="generation-progress-time"> · {progress.elapsed}</span>
        </p>
        {progress.now && <p className="generation-progress-now">{progress.now}</p>}
      </>}
      {progress.summary && <TimingSummary summary={progress.summary} />}
      {progress.steps.length > 0 && <StepList steps={progress.steps} title={running ? "Show steps" : `Show all ${progress.steps.length} steps`} />}
    </div>
  );
}

// "Done in 18s · Rendering clips 9.8s (slowest) · Picking moments 6.1s · ..."
export function TimingSummary({ summary, prefix = "Done in" }) {
  return (
    <p className="generation-progress-summary">
      <b>{prefix} {summary.total}</b>
      {summary.parts.map((part) => (
        <span key={part.label} className={part.slowest ? "is-slowest" : undefined}>
          {" · "}{part.label} {part.took}{part.slowest && " (slowest)"}
        </span>
      ))}
    </p>
  );
}

// Every step with when it started and how long it took; the slowest step is highlighted.
export function StepList({ steps, title }) {
  return (
    <details className="generation-progress-steps">
      <summary>{title}</summary>
      <ol>
        {steps.map((step, i) => (
          <li key={i} className={step.slowest ? "is-slowest" : undefined}>
            <span className="generation-progress-time">{step.at}</span>
            <span>
              {step.label}
              {step.took && <span className="generation-progress-took"> · {step.took}{step.slowest && " — slowest step"}</span>}
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}

export default GenerationProgress;
