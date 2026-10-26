import { Handle, Position } from "@xyflow/react";

// The video box on the left of the canvas.
// No video yet: an upload box (click it, or drop a file anywhere on the canvas).
//   data.video       - { name, url } or null
//   data.onFile(f)   - a video file was picked
//   data.onRemove()  - the ✕ was clicked
//   data.onDuration  - the video's length in seconds is known
// "nodrag" on the clickable parts stops React Flow from treating a click as dragging the box.
function SourceNode({ data }) {
  const { video, onFile, onRemove, onDuration } = data;

  return (
    <div className="studio-node studio-source-node">
      {video ? (
        <>
          <video
            className="studio-source-video nodrag nopan"
            src={video.url}
            controls
            muted
            playsInline
            onLoadedMetadata={(e) => onDuration(e.target.duration)}
          />
          <div className="studio-source-name">
            <span title={video.name}>🎬 {video.name}</span>
            <button type="button" className="nodrag" onClick={onRemove} title="Remove video">✕</button>
          </div>
        </>
      ) : (
        <label className="studio-drop nodrag">
          <input type="file" accept="video/*" hidden onChange={(e) => onFile(e.target.files[0])} />
          <span className="studio-drop-icon">▶</span>
          <span className="studio-drop-title">Drop a video here</span>
          <span className="studio-drop-hint">or click to upload</span>
          <span className="btn btn-primary btn-small">⬆ Upload Video</span>
        </label>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

export default SourceNode;
