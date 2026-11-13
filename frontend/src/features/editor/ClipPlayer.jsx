import { useEffect, useMemo, useRef, useState } from "react";
import useApi from "../../api/useApi";
import ClipLoading from "./ClipLoading";
import { formatTime } from "../../utils/time";
import { clipMediaPath } from "./clips";
import { dragFraming, frameSize } from "./playerMath";
import "./ClipPlayer.css";
import { timelineClock } from "./reelTiming";
import { ratioOf } from "./aspectRatios";
import useFramingPlan, { framingAt } from "./useFramingPlan";
import Icon from "../../components/ui/Icon";

// Live preview of one clip with its edits: plays only the trimmed part (looping), in the chosen
// aspect-ratio frame, with the captions drawn on top. The real render happens on Export.
//   clip  - { job_id, clip_index } ; info - { duration, width, height, cues } ; state - the draft
//   controlRef - optional useRef() from the page: gets { seek(t), getTime(), isReady() } so the timeline
//                can move the playhead and jump the video
//   framing    - optional { patch, recordUndo } from useClipDraft: in Fill mode you can then drag the video
//                to choose what stays in the frame (one undo step per drag)
//   onSourceMedia - optional: called with the source video URL once it loads (the timeline uses it for frames)
//   onOpenTrends, trendsOpen - optional: show a Trends button that opens the Trends popup
function ClipPlayer({ projectId, clip, info, state, controlRef, framing, onSourceMedia, onOpenTrends, trendsOpen, saveStatus }) {
  const api = useApi();
  const videoRef = useRef(null);
  const stageRef = useRef(null);
  const [url, setUrl] = useState(null);
  const [render, setRender] = useState(null); // { key, url } or { key, error } for the last finished server render
  const [retry, setRetry] = useState(0);
  const [view, setView] = useState("edited");
  const [cutout, setCutout] = useState(null);
  // A finished AI edit is its own film: its file sets the clock, not the source timeline.
  const aiDuration = state.ai_edit?.duration;
  const clock = useMemo(() => aiDuration ? { duration: aiDuration, output: t => t, source: t => t } : timelineClock(state), [state, aiDuration]);
  const styled = Boolean(state.stylize?.events?.length);
  const advanced = true; // Edited always uses the same server renderer as MP4 export.
  const snapshot = JSON.stringify(state);
  // The render for the current edit (+ retry count). An older render's result is ignored, so
  // "rendering" is simply: the last finished render isn't this one yet.
  const renderKey = `${retry}:${snapshot}`;
  const current = render?.key === renderKey ? render : null;
  const rendered = current?.url ?? null;
  const renderError = current?.error ?? '';
  const rendering = advanced && !current;
  const showEdited = view === "edited" && !!rendered;
  // Until the server's render of this exact edit arrives, the shape is shown instantly by cropping the video itself
  const cropNow = view === "edited" && !showEdited && state.composition.mode === "fill";
  // Fan-edit previews first compute subject cutouts locally; show that progress while rendering.
  useEffect(() => {
    if (!rendering || !styled) return;
    let active = true;
    const poll = () => api.getStyleProgress(projectId, clip.job_id, clip.clip_index)
      .then(p => { if (active) setCutout(p?.total ? p : null); }).catch(() => {});
    const timer = setInterval(poll, 2000);
    const first = setTimeout(poll, 0);
    return () => { active = false; clearInterval(timer); clearTimeout(first); setCutout(null); };
  }, [api, projectId, clip.job_id, clip.clip_index, rendering, styled]);
  useEffect(() => {
    if (!advanced) return;
    let active = true, objectUrl;
    const timer = setTimeout(() => {
      api.exportClip(projectId, clip.job_id, clip.clip_index, { ...JSON.parse(snapshot), preview: true, resolution: '540p' }).then(blob => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob); setRender({ key: renderKey, url: objectUrl });
      }).catch(e => { if (active) setRender({ key: renderKey, error: e.message }); });
    }, 900);
    return () => { active = false; clearTimeout(timer); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [api, projectId, clip.job_id, clip.clip_index, snapshot, advanced, renderKey]);
  const [error, setError] = useState(null);
  const [time, setTime] = useState(state.start);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [loop, setLoop] = useState(true);
  const drag = useRef(null);        // the Fill-mode drag in progress
  const justDragged = useRef(false); // so letting go after a drag doesn't also play/pause
  const [stage, setStage] = useState({ width: 0, height: 0 });
  const [fileShape, setFileShape] = useState(null); // an AI edit's own width / height, once its file has loaded
  const framingPlan = useFramingPlan(projectId, clip, state, info);

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

  useEffect(() => { onSourceMedia?.(url); }, [url, onSourceMedia]);

  // The "remote control" the timeline uses
  useEffect(() => {
    if (!controlRef) return;
    controlRef.current = {
      seek: (t) => {
        if (videoRef.current) videoRef.current.currentTime = showEdited ? clock.output(t) : t;
        setTime(t);
      },
      getTime: () => showEdited ? clock.source(videoRef.current?.currentTime ?? 0) : (videoRef.current?.currentTime ?? 0),
      isReady: () => Boolean(videoRef.current),
      isPlaying: () => Boolean(videoRef.current && !videoRef.current.paused),
      togglePlay: () => {
        const video = videoRef.current;
        if (!video) return;
        if (video.paused) video.play().catch(() => {}); else video.pause();
      },
    };
    return () => {
      controlRef.current = null;
    };
  }, [controlRef, showEdited, clock]);

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
    if (showEdited) { setTime(clock.source(video.currentTime)); return; }
    if (view === "original") { setTime(video.currentTime); return; }
    if (video.currentTime >= state.end || video.currentTime < state.start - 0.05) video.currentTime = state.start;
    setTime(video.currentTime);
  }

  // When the trim reaches the very end of the file, the browser stops the video by itself first
  function handleEnded() {
    const video = videoRef.current;
    video.currentTime = showEdited || view === "original" ? 0 : state.start;
    if (loop) video.play();
  }

  function togglePlay() {
    if (justDragged.current) {
      justDragged.current = false;
      return;
    }
    const video = videoRef.current;
    if (video.paused) video.play().catch(e => setRenderError(e.message));
    else video.pause();
  }

  // Instant Fill preview that follows the speaker: move the crop with the video's clock
  useEffect(() => {
    const video = videoRef.current;
    if (!cropNow || !framingPlan || !video) return undefined;
    let frame = 0;
    const move = () => {
      const at = framingAt(framingPlan, video.currentTime);
      if (at) video.style.objectPosition = `${at.x * 100}% ${at.y * 100}%`;
      frame = requestAnimationFrame(move);
    };
    frame = requestAnimationFrame(move);
    return () => { cancelAnimationFrame(frame); video.style.objectPosition = ""; };
  }, [cropNow, framingPlan, url]);

  if (error) return <div className="clip-player-message" role="alert">{error.message || error}</div>;
  if (!url) return <ClipLoading />;

  const { composition } = state;
  const audioOnly = info.has_video === false;
  const aiShape = composition.ratio !== "original" ? ratioOf(composition.ratio) : fileShape || 9 / 16;
  const ratio = view === "original" ? info.width / info.height : state.ai_edit ? aiShape : audioOnly ? 16/9 : state.fablecut?.ratio === '9:16' ? 9/16 : composition.ratio === "original" ? info.width / info.height : ratioOf(composition.ratio);
  // The biggest frame of this shape that fits the space
  const { width: frameWidth, height: frameHeight } = frameSize(stage, ratio);

  const canDrag = Boolean(framing) && !audioOnly && !state.fablecut && view === "edited" && composition.mode === "fill";

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

  const versionControls = (
      <div className="clip-player-version-controls">
      {saveStatus && <div className="clip-player-save-status">{saveStatus}</div>}
      <div className="editor-choice-row" role="tablist" aria-label="Preview version">
        {['original', 'edited'].map(mode => <button key={mode} role="tab" aria-selected={view === mode} className={`editor-choice${view === mode ? ' active' : ''}`} onClick={() => { videoRef.current?.pause(); setView(mode); }}>{mode === 'original' ? 'Original' : 'Edited'}</button>)}
      </div>

      </div>
  );

  return (
    <div className="clip-player">
      {!saveStatus && versionControls}
      {onOpenTrends && <button type="button" className="editor-choice clip-player-trends"
        aria-haspopup="dialog" aria-expanded={trendsOpen} onClick={onOpenTrends}>Trends</button>}
      <div ref={stageRef} className="clip-player-stage">
        <div className={`clip-player-frame${canDrag ? " can-drag" : ""}`}
          style={{ width: frameWidth, height: frameHeight, background: composition.background }}
          title={canDrag ? "Drag to choose what stays in the frame" : undefined}
          onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}>
          {audioOnly ? <>
            <p style={{textAlign:'center',padding:'2rem',color:'#f5f0de'}}><Icon name="headphones" /> Audio recording</p>
            <audio muted={muted} onEnded={handleEnded} ref={videoRef} src={showEdited ? rendered : url} aria-label="Edited audio preview"
              onError={() => setError(new Error("Unable to load the preview. Please try again."))}
              onLoadedMetadata={e => {e.target.currentTime=showEdited || view === "original" ? 0 : state.start;}}
              onTimeUpdate={handleTimeUpdate} onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)} />
          </> : <video
            ref={videoRef}
            src={showEdited ? rendered : url}
            playsInline
            muted={muted}
            className="clip-player-video"
            style={{
              objectFit: cropNow ? "cover" : "contain",
              objectPosition: `${composition.x * 100}% ${composition.y * 100}%`,
            }}
            onLoadedMetadata={(e) => { if (state.ai_edit && e.target.videoWidth) setFileShape(e.target.videoWidth / e.target.videoHeight); e.target.currentTime = showEdited || view === "original" ? 0 : state.start; }}
            onError={() => setError(new Error("Unable to load the preview. Please try again."))}
            onTimeUpdate={handleTimeUpdate}
            onEnded={handleEnded}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onClick={togglePlay}
          />}
        </div>
      </div>
      {advanced && <div className="editor-control-note" role="status">{view === 'original' ? 'Original source · no edits' : rendering ? (cutout ? `Fan-edit effects: cutting out the subject ${cutout.done}/${cutout.total} frames (first time only)… Original source shown until ready.` : styled ? 'Rendering fan-edit effects… Original source shown until ready.' : 'Rendering edited preview… Original source shown until ready.') : rendered ? (state.ai_edit ? `AI edit ${state.ai_edit.version} · this exact file is what Export saves` : 'Rendered preview · same audio/effects as MP4 export') : 'Edited preview unavailable.'}{renderError && <><span role="alert"> {renderError}</span><button className="editor-choice" onClick={() => setRetry(n => n + 1)}>Retry preview</button></>}</div>}
      <div className="clip-player-bar">
        <button type="button" className="btn btn-small" onClick={togglePlay} aria-label={playing ? "Pause" : "Play"}>
          <Icon name={playing ? "pause" : "play"} />
        </button>
        <span className="clip-player-time">
          {formatTime(showEdited ? clock.output(time) : time)} / {formatTime(view === "original" ? info.duration : clock.duration)}
        </span>
        <button type="button" className="btn btn-small btn-ghost" onClick={() => setMuted((m) => !m)}
          aria-pressed={muted} aria-label={muted ? "Unmute" : "Mute"} title={muted ? "Unmute" : "Mute"}>
          <Icon name={muted ? "mute" : "volume"} />
        </button>
        <button type="button" className={`btn btn-small btn-ghost clip-player-loop${loop ? " active" : ""}`}
          onClick={() => setLoop((l) => !l)} aria-pressed={loop} title={loop ? "Looping: on" : "Looping: off"}>
          <Icon name="repeat" /> Loop
        </button>
        {saveStatus && versionControls}
      </div>
    </div>
  );
}

export default ClipPlayer;
