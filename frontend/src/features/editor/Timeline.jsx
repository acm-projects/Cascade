import { useEffect, useRef, useState } from "react";
import { formatTime } from "../../utils/time";
import { filmstripFrameIndex, filmstripTileCount, moveEnd, moveStart, rulerStep, rulerTicks, timeToX, xToTime } from "./timelineMath";
import useFilmstrip from "./useFilmstrip";
import "./Timeline.css";
import BrollTrack from "./BrollTrack";
import Icon from "../../components/ui/Icon";
import { timelineClock } from "./reelTiming";

const pct = (t, duration) => `${timeToX(t, duration, 100)}%`; // a time as a % across the track

// "funny thing he said about the cat" -> "funny thing he said…"
function firstWords(text, count = 4) {
  const words = text.split(/\s+/);
  return words.length > count ? `${words.slice(0, count).join(" ")}…` : text;
}

// One row of the timeline: a labeled tag on the left (click it to open that tool), and its lane on the right.
function TrackRow({ kind, label, icon, onOpen, children }) {
  const name = <><Icon name={icon} size={16} /><span>{label}</span></>;
  return (
    <div className={`timeline-row timeline-row-${kind}`}>
      {onOpen ? (
        <button type="button" className="timeline-label" onClick={onOpen} title={`Open ${label}`}>{name}</button>
      ) : (
        <div className="timeline-label">{name}</div>
      )}
      {children}
    </div>
  );
}

// A lane of simple blocks (extra edits the AI or the tools added). Click a block to jump to it.
function BlockLane({ label, items, duration, player, onOpen }) {
  return (
    <div className="timeline-lane" aria-label={`${label} track`}>
      {items.map((item, i) => (
        <button key={item.id || i} type="button" className="timeline-block"
          style={{ left: pct(item.start, duration), width: pct(item.duration, duration) }}
          title={`${label} ${item.start.toFixed(2)}–${(item.start + item.duration).toFixed(2)}s`}
          onClick={() => { player.current?.seek(item.start); onOpen?.(); }}>
          {item.text || label}
        </button>
      ))}
    </div>
  );
}

