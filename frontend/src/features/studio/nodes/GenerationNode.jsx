import { Handle, Position } from "@xyflow/react";
import Spinner from "../../../components/ui/Spinner";

// One prompt you sent ("a generation"). Its clips grow out of its right side.
//   data.group   - from listGenerations: { job_id, prompt, state, message, clips, requested_clip_count,
//                  selection_note, displayed_clip_count, is_updated }
//   data.number  - 1, 2, 3... in this session
//   data.onStop(jobId), data.onRetry(jobId), data.onReuse(prompt)
function GenerationNode({ data }) {
  const { group, number, onStop, onRetry, onReuse } = data;
  const active = ["queued", "processing"].includes(group.state);

  let status;
  if (active) status = group.message || "Finding moments…";
  else if (group.state === "error") status = group.message || "This request failed.";
  else if (group.is_updated) status = `${group.displayed_clip_count} clips · updated`;
  else status = `${group.clips.length} of ${group.requested_clip_count || group.clips.length} clips ready`;

  return (
    <div className={`studio-node studio-generation-node is-${group.state}`}>
      <Handle type="target" position={Position.Left} />
      <span className="studio-node-kicker">💬 Prompt {number}</span>
      <span className="studio-generation-prompt">{group.prompt}</span>
      <span className="studio-generation-status" role="status">
        {active && <Spinner size={14} label="Working" />} {status}
      </span>
      {group.selection_note && !group.is_updated && <span className="studio-generation-note">{group.selection_note}</span>}
      <div className="studio-node-actions nodrag nopan">
        {active && <button type="button" className="btn btn-ghost btn-small" onClick={() => onStop(group.job_id)}>Stop</button>}
        {group.state === "error" && (
          <button type="button" className="btn btn-primary btn-small" onClick={() => onRetry(group.job_id)}>Retry</button>
        )}
        <button type="button" className="btn btn-ghost btn-small" onClick={() => onReuse(group.prompt)}>Reuse prompt</button>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

export default GenerationNode;
