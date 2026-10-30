import { useEffect, useRef } from "react";
import { dragBroll } from "./brollTiming";

export default function BrollTrack({ state, duration, player, change, patch, recordUndo, selectedId, onSelect, disabled }) {
  const track = useRef(null);
  const drag = useRef(null);
  const latest = useRef(state);
  useEffect(() => { latest.current = state; });

  // Delete only the selected stock segment, never text being edited in an input.
  useEffect(() => {
    function remove(event) {
      if (disabled || !selectedId || event.defaultPrevented || event.target.closest?.("input, textarea, select, [contenteditable]")) return;
      if (event.key !== "Delete" && event.key !== "Backspace") return;
      if (!latest.current.broll.some(s => s.id === selectedId)) return;
      event.preventDefault();
      change(s => ({ ...s, broll: s.broll.filter(item => item.id !== selectedId) }));
      onSelect(null);
    }
    window.addEventListener("keydown", remove);
    return () => window.removeEventListener("keydown", remove);
  }, [change, selectedId, onSelect, disabled]);

  function begin(event, segment, kind) {
    if (disabled || event.button !== 0) return;
    event.preventDefault(); event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { before: latest.current, segment, kind, x: event.clientX, width: track.current.getBoundingClientRect().width };
    onSelect(segment.id); player.current?.seek(segment.start + .001);
  }
  function move(event) {
    if (!drag.current) return;
    const { before, segment, kind, x, width } = drag.current;
    const moved = dragBroll(segment, kind, (event.clientX - x) * duration / width, before.broll, duration);
    patch({ ...before, broll: before.broll.map(s => s.id === segment.id ? moved : s) });
  }
  function finish(event) {
    if (!drag.current) return;
    if (event.type === 'pointercancel') patch(drag.current.before);
    else recordUndo(drag.current.before);
    drag.current = null;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
  }
  function nudge(event, segment, kind) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const delta = (event.key === 'ArrowLeft' ? -1 : 1) * (event.shiftKey ? 1 : .1);
    const moved = dragBroll(segment, kind, delta, state.broll, duration);
    change({ ...state, broll: state.broll.map(s => s.id === segment.id ? moved : s) });
    onSelect(segment.id);
  }
  const props = (segment, kind) => ({
    disabled, onPointerDown: e => begin(e, segment, kind), onPointerMove: move,
    onPointerUp: finish, onPointerCancel: finish, onKeyDown: e => nudge(e, segment, kind),
    onClick: () => { onSelect(segment.id); player.current?.seek(segment.start + .001); },
  });
  return <div className="timeline-broll" aria-label="B-roll track">
    <small>B-roll · drag to move, edges to trim · Delete removes selection</small>
    <div ref={track} className="timeline-broll-lane">
      {state.broll.map((segment, index) => <div key={segment.id} className={`timeline-broll-segment${segment.id === selectedId ? ' active' : ''}`}
        style={{ left: `${segment.start / duration * 100}%`, width: `${segment.duration / duration * 100}%` }}>
        <button type="button" className="timeline-broll-body" aria-pressed={segment.id === selectedId}
          aria-label={`B-roll ${index + 1}, ${segment.start.toFixed(2)} to ${(segment.start + segment.duration).toFixed(2)} seconds`} {...props(segment,'move')}>B-roll {index + 1}</button>
        <button type="button" className="timeline-broll-edge start" aria-label={`Resize start of B-roll ${index + 1}`} {...props(segment,'start')} />
        <button type="button" className="timeline-broll-edge end" aria-label={`Resize end of B-roll ${index + 1}`} {...props(segment,'end')} />
      </div>)}
      {!state.broll.length && <small className="timeline-no-cues">No B-roll yet</small>}
    </div>
  </div>;
}
