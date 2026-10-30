import { useEffect, useRef, useState } from "react";
import useApi from "../../api/useApi";
import Spinner from "../../components/ui/Spinner";
import { formatTime } from "../../utils/time";
import { clipMediaPath } from "./clips";
import { activeCueIndex, dragFraming, effectsFilter, frameSize } from "./playerMath";
import "./ClipPlayer.css";

const RATIOS = { "9:16": 9 / 16, "1:1": 1, "4:5": 4 / 5, "16:9": 16 / 9, "4:3": 4 / 3 };
const POSITIONS = { top: "flex-start", middle: "center", bottom: "flex-end" };

// "#000000" + opacity 0.5 -> "rgba(0, 0, 0, 0.5)"
function withOpacity(hex, opacity) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${opacity})`;
}

// Live preview of one clip with its edits: plays only the trimmed part (looping, unless you turn it off),
// in the chosen aspect-ratio frame, with the effects and captions drawn on top. The real render happens on Export.
// Space plays/pauses (when you're not typing).
//   clip  - { job_id, clip_index } ; info - { duration, width, height, cues } ; state - the draft
//   controlRef - optional useRef() from the page: gets { seek(t), getTime(), isReady() } so the timeline
//                can move the playhead and jump the video
//   framing    - optional { patch, recordUndo } from useClipDraft: in Fill mode you can then drag the video
//                to choose what stays in the frame (one undo step per drag)
function ClipPlayer({ projectId, clip, info, state, controlRef, framing }) {
  const api = useApi();
  const videoRef = useRef(null);
  const stageRef = useRef(null);
  const [url, setUrl] = useState(null);
  const [error, setError] = useState(null);
  const [time, setTime] = useState(state.start);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [loop, setLoop] = useState(true);
  const drag = useRef(null);        // the Fill-mode drag in progress
  const justDragged = useRef(false); // so letting go after a drag doesn't also play/pause
  const [stage, setStage] = useState({ width: 0, height: 0 });

  // Download the clip with the sign-in token (videos can't send it themselves)
  useEffect(() => {
    let active = true;
    let objectUrl = null;
    api.getMedia(clipMediaPath(projectId, clip))
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (active) setUrl(objectUrl);
      })
      .catch((err) => active && setError(err.message));
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [api, projectId, clip]);

  // Measure the space we have, so the frame can be as big as fits (and captions scale with it)
  useEffect(() => {
    const element = stageRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) =>
      setStage({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(element);
    return () => observer.disconnect();
  }, [url]);

  // The "remote control" the timeline uses
  useEffect(() => {
    if (!controlRef) return;
    controlRef.current = {
      seek: (t) => {
        if (videoRef.current) videoRef.current.currentTime = t;
        setTime(t);
      },
      getTime: () => videoRef.current?.currentTime ?? 0,
      isReady: () => Boolean(videoRef.current),
    };
    return () => {
      controlRef.current = null;
    };
  }, [controlRef]);

  // Space = play / pause (but not while typing or when a button has focus: Space already "clicks" those)
  useEffect(() => {
    function handleKey(event) {
      if (event.key !== " " || event.target.closest?.("input, textarea, select, button, [contenteditable]")) return;
      const video = videoRef.current;
      if (!video) return;
      event.preventDefault();
      if (video.paused) video.play();
      else video.pause();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  // Stay inside the trim: at the end, go back to the start (and keep playing only if Loop is on)
  function handleTimeUpdate() {
    const video = videoRef.current;
    if (video.currentTime >= state.end) {
      video.currentTime = state.start;
      if (!loop) video.pause();
    } else if (video.currentTime < state.start - 0.05) {
      video.currentTime = state.start;
    }
    setTime(video.currentTime);
  }

  // When the trim reaches the very end of the file, the browser stops the video by itself first
  function handleEnded() {
    const video = videoRef.current;
    video.currentTime = state.start;
    if (loop) video.play();
  }

  function togglePlay() {
    if (justDragged.current) {
      justDragged.current = false;
      return;
    }
    const video = videoRef.current;
    if (video.paused) video.play();
    else video.pause();
  }

  if (error) return <div className="clip-player-message" role="alert">{error}</div>;
  if (!url) return <div className="clip-player-message"><Spinner label="Loading clip" /> Loading clip…</div>;

  const { composition, captions } = state;
  const audioOnly = info.has_video === false;
  const ratio = audioOnly ? 16/9 : composition.ratio === "original" ? info.width / info.height : RATIOS[composition.ratio];
  const cueIndex = activeCueIndex(info.cues, time);
  const caption = cueIndex >= 0 ? state.texts?.[cueIndex] ?? info.cues[cueIndex].text : null;
  const outputHeight = Math.max(info.height, 1);
  const { width: frameWidth, height: frameHeight } = frameSize(stage, ratio);
  const canDrag = Boolean(framing) && !audioOnly && composition.mode === "fill";

  // ---------- Drag to reposition (Fill) ----------
  function startDrag(event) {
    if (!canDrag || event.button !== 0) return;
    drag.current = { x: event.clientX, y: event.clientY, from: { x: composition.x, y: composition.y }, before: state, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function moveDrag(event) {
    const current = drag.current;
    if (!current) return;
    const dx = event.clientX - current.x;
    const dy = event.clientY - current.y;
    if (!current.moved && Math.hypot(dx, dy) < 4) return; // a small wobble is still a click
    current.moved = true;
    const video = videoRef.current;
    const next = dragFraming(current.from, dx, dy, { width: frameWidth, height: frameHeight },
      { width: video.videoWidth, height: video.videoHeight });
    framing.patch((s) => ({ ...s, composition: { ...s.composition, ...next } }));
  }

  function endDrag() {
    const current = drag.current;
    drag.current = null;
    if (!current?.moved) return;
    framing.recordUndo(current.before);
    justDragged.current = true;
  }

  return (
    <div className="clip-player">
      <div ref={stageRef} className="clip-player-stage">
        <div className={`clip-player-frame${canDrag ? " can-drag" : ""}`}
          style={{ width: frameWidth, height: frameHeight, background: composition.background }}
          title={canDrag ? "Drag to choose what stays in the frame" : undefined}
          onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}>
          {audioOnly ? <>
            <p style={{textAlign:'center',padding:'2rem',color:'#f5f0de'}}>🎧 Audio recording</p>
            <audio ref={videoRef} src={url} muted={muted} aria-label="Edited audio preview"
              onLoadedMetadata={e => {e.target.currentTime=state.start;}}
              onTimeUpdate={handleTimeUpdate} onEnded={handleEnded} onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)} />
          </> : <video
            ref={videoRef}
            src={url}
            playsInline
            muted={muted}
            className="clip-player-video"
            style={{
              filter: effectsFilter(state.effects),
              objectFit: composition.mode === "fill" ? "cover" : "contain",
              objectPosition: `${composition.x * 100}% ${composition.y * 100}%`,
            }}
            onLoadedMetadata={(e) => (e.target.currentTime = state.start)}
            onTimeUpdate={handleTimeUpdate}
            onEnded={handleEnded}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onClick={togglePlay}
          />}
          {captions.enabled && caption && (
            <div className="clip-player-captions" style={{ justifyContent: POSITIONS[captions.position] }}>
              <span
                style={{
                  fontFamily: captions.font,
                  fontSize: `${(captions.size * frameHeight) / outputHeight}px`,
                  fontWeight: captions.bold ? 700 : 400,
                  color: captions.color,
                  background: withOpacity(captions.background, captions.opacity),
                  WebkitTextStroke: `${(captions.thickness * frameHeight) / outputHeight}px ${captions.stroke}`,
                  paintOrder: "stroke fill",
                }}
              >
                {caption}
              </span>
            </div>
          )}
        </div>
      </div>
      <div className="clip-player-bar">
        <button type="button" className="btn btn-small" onClick={togglePlay} aria-label={playing ? "Pause" : "Play"}>
          {playing ? "⏸" : "▶"}
        </button>
        <span className="clip-player-time">
          {formatTime(Math.max(0, time - state.start))} / {formatTime(state.end - state.start)}
        </span>
        <button type="button" className="btn btn-small btn-ghost" onClick={() => setMuted((m) => !m)}
          aria-pressed={muted} aria-label={muted ? "Unmute" : "Mute"} title={muted ? "Unmute" : "Mute"}>
          {muted ? "🔇" : "🔊"}
        </button>
        <button type="button" className={`btn btn-small btn-ghost clip-player-loop${loop ? " active" : ""}`}
          onClick={() => setLoop((l) => !l)} aria-pressed={loop} title={loop ? "Looping: on" : "Looping: off"}>
          🔁 Loop
        </button>
      </div>
    </div>
  );
}

export default ClipPlayer;
