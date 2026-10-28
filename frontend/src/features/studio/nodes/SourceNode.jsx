import { Handle, Position } from "@xyflow/react";
import { MEDIA_ACCEPT } from '../../../utils/media';

// The video box on the left of the canvas.
// No video yet: pick one (click the box, or drop a file anywhere on the canvas). It uploads with your first prompt.
//   data.session          - the current studio session (source_job is set once a video is uploaded)
//   data.sourceName       - the uploaded video's file name
//   data.pendingFile      - a video picked but not uploaded yet
//   data.onChooseFile(f)  - a video was picked
//   data.onPreviewSource  - watch the video
// "nodrag" on the clickable parts stops React Flow from treating a click as dragging the box.
function SourceNode({ data }) {
  const { session, sourceName, pendingFile, onChooseFile, onPreviewSource } = data;
  const hasVideo = Boolean(session.source_job || pendingFile);

  return (
    <div className="studio-node studio-source-node">
      <span className="studio-node-kicker">Original media</span>
      {session.source_job ? (
        <>
          <button type="button" className="studio-poster nodrag nopan" onClick={onPreviewSource}>
            <span className="studio-poster-play">▶</span>
            <span>Preview original</span>
          </button>
          <strong className="studio-source-name" title={sourceName}>{sourceName || "Uploaded video"}</strong>
        </>
      ) : (
        <label className="studio-drop nodrag">
          <input type="file" accept={MEDIA_ACCEPT} hidden onChange={(e) => onChooseFile(e.target.files[0])} />
          <span className="studio-drop-icon">{hasVideo ? "✓" : "▶"}</span>
          <span className="studio-drop-title">{pendingFile ? pendingFile.name : "Drop video or audio here"}</span>
          <span className="studio-drop-hint">
            {pendingFile ? "Now describe the clips you want in the chat" : "or click to choose one"}
          </span>
          <span className="btn btn-primary btn-small">{pendingFile ? "Change media" : "⬆ Choose video or audio"}</span>
        </label>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

export default SourceNode;
