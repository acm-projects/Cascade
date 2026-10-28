import { useEffect, useRef } from "react";
import { formatTime } from "../../utils/time";
import { moveEnd, moveStart, rulerStep, rulerTicks, timeToX, xToTime } from "./timelineMath";
import "./Timeline.css";

const pct = (t, duration) => `${timeToX(t, duration, 100)}%`; // a time as a % across the track

// "funny thing he said about the cat" -> "funny thing he said…"
function firstWords(text, count = 4) {
  const words = text.split(/\s+/);
  return words.length > count ? `${words.slice(0, count).join(" ")}…` : text;
}

// The Editor's timeline: the whole clip as a track, with
//  - two green handles to trim (one undo step per drag), the cut-off parts shaded
//  - a playhead that follows the video; click or drag on the track to jump/scrub
//  - a ruler, and one block per caption line (click to jump there)
//  - keyboard: "[" sets the start at the playhead, "]" sets the end
// Props:
//   duration, cues   - from the clip's info
//   state            - the draft ({ start, end, texts })
//   player           - the ClipPlayer's controlRef ({ seek(t), getTime() })
//   change, patch, recordUndo - from useClipDraft
//   focusedCue, onCueClick(index) - which caption block is highlighted
function Timeline({ duration, cues, state, player, change, patch, recordUndo, focusedCue, onCueClick }) {
  const trackRef = useRef(null);
  const playheadRef = useRef(null);
  const drag = useRef(null); // { kind: "start" | "end" | "playhead", before }
  const latest = useRef(state);
  useEffect(() => {
    latest.current = state;
  });

  // Move the playhead every animation frame (smooth, and no React re-render 60 times a second)
  useEffect(() => {
    let frame;
    const tick = () => {
      const t = player.current?.getTime() ?? 0;
      if (playheadRef.current) playheadRef.current.style.left = pct(t, duration);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [player, duration]);

  // "[" and "]" set the trim at the playhead (not while typing in a box)
  useEffect(() => {
    function handleKey(event) {
      if (event.target.closest?.("input, textarea, select, [contenteditable]")) return;
      if (event.key !== "[" && event.key !== "]") return;
      const t = player.current?.getTime() ?? 0;
      event.preventDefault();
      if (event.key === "[") change((s) => ({ ...s, start: moveStart(t, s.end, duration) }));
      else change((s) => ({ ...s, end: moveEnd(t, s.start, duration) }));
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [player, change, duration]);

  // Where on the track (in seconds) the mouse is
  function timeAt(event) {
    const box = trackRef.current.getBoundingClientRect();
    return xToTime(event.clientX - box.left, duration, box.width);
  }

  // Press: remember what we're dragging, and keep getting mouse events even off the element
  function startDrag(kind, event) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { kind, before: latest.current };
    moveDrag(event);
  }

  // Move: trim live with patch() (no undo step per pixel), and show that frame in the preview
  function moveDrag(event) {
    if (!drag.current) return;
    const t = timeAt(event);
    if (drag.current.kind === "start") {
      const start = moveStart(t, latest.current.end, duration);
      patch((s) => ({ ...s, start }));
      player.current?.seek(start);
    } else if (drag.current.kind === "end") {
      const end = moveEnd(t, latest.current.start, duration);
      patch((s) => ({ ...s, end }));
      player.current?.seek(end);
    } else {
      player.current?.seek(t);
    }
  }

  // Let go: the whole drag becomes ONE undo step
  function endDrag(event) {
    if (!drag.current) return;
    if (drag.current.kind !== "playhead") recordUndo(drag.current.before);
    if (drag.current.kind === "end") player.current?.seek(latest.current.start); // replay from the start
    drag.current = null;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
  }

  const dragProps = (kind) => ({
    onPointerDown: (event) => startDrag(kind, event),
    onPointerMove: moveDrag,
    onPointerUp: endDrag,
    onPointerCancel: endDrag,
  });

  const step = rulerStep(duration);
  const label = (t) => (step < 1 ? `${t.toFixed(step < 0.5 ? 2 : 1)}s` : formatTime(t));
  // Short clips need tenths of a second to be readable ("0.4s" instead of "0:00")
  const time = (t) => (duration < 10 ? `${t.toFixed(1)}s` : formatTime(t));

  return (
    <div className="timeline">
      <div className="timeline-ruler" aria-hidden="true">
        {rulerTicks(duration).map((t) => (
          <span key={t} className="timeline-tick" style={{ left: pct(t, duration) }}>{label(t)}</span>
        ))}
      </div>

      {/* Clicking or dragging anywhere on the track moves the playhead */}
      <div ref={trackRef} className="timeline-track" {...dragProps("playhead")}>
        <div className="timeline-cut" style={{ left: 0, width: pct(state.start, duration) }} />
        <div className="timeline-cut" style={{ left: pct(state.end, duration), right: 0 }} />
        <div className="timeline-kept" style={{ left: pct(state.start, duration), right: `${100 - timeToX(state.end, duration, 100)}%` }} />

        <button type="button" className="timeline-handle timeline-handle-start" style={{ left: pct(state.start, duration) }}
          aria-label={`Trim start: ${formatTime(state.start)}. Drag, or press [ at the playhead`} {...dragProps("start")} />
        <button type="button" className="timeline-handle timeline-handle-end" style={{ left: pct(state.end, duration) }}
          aria-label={`Trim end: ${formatTime(state.end)}. Drag, or press ] at the playhead`} {...dragProps("end")} />

        <div ref={playheadRef} className="timeline-playhead" {...dragProps("playhead")} />
      </div>

      <div className="timeline-cues">
        {cues.length === 0 && <span className="timeline-no-cues">No captions in this clip</span>}
        {cues.map((cue, index) => {
          const text = state.texts?.[index] ?? cue.text;
          return (
            <button key={index} type="button"
              className={`timeline-cue${index === focusedCue ? " active" : ""}`}
              style={{ left: pct(cue.start, duration), width: `${timeToX(cue.end - cue.start, duration, 100)}%` }}
              title={`${formatTime(cue.start)} – ${text}`}
              onClick={() => {
                player.current?.seek(cue.start);
                onCueClick?.(index);
              }}>
              {firstWords(text)}
            </button>
          );
        })}
      </div>

      <div className="timeline-footer">
        <span>Trim {time(state.start)} – {time(state.end)} · {time(state.end - state.start)} long</span>
        <span className="timeline-keys">Drag the green handles · click to jump · <kbd>[</kbd> <kbd>]</kbd> trim at playhead</span>
      </div>
    </div>
  );
}

export default Timeline;
