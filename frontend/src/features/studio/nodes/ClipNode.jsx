import { Handle, Position } from "@xyflow/react";
import { formatTime } from "../../../utils/time";
import { sameRef } from "../graph";

// One clip the AI found. Check it to (1) guide the next prompt ("more like this") and
// (2) take it to the Editor. ▶ opens it big.
//   data.clip       - { title, explanation, start, end, clip_url }
//   data.ref        - { job_id, clip_index } (which clip this is, for the backend)
//   data.label      - "2", or "2.1" after a "more like this" update replaced it
//   data.number     - which prompt it came from
//   data.revision   - a "more like this" update still running/failed for this slot (or null)
//   data.highlighted - the ref whose chip is hovered in the chat (that clip glows)
//   data.editorClips, data.onToggle(ref), data.onPreview(clip, ref), data.onRetry(jobId)
function ClipNode({ data }) {
  const { clip, ref, label, number, revision, editorClips, highlighted, onToggle, onPreview, onRetry } = data;
  const selected = editorClips.some((item) => sameRef(item, ref));
  const updating = revision && ["queued", "processing"].includes(revision.state);

  return (
    <div className={`studio-node studio-clip-node${selected ? " is-selected" : ""}${highlighted && sameRef(highlighted, ref) ? " is-highlighted" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <div className="studio-clip-head">
        <span>P{number} · Clip {label}</span>
        <span>{formatTime(clip.end - clip.start)}</span>
      </div>
      <button type="button" className="studio-poster nodrag nopan" onClick={() => onPreview(clip, ref)}
        aria-label={`Preview ${clip.title || "clip"}`}>
        <span className="studio-poster-play">▶</span>
        <span>{formatTime(clip.start)} – {formatTime(clip.end)}</span>
      </button>
      <strong className="studio-clip-title" title={clip.title}>{clip.title || "A moment from your video"}</strong>
      {clip.explanation && <span className="studio-clip-why" title={clip.explanation}>{clip.explanation}</span>}
      {revision && (
        <span className="studio-clip-revision" role="status">
          {updating ? "Finding similar moments…" : revision.state === "error" ? "Update failed. Your clip is kept." : "No new matches. Your clip is kept."}
          {revision.state === "error" && (
            <button type="button" className="btn btn-ghost btn-small nodrag" onClick={() => onRetry(revision.job_id)}>Retry</button>
          )}
        </span>
      )}
      <label className="studio-clip-select nodrag nopan">
        <input type="checkbox" checked={selected} onChange={() => onToggle(ref)}
          aria-label={`Pick prompt ${number} clip ${label}: ${clip.title || "clip"}`} />
        {selected ? "Picked ✓" : "Pick clip"}
      </label>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

export default ClipNode;
