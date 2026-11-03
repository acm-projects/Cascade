import { useEffect, useRef, useState } from "react";
import { formatTime } from "../../utils/time";
import { moveEnd, moveStart, rulerStep, timeToX, xToTime } from "./timelineMath";
import "./Timeline.css";
import BrollTrack from "./BrollTrack";
import { Filmstrip, AudioWaveform } from "./TimelineMedia";
import { layoutLanes } from "./timelineLayout";
import { timelineClock } from "./reelTiming";

const pct = (t, duration) => `${timeToX(t, duration, 100)}%`; // a time as a % across the track

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
function Timeline({ duration, cues, state, player, change, patch, recordUndo, focusedCue, onCueClick, selectedBroll, onSelectBroll, disabled, projectId, clip, sourceUrl, hasVideo = true, onTrackClick }) {
  const trackRef = useRef(null);
  const scrollRef = useRef(null);
  const timeRef = useRef(null);
  const playButtonRef = useRef(null);
  const [zoom, setZoom] = useState(1);
  const [viewport, setViewport] = useState(600);
  const [expanded, setExpanded] = useState({});
  const [selection, setSelection] = useState('video');
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setViewport(Math.max(1, entry.contentRect.width)));
    observer.observe(scrollRef.current);
    return () => observer.disconnect();
  }, []);
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
      if (playheadRef.current) {
        playheadRef.current.style.left = pct(t, duration);
        playheadRef.current.setAttribute('aria-valuenow', t.toFixed(2));
      }
      if (timeRef.current) timeRef.current.textContent = `${formatTime(t)} / ${formatTime(duration)}`;
      if (playButtonRef.current) {
        const playing = player.current?.isPlaying?.() || false;
        playButtonRef.current.textContent = playing ? 'Ⅱ Pause' : '▶ Play';
        playButtonRef.current.setAttribute('aria-label', playing ? 'Pause timeline playback' : 'Play timeline playback');
      }
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
    if (kind !== "playhead") setSelection("video");
    event.preventDefault();
    event.stopPropagation();
    if (kind !== "playhead" || event.currentTarget === playheadRef.current) event.currentTarget.focus({ preventScroll: true });
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
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  const dragProps = (kind) => ({
    onPointerDown: (event) => startDrag(kind, event),
    onPointerMove: moveDrag,
    onPointerUp: endDrag,
    onPointerCancel: endDrag,
    onLostPointerCapture: endDrag,
  });

  const visibleDuration = duration / zoom;
  const step = rulerStep(visibleDuration);
  const ruler = Array.from({ length: Math.min(1000, Math.ceil(duration / step)) }, (_, i) => i * step);
  const label = t => step < 1 ? `${t.toFixed(step < .5 ? 2 : 1)}s` : formatTime(t);
  const time = t => `${t.toFixed(2)}s`;
  const captionLayout = layoutLanes(cues.map((cue, index) => ({ ...cue, index, duration: cue.end - cue.start })));
  const music = layoutLanes((state.audio || []).filter(item => item.track === 'music'));
  const effects = layoutLanes([
    ...(state.speed || []).map(item => ({ ...item, duration: item.end - item.start, name: 'Speed', panel: 'Reel' })),
    ...(state.motion || []).map(item => ({ ...item, name: item.type || 'Motion', panel: 'Reel' })),
    ...(state.text_overlays || []).map(item => ({ ...item, name: item.text || 'Text', panel: 'Reel' })),
    ...(state.audio || []).filter(item => item.track === 'sfx').map(item => ({ ...item, name: 'Sound effect', panel: 'Music' })),
    ...(state.stylize?.events || []).map(item => ({ ...item, name: item.kind === 'text' ? `Text · ${item.text}` : item.kind === 'title_card' ? 'Edited by Cascade' : item.kind.replace('_', ' '), panel: 'AI Editor' })),
  ]);
  const rows = [
    { id: 'video', name: hasVideo ? 'Video' : 'Source', height: 76 },
    { id: 'captions', name: 'Captions', height: cues.length ? captionLayout.lanes * 30 + 14 : 36 },
    { id: 'broll', name: 'B-roll', count: (state.broll || []).length, height: 60 },
    { id: 'music', name: 'Music', count: music.items.length, height: music.lanes * 50 + 12 },
    { id: 'effects', name: 'Effects', count: effects.items.length, height: effects.lanes * 32 + 12 },
  ].map(row => {
    // B-roll, Music and Effects are dropdowns: closed until someone opens them.
    const collapsed = row.count !== undefined && !expanded[row.id];
    return { ...row, collapsed, height: collapsed ? 28 : row.height };
  });
  const position = item => ({ left: pct(item.start, duration), width: pct(item.duration, duration) });
  const currentCue = cues[focusedCue];
  function changeZoom(next) {
    const scroll = scrollRef.current;
    const anchor = scroll.scrollLeft / (viewport * zoom);
    const value = Math.max(1, Math.min(8, Math.round(next * 4) / 4));
    setZoom(value);
    requestAnimationFrame(() => { scroll.scrollLeft = anchor * viewport * value; });
  }

  return (
    <div className="timeline">
      <div className="timeline-toolbar" role="toolbar" aria-label="Timeline controls">
        <button ref={playButtonRef} type="button" onClick={() => player.current?.togglePlay?.()} aria-label="Play timeline playback">▶ Play</button>
        <output ref={timeRef} className="timeline-time" aria-label="Source position and duration">{formatTime(state.start)} / {formatTime(duration)}</output>
        <span className="timeline-clock-label">Source time</span>
        <div className="timeline-zoom">
          <button type="button" aria-label="Zoom out timeline" disabled={zoom <= 1} onClick={() => changeZoom(Math.max(1, zoom / 1.5))}>−</button>
          <label>Zoom <input aria-label="Timeline zoom" type="range" min="1" max="8" step=".25" value={zoom} onChange={event => changeZoom(Number(event.target.value))} /></label>
          <button type="button" aria-label="Zoom in timeline" disabled={zoom >= 8} onClick={() => changeZoom(Math.min(8, zoom * 1.5))}>+</button>
          <button type="button" onClick={() => { setZoom(1); scrollRef.current.scrollLeft = 0; }}>Fit timeline</button>
        </div>
      </div>
      <div className="timeline-board">
        <div className="timeline-labels">
          <div className="timeline-label timeline-label-ruler">TRACKS</div>
          {rows.map(row => <div key={row.id} className={`timeline-label${row.collapsed ? ' collapsed' : ''}`} style={{ height: row.height }}>
            {row.count !== undefined ? <button type="button" aria-expanded={!row.collapsed} aria-label={`${row.collapsed ? 'Show' : 'Hide'} ${row.name} track`} onClick={() => setExpanded(all => ({ ...all, [row.id]: !all[row.id] }))}>{row.collapsed ? '▸' : '▾'} {row.name}{row.count ? ` (${row.count})` : ''}</button> : <span>{row.name}</span>}
          </div>)}
        </div>
        <div ref={scrollRef} className="timeline-scroll" tabIndex="0" aria-label="Scrollable timeline">
          <div ref={trackRef} className="timeline-content" style={{ width: viewport * zoom }}>
            <div className="timeline-ruler" {...dragProps('playhead')} aria-label="Time ruler; drag to seek">
              {ruler.map(t => <span key={t} className="timeline-tick" style={{ left: pct(t, duration) }}>{label(t)}</span>)}
            </div>
            {rows.map(row => <div key={row.id} className={`timeline-row timeline-row-${row.id}${row.collapsed ? ' collapsed' : ''}`} style={{ height: row.height }} aria-label={`${row.name} track`} {...dragProps('playhead')}>
              {row.collapsed ? <span className="timeline-empty">{row.count ? `${row.count} ${row.name.toLowerCase()} item${row.count === 1 ? '' : 's'} · open ▸ ${row.name} to view` : `No ${row.name.toLowerCase()} added`}</span> : row.id === 'video' ? <>
                <div className={`timeline-track${selection === 'video' ? ' active' : ''}`} onPointerDown={event => { setSelection('video'); startDrag('playhead', event); }}>
                  <Filmstrip key={`${sourceUrl}:${duration}`} url={sourceUrl} duration={duration} hasVideo={hasVideo} />
                  <div className="timeline-cut" style={{ left: 0, width: pct(state.start, duration) }} />
                  <div className="timeline-cut" style={{ left: pct(state.end, duration), right: 0 }} />
                  <div className="timeline-kept" style={{ left: pct(state.start, duration), width: pct(state.end - state.start, duration) }} />
                  {(state.timeline || []).map((span, i) => <div key={i} className="timeline-footage-span" title={`Kept footage ${time(span.start)}–${time(span.end)}`} style={position({ start: span.start, duration: span.end - span.start })} />)}
                  <button type="button" className="timeline-handle timeline-handle-start" style={{ left: pct(state.start, duration) }} disabled={disabled}
                    aria-label={`Trim start: ${time(state.start)}. Drag, or press [ at the playhead`} {...dragProps('start')}
                    onKeyDown={event => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); change(s => ({ ...s, start: moveStart(s.start + (event.key === 'ArrowLeft' ? -.1 : .1), s.end, duration) })); } }} />
                  <button type="button" className="timeline-handle timeline-handle-end" style={{ left: pct(state.end, duration) }} disabled={disabled}
                    aria-label={`Trim end: ${time(state.end)}. Drag, or press ] at the playhead`} {...dragProps('end')}
                    onKeyDown={event => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); change(s => ({ ...s, end: moveEnd(s.end + (event.key === 'ArrowLeft' ? -.1 : .1), s.start, duration) })); } }} />
                </div>
              </> : row.id === 'captions' ? <>
                {!cues.length && <span className="timeline-empty">No captions in this clip</span>}
                {captionLayout.items.map(cue => {
                  const text = state.texts?.[cue.index] ?? cue.text;
                  return <button key={cue.index} type="button" className={`timeline-cue${cue.index === focusedCue ? ' active' : ''}`} style={{ ...position(cue), top: 7 + cue.lane * 30 }}
                    title={`${time(cue.start)} – ${time(cue.end)} · ${text}`} aria-label={`Caption ${cue.index + 1}: ${text}`} aria-pressed={cue.index === focusedCue}
                    onPointerDown={event => event.stopPropagation()} onClick={() => { player.current?.seek(cue.start); onCueClick?.(cue.index); setSelection('captions'); }}><span>{text}</span></button>;
                })}
              </> : row.id === 'broll' ? <BrollTrack state={state} duration={duration} player={player} change={change} patch={patch} recordUndo={recordUndo}
                projectId={projectId} clip={clip} selectedId={selectedBroll} onSelect={onSelectBroll} disabled={disabled} />
                : row.id === 'music' ? <>
                  {!music.items.length && <span className="timeline-empty">Add music in the Music panel</span>}
                  {music.items.map(item => <button type="button" key={item.id} className={`timeline-audio${selection === item.id ? ' active' : ''}`} style={{ ...position(item), top: 6 + item.lane * 50 }} title="Music · source waveform before mixing"
                    onPointerDown={event => event.stopPropagation()} onClick={() => { setSelection(item.id); player.current?.seek(item.start); onTrackClick?.('Music'); }}>
                    <AudioWaveform key={item.asset_id} projectId={projectId} clip={clip} segment={item} /><span>Music · {time(item.duration)}</span>
                  </button>)}
                </> : <>
                  {!effects.items.length && <span className="timeline-empty">No effects added</span>}
                  {effects.items.map((item, i) => <button type="button" key={item.id || i} className={`timeline-cue timeline-effect${selection === `effect-${i}` ? ' active' : ''}`} style={{ ...position(item), top: 6 + item.lane * 32 }} title={`${item.name} · ${time(item.start)}–${time(item.start + item.duration)}`}
                    onPointerDown={event => event.stopPropagation()} onClick={() => { setSelection(`effect-${i}`); player.current?.seek(item.start); onTrackClick?.(item.panel); }}><span>{item.name}</span></button>)}
                </>}
            </div>)}
            <div ref={playheadRef} className="timeline-playhead" role="slider" tabIndex="0" aria-label="Scrub source playhead" aria-valuemin={0} aria-valuemax={duration}
              {...dragProps('playhead')} onKeyDown={event => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); player.current?.seek(Math.max(0, Math.min(duration, (player.current?.getTime() || 0) + (event.key === 'ArrowLeft' ? -1 : 1) * (event.shiftKey ? 1 : .1)))); } }} />
          </div>
        </div>
      </div>
      {selection === 'captions' && currentCue && <p className="timeline-caption-detail">{state.texts?.[focusedCue] ?? currentCue.text}</p>}
      <div className="timeline-footer">
        <span>Trim {time(state.start)} – {time(state.end)} · edited {time(timelineClock(state).duration)}</span>
        <span>Drag handles to trim · <kbd>[</kbd> <kbd>]</kbd> at playhead · B-roll: drag / Delete</span>
      </div>
    </div>
  );
}

export default Timeline;
