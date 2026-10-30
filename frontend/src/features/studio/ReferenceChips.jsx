import { sameRef } from "./graph";

// The picked clips of this session, as chips above the chat box. Picked clips guide the next prompt
// ("more like these"); click a chip to leave that clip out of this prompt (it stays picked for the Editor).
// Hovering a chip makes its clip glow on the canvas.
//   chips     - [{ ref, label: "P1 · Clip 2", title }]
//   leftOut   - refs the user switched off for this prompt
//   onToggle(ref), onHover(ref | null)
function ReferenceChips({ chips, leftOut, onToggle, onHover }) {
  if (chips.length === 0) return null;
  return (
    <div className="reference-chips" aria-label="Picked clips that guide this prompt">
      {chips.map(({ ref, label, title }) => {
        const on = !leftOut.some((item) => sameRef(item, ref));
        return (
          <button key={`${ref.job_id}:${ref.clip_index}`} type="button" aria-pressed={on}
            className={`reference-chip${on ? " is-on" : ""}`} title={on ? "Guides this prompt. Click to leave it out." : "Left out. Click to use it."}
            onClick={() => onToggle(ref)} onMouseEnter={() => onHover(ref)} onMouseLeave={() => onHover(null)}
            onFocus={() => onHover(ref)} onBlur={() => onHover(null)}>
            {on ? "🌿" : "○"} {label}{title ? ` · ${title}` : ""}
          </button>
        );
      })}
    </div>
  );
}

export default ReferenceChips;