// The Editor's timeline: stacked tracks like a video editor, top to bottom:
//   text, captions and B-roll (they sit on top of the video on screen), the video, then music and other edits.
//  - little video frames along the video track (a film strip, like CapCut)
//  - two green handles to trim (one undo step per drag), the cut-off parts shaded
//  - a playhead through every track that follows the video; click or drag on the ruler or video to jump/scrub
//  - one block per caption line (click to jump there)
//  - keyboard: "[" sets the start at the playhead, "]" sets the end
// Props:
//   projectId, clip, hasVideo - which clip to show frames from (no frames for audio recordings)
//   duration, cues   - from the clip's info
//   state            - the draft ({ start, end, texts })
//   player           - the ClipPlayer's controlRef ({ seek(t), getTime() })
//   change, patch, recordUndo - from useClipDraft
//   focusedCue, onCueClick(index) - which caption block is highlighted
//   onOpenTool(name)  - open a tool from its track: "Captions", "B-roll" or "Music"
function Timeline({ projectId, clip, hasVideo, duration, cues, state, player, change, patch, recordUndo, focusedCue, onCueClick, onOpenTool, selectedBroll, onSelectBroll, disabled }) {
  const trackRef = useRef(null);
  const playheadRef = useRef(null);
  const drag = useRef(null); // { kind: "start" | "end" | "playhead", before }
  const latest = useRef(state);
  useEffect(() => {
    latest.current = state;
  });

  const strip = useFilmstrip(projectId, clip, duration, hasVideo);
  const [trackSize, setTrackSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) =>
      setTrackSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(trackRef.current);
    return () => observer.disconnect();
  }, []);
  const tileCount = strip.frames.length ? filmstripTileCount(trackSize.width, trackSize.height, strip.aspect) : 0;

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
      if (disabled || event.target.closest?.("input, textarea, select, [contenteditable]")) return;
      if (event.key !== "[" && event.key !== "]") return;
      const t = player.current?.getTime() ?? 0;
      event.preventDefault();
      if (event.key === "[") change((s) => ({ ...s, start: moveStart(t, s.end, duration) }));
      else change((s) => ({ ...s, end: moveEnd(t, s.start, duration) }));
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [player, change, duration, disabled]);

  // Where on the track (in seconds) the mouse is
  function timeAt(event) {
    const box = trackRef.current.getBoundingClientRect();
    return xToTime(event.clientX - box.left, duration, box.width);
  }

  // Press: remember what we're dragging, and keep getting mouse events even off the element
  function startDrag(kind, event) {
    if (event.button !== 0 || (disabled && kind !== "playhead")) return;
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
    if (drag.current.kind !== "playhead") {
      if (event.type === "pointercancel") patch(drag.current.before);
      else recordUndo(drag.current.before);
    }
    if (drag.current.kind === "end") player.current?.seek(latest.current.start); // replay from the start
    drag.current = null;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  const dragProps = (kind) => ({
    onPointerDown: (event) => startDrag(kind, event),
    onPointerMove: moveDrag,
    onPointerUp: endDrag,
    onPointerCancel: endDrag,
    onLostPointerCapture: endDrag,
  });

  const step = rulerStep(duration);
  const label = (t) => (step < 1 ? `${t.toFixed(step < 0.5 ? 2 : 1)}s` : formatTime(t));
  // Short clips need tenths of a second to be readable ("0.4s" instead of "0:00")
  const time = (t) => (duration < 10 ? `${t.toFixed(1)}s` : formatTime(t));

  const music = (state.audio || []).filter((item) => item.track === "music");
  const soundEffects = (state.audio || []).filter((item) => item.track === "sfx");
  const textOverlays = state.text_overlays || [];
  // Extra lanes only appear once there's something on them
  const extraLanes = [
    ["sfx", "Sound effects", "volume", soundEffects],
    ["extra", "Kept footage", "scissors", (state.timeline || []).map((s) => ({ start: s.start, duration: s.end - s.start }))],
    ["extra", "Speed ramps", "repeat", (state.speed || []).map((s) => ({ start: s.start, duration: s.end - s.start }))],
    ["extra", "Zoom / shake", "target", state.motion || []],
    ["extra", "AI effects", "sparkles", (state.stylize?.events || []).map((e) => ({ ...e,
      text: e.kind === "text" ? `Text · ${e.text}` : e.kind === "title_card" ? "Edited by Cascade" : e.kind.replace("_", " ") }))],
  ].filter(([, , , items]) => items.length);

  return (
    <div className="timeline">
      <div className="timeline-row">
        <span />
        <div className="timeline-ruler" title="Click or drag to move the playhead" {...dragProps("playhead")}>
          {rulerTicks(duration).map((t) => (
            <span key={t} className="timeline-tick" style={{ left: pct(t, duration) }}>{label(t)}</span>
          ))}
        </div>
      </div>

      <div className="timeline-tracks">
        {textOverlays.length > 0 && (
          <TrackRow kind="text" label="Text" icon="pencil">
            <BlockLane label="Text" items={textOverlays} duration={duration} player={player} />
          </TrackRow>
        )}

        <TrackRow kind="captions" label="Captions" icon="captions" onOpen={() => onOpenTool?.("Captions")}>
          <div className="timeline-lane timeline-cues">
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
        </TrackRow>

        {hasVideo && (
          <TrackRow kind="broll" label="B-roll" icon="film" onOpen={() => onOpenTool?.("B-roll")}>
            <BrollTrack state={state} duration={duration} player={player} change={change} patch={patch}
              projectId={projectId} clip={clip} recordUndo={recordUndo} selectedId={selectedBroll} onSelect={onSelectBroll} disabled={disabled}
              onAdd={() => onOpenTool?.("B-roll")} />
          </TrackRow>
        )}

        <TrackRow kind="video" label={hasVideo ? "Video" : "Audio"} icon={hasVideo ? "play" : "headphones"}>
          {/* Clicking or dragging anywhere on the track moves the playhead */}
          <div ref={trackRef} className={`timeline-track${tileCount ? " has-filmstrip" : ""}`} {...dragProps("playhead")}>
            {tileCount > 0 && (
              <div className="timeline-filmstrip" aria-hidden="true">
                {Array.from({ length: tileCount }, (_, index) => {
                  const frame = strip.frames[filmstripFrameIndex(index, tileCount, strip.total)];
                  return frame ? <img key={index} src={frame} alt="" draggable="false" /> : <span key={index} />;
                })}
              </div>
            )}
            <div className="timeline-cut" style={{ left: 0, width: pct(state.start, duration) }} />
            <div className="timeline-cut" style={{ left: pct(state.end, duration), right: 0 }} />
            <div className="timeline-kept" style={{ left: pct(state.start, duration), right: `${100 - timeToX(state.end, duration, 100)}%` }} />

            <button type="button" className="timeline-handle timeline-handle-start" style={{ left: pct(state.start, duration) }}
              aria-label={`Trim start: ${formatTime(state.start)}. Drag, or press [ at the playhead`} {...dragProps("start")} />
            <button type="button" className="timeline-handle timeline-handle-end" style={{ left: pct(state.end, duration) }}
              aria-label={`Trim end: ${formatTime(state.end)}. Drag, or press ] at the playhead`} {...dragProps("end")} />
          </div>
        </TrackRow>

        <TrackRow kind="music" label="Music" icon="headphones" onOpen={() => onOpenTool?.("Music")}>
          {music.length ? (
            <BlockLane label="Music" items={music} duration={duration} player={player} />
          ) : (
            <div className="timeline-lane">
              <button type="button" className="timeline-add" onClick={() => onOpenTool?.("Music")}>
                <Icon name="plus" /> Add music
              </button>
            </div>
          )}
        </TrackRow>

        {extraLanes.map(([kind, name, icon, items]) => (
          <TrackRow key={name} kind={kind} label={name} icon={icon}>
            <BlockLane label={name} items={items} duration={duration} player={player}
              onOpen={name === "AI effects" ? () => onOpenTool?.("AI Editor") : undefined} />
          </TrackRow>
        ))}

        {/* The playhead runs through every track */}
        <div className="timeline-playhead-layer">
          <div ref={playheadRef} className="timeline-playhead" {...dragProps("playhead")} />
        </div>
      </div>

      <div className="timeline-footer">
        <span>Trim {time(state.start)} – {time(state.end)} · {time(timelineClock(state).duration)} long</span>
        <span className="timeline-keys">
          {selectedBroll ? "Drag to move · drag the edges to resize · Delete removes it"
            : <>Drag the green handles · click to jump · <kbd>[</kbd> <kbd>]</kbd> trim at playhead</>}
        </span>
      </div>
    </div>
  );
}

export default Timeline;
