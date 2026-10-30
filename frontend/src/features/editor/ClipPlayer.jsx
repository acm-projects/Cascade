import { useEffect, useMemo, useRef, useState } from "react";
import useApi from "../../api/useApi";
import Spinner from "../../components/ui/Spinner";
import { formatTime } from "../../utils/time";
import { clipMediaPath } from "./clips";
import "./ClipPlayer.css";
import { timelineClock } from "./reelTiming";

const RATIOS = { "9:16": 9 / 16, "1:1": 1, "4:5": 4 / 5, "16:9": 16 / 9, "4:3": 4 / 3 };
// Live preview of one clip with its edits: plays only the trimmed part (looping), in the chosen
// aspect-ratio frame, with the captions drawn on top. The real render happens on Export.
//   clip  - { job_id, clip_index } ; info - { duration, width, height, cues } ; state - the draft
//   controlRef - optional useRef() from the page: gets { seek(t), getTime(), isReady() } so the timeline
//                can move the playhead and jump the video
function ClipPlayer({ projectId, clip, info, state, controlRef }) {
  const api = useApi();
  const videoRef = useRef(null);
  const stageRef = useRef(null);
  const [url, setUrl] = useState(null);
  const [rendered, setRendered] = useState(null);
  const [rendering, setRendering] = useState(false);
  const [renderError, setRenderError] = useState('');
  const [retry, setRetry] = useState(0);
  const [view, setView] = useState("edited");
  const clock = useMemo(() => timelineClock(state), [state]);
  const showEdited = view === "edited" && !!rendered;
  const advanced = true; // Edited always uses the same server renderer as MP4 export.
  const snapshot = JSON.stringify(state);
  useEffect(() => {
    let active = true, objectUrl;
    setRendered(null); setRenderError('');
    if (!advanced) { setRendering(false); return; }
    setRendering(true);
    const timer = setTimeout(() => {
      api.exportClip(projectId, clip.job_id, clip.clip_index, JSON.parse(snapshot)).then(blob => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob); setRendered(objectUrl);
      }).catch(e => { if (active) setRenderError(e.message); }).finally(() => { if (active) setRendering(false); });
    }, 900);
    return () => { active = false; clearTimeout(timer); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [api, projectId, clip.job_id, clip.clip_index, snapshot, advanced, retry]);
  const [error, setError] = useState(null);
  const [time, setTime] = useState(state.start);
  const [playing, setPlaying] = useState(false);
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
        if (videoRef.current) videoRef.current.currentTime = showEdited ? clock.output(t) : t;
        setTime(t);
      },
      getTime: () => showEdited ? clock.source(videoRef.current?.currentTime ?? 0) : (videoRef.current?.currentTime ?? 0),
      isReady: () => Boolean(videoRef.current),
    };
    return () => {
      controlRef.current = null;
    };
  }, [controlRef, showEdited, clock]);

  // Stay inside the trim: jump back to the start when the end is reached
  function handleTimeUpdate() {
    const video = videoRef.current;
    if (showEdited) { setTime(clock.source(video.currentTime)); return; }
    if (view === "original") { setTime(video.currentTime); return; }
    if (video.currentTime >= state.end || video.currentTime < state.start - 0.05) video.currentTime = state.start;
    setTime(video.currentTime);
  }

  function togglePlay() {
    const video = videoRef.current;
    if (video.paused) video.play().catch(e => setRenderError(e.message));
    else video.pause();
  }

  if (error) return <div className="clip-player-message" role="alert">{error}</div>;
  if (!url) return <div className="clip-player-message"><Spinner label="Loading clip" /> Loading clip…</div>;

  const { composition } = state;
  const audioOnly = info.has_video === false;
  const ratio = view === "original" ? info.width / info.height : audioOnly ? 16/9 : composition.ratio === "original" ? info.width / info.height : RATIOS[composition.ratio];
  // The biggest frame of this shape that fits the space
  const frameWidth = Math.min(stage.width, stage.height * ratio);
  const frameHeight = frameWidth / ratio;

  return (
    <div className="clip-player">
      <div className="editor-choice-row" role="tablist" aria-label="Preview version">
        {['original', 'edited'].map(mode => <button key={mode} role="tab" aria-selected={view === mode} className={`editor-choice${view === mode ? ' active' : ''}`} onClick={() => { videoRef.current?.pause(); setView(mode); }}>{mode === 'original' ? 'Original' : 'Edited'}</button>)}
      </div>
      <div ref={stageRef} className="clip-player-stage">
        <div className="clip-player-frame" style={{ width: frameWidth, height: frameHeight, background: composition.background }}>
          {audioOnly ? <>
            <p style={{textAlign:'center',padding:'2rem',color:'#f5f0de'}}>🎧 Audio recording</p>
            <audio ref={videoRef} src={showEdited ? rendered : url} aria-label="Edited audio preview"
              onLoadedMetadata={e => {e.target.currentTime=showEdited || view === "original" ? 0 : state.start;}}
              onTimeUpdate={handleTimeUpdate} onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)} />
          </> : <video
            ref={videoRef}
            src={showEdited ? rendered : url}
            playsInline
            className="clip-player-video"
            style={{
              objectFit: "contain",
              objectPosition: `${composition.x * 100}% ${composition.y * 100}%`,
            }}
            onLoadedMetadata={(e) => (e.target.currentTime = showEdited || view === "original" ? 0 : state.start)}
            onTimeUpdate={handleTimeUpdate}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onClick={togglePlay}
          />}

        </div>
      </div>
      {advanced && <div className="editor-control-note" role="status">{view === 'original' ? 'Original source · no edits' : rendering ? 'Rendering edited preview… Original source shown until ready.' : rendered ? 'Rendered preview · same audio/effects as MP4 export' : 'Edited preview unavailable.'}{renderError && <><span role="alert"> {renderError}</span><button className="editor-choice" onClick={() => setRetry(n => n + 1)}>Retry preview</button></>}</div>}
      <div className="clip-player-bar">
        <button type="button" className="btn btn-small" onClick={togglePlay} aria-label={playing ? "Pause" : "Play"}>
          {playing ? "⏸" : "▶"}
        </button>
        <span className="clip-player-time">
          {formatTime(showEdited ? clock.output(time) : time)} / {formatTime(view === "original" ? info.duration : clock.duration)}
        </span>
      </div>
    </div>
  );
}

export default ClipPlayer;
