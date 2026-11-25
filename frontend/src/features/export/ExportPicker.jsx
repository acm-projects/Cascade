import { useEffect, useState } from "react";
import Modal from "../../components/ui/Modal";
import Button from "../../components/ui/Button";
import Spinner from "../../components/ui/Spinner";
import Icon from "../../components/ui/Icon";
import useApi from "../../api/useApi";
import { formatTime } from "../../utils/time";
import { clipKey, flattenClips } from "../editor/clips";
import { defaultPicks } from "./exportPicks";
import "./ExportPicker.css";

// "Which clips go to Export?" Opens from the Editor's Export button (and the Export step in the top bar).
// Edited clips (backend/editor/drafts.py `edited`) and the clip on screen start ticked.
//   onConfirm(keys) - go to Export with these clips; onClose - stay in the Editor
// The caller saves the current clip first, so the "Edited" marks are up to date.
export default function ExportPicker({ projectId, currentKey, onConfirm, onClose }) {
  const api = useApi();
  const [clips, setClips] = useState(null);
  const [error, setError] = useState(null);
  const [picks, setPicks] = useState([]);

  useEffect(() => {
    let active = true;
    api.getEditorIndex(projectId, { selectedOnly: true })
      .then((index) => {
        if (!active) return;
        const list = flattenClips(index);
        setClips(list);
        setPicks(defaultPicks(list, currentKey));
      })
      .catch((err) => active && setError(err));
    return () => { active = false; };
  }, [api, projectId, currentKey]);

  const toggle = (key) => setPicks((now) => (now.includes(key) ? now.filter((k) => k !== key) : [...now, key]));
  const edited = clips?.filter((clip) => clip.edited) ?? [];
  const count = picks.length;

  return (
    <Modal title="Which clips do you want to export?" onClose={onClose} wide className="export-picker">
      {error ? <p role="alert">{error.message}</p>
        : !clips ? <Spinner label="Loading your clips" />
          : <>
            <p className="export-picker-note">
              Only the clips you tick go to Export. {edited.length
                ? `${edited.length} of ${clips.length} ${clips.length === 1 ? "clip has" : "clips have"} your edits.`
                : "None of these clips has been edited yet."}
            </p>
            <div className="export-picker-quick">
              <button type="button" className="export-link" onClick={() => setPicks(clips.map(clipKey))}>Select all</button>
              {edited.length > 0 && (
                <button type="button" className="export-link" onClick={() => setPicks(edited.map(clipKey))}>Only edited clips</button>
              )}
              <button type="button" className="export-link" onClick={() => setPicks([])}>Clear</button>
            </div>
            <ul className="export-picker-list">
              {clips.map((clip, i) => {
                const key = clipKey(clip);
                return (
                  <li key={key}>
                    <label className={`export-picker-row${picks.includes(key) ? " is-picked" : ""}`}>
                      <input type="checkbox" checked={picks.includes(key)} onChange={() => toggle(key)} />
                      <span className="export-picker-name">
                        <b>Clip {i + 1}</b> {clip.title && <span title={clip.title}>{clip.title}</span>}
                      </span>
                      {key === currentKey && <span className="export-picker-tag is-current">On screen</span>}
                      {clip.edited
                        ? <span className="export-picker-tag is-edited"><Icon name="check" /> Edited</span>
                        : <span className="export-picker-tag">Not edited</span>}
                      <span className="export-picker-time">{formatTime(clip.end - clip.start)}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </>}
      <div className="export-picker-actions">
        <Button size="sm" onClick={onClose}>Keep editing</Button>
        <Button size="sm" variant="primary" disabled={!count} onClick={() => onConfirm(picks)}>
          {count ? `Export ${count} ${count === 1 ? "clip" : "clips"}` : "Tick a clip to export"} →
        </Button>
      </div>
    </Modal>
  );
}
