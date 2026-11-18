import { useState } from "react";
import Modal from "../../components/ui/Modal";
import Icon from "../../components/ui/Icon";
import { clipKey, combinable } from "./clips";
import { formatTime } from "../../utils/time";
import "./CombineClips.css";

// Multi-clip editing: a "Combine" button next to the clip tabs opens a picker; tick the clips to join (they play in
// list order) and "Combine" makes them one clip that the Editor opens. Shown only when two or more clips can be joined.
//   clips: the Editor's clip list; onCombine(chosenClips) -> Promise; busy: a combine is running
//   className: the button's look (the clip tabs pass their tab class so it sits in line with them); compact: icon only
export default function CombineClips({ clips, onCombine, busy, className = "btn btn-small", compact = false }) {
  const options = combinable(clips);
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState(() => new Set(options.map(clipKey)));
  if (options.length < 2) return null;

  const picked = options.filter((clip) => chosen.has(clipKey(clip)));
  const total = picked.reduce((sum, clip) => sum + (clip.end - clip.start), 0);
  const toggle = (key) => setChosen((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  const number = (clip) => clips.findIndex((item) => clipKey(item) === clipKey(clip)) + 1;

  return (
    <>
      <button type="button" className={`${className} combine-clips-button${compact ? " is-compact" : ""}`} disabled={busy}
        onClick={() => setOpen(true)} aria-label="Combine clips into one edit" title="Combine clips into one edit">
        {busy ? <span className="combine-spinner" /> : <Icon name="film" />}
        {!compact && (busy ? " Combining…" : " Combine")}
      </button>
      {open && (
        <Modal title="Combine clips into one edit" onClose={() => setOpen(false)}>
          <div className="combine-clips-picker">
            <p className="combine-note">Tick the clips to join. They play in this order, then the Editor opens the new clip.</p>
            <ul>
              {options.map((clip) => {
                const key = clipKey(clip);
                return (
                  <li key={key}>
                    <label>
                      <input type="checkbox" checked={chosen.has(key)} onChange={() => toggle(key)} />
                      <b>Clip {number(clip)}</b> {clip.title || ""}
                      <span className="combine-note">{formatTime(clip.end - clip.start)}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
            <div className="combine-actions">
              <button type="button" className="btn btn-primary" disabled={picked.length < 2}
                title={picked.length < 2 ? "Pick at least two clips" : undefined}
                onClick={() => { setOpen(false); onCombine(picked).catch(() => {}); }}>
                Combine {picked.length} clips ({formatTime(total)})
              </button>
              <button type="button" className="btn" onClick={() => setOpen(false)}>Cancel</button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
