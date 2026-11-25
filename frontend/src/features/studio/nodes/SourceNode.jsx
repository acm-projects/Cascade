import { Handle, Position } from "@xyflow/react";
import { MEDIA_ACCEPT } from '../../../utils/media';
import Icon from "../../../components/ui/Icon";

// The footage box on the left of the canvas.
// No footage yet: pick one or more files (click the box, or drop files anywhere on the canvas). They upload with
// your first prompt; several files are joined end to end into one source, in the order listed.
//   data.session            - the current studio session (source_job is set once footage is uploaded)
//   data.sourceName         - the uploaded footage's name
//   data.pendingFiles       - files picked but not uploaded yet
//   data.onChooseFiles(fs)  - files were picked (added to the list)
//   data.onRemoveFile(i)    - take a picked file off the list
//   data.onPreviewSource(i) - watch the uploaded footage, or picked file i
// "nodrag" on the clickable parts stops React Flow from treating a click as dragging the box.
export function SourceCard({ data, children }) {
  const { session, sourceName, pendingFiles = [], onChooseFiles, onRemoveFile, onPreviewSource } = data;
  const pick = (event) => {
    onChooseFiles(event.target.files);
    event.target.value = ""; // picking the same file again still fires onChange
  };

  return (
    <div className="studio-node studio-source-node">
      <span className="studio-node-kicker">Original media</span>
      {session.source_job ? (
        <>
          <button type="button" className="studio-poster nodrag nopan" onClick={() => onPreviewSource()}>
            <span className="studio-poster-play"><Icon name="play" /></span>
            <span>Preview original</span>
          </button>
          <strong className="studio-source-name" title={sourceName}>{sourceName || "Uploaded video"}</strong>
        </>
      ) : pendingFiles.length ? (
        <div className="studio-file-picks nodrag nopan">
          <ol className="studio-file-list nowheel">
            {pendingFiles.map((file, index) => (
              <li key={`${file.name}|${file.size}|${file.lastModified}`}>
                <button type="button" className="studio-file-name" title={`Preview ${file.name}`}
                  onClick={() => onPreviewSource(index)}>
                  <Icon name="film" /> <span>{file.name}</span>
                </button>
                <button type="button" className="studio-file-remove" aria-label={`Remove ${file.name}`}
                  title="Remove" onClick={() => onRemoveFile(index)}>
                  <Icon name="close" />
                </button>
              </li>
            ))}
          </ol>
          <span className="studio-drop-hint">
            {pendingFiles.length > 1 ? `${pendingFiles.length} files, joined in this order. Now describe the clips you want`
              : "Now describe the clips you want in the chat"}
          </span>
          <label className="btn btn-small studio-drop-button">
            <input type="file" accept={MEDIA_ACCEPT} multiple hidden onChange={pick} />
            <Icon name="plus" /> Add more files
          </label>
        </div>
      ) : (
        <label className="studio-drop nodrag">
          <input type="file" accept={MEDIA_ACCEPT} multiple hidden onChange={pick} />
          <span className="studio-drop-icon"><Icon name="play" /></span>
          <span className="studio-drop-title">Drop your video or audio</span>
          <span className="studio-drop-hint">or click to choose one or more files</span>
          <span className="btn btn-primary btn-small studio-drop-button">
            <Icon name="upload" /> Choose files
          </span>
        </label>
      )}
      {children}
    </div>
  );
}

// On the flat React Flow canvas: the card, with the dot the vine starts from
function SourceNode({ data }) {
  return (
    <SourceCard data={data}>
      <Handle type="source" position={Position.Right} />
    </SourceCard>
  );
}

export default SourceNode;
