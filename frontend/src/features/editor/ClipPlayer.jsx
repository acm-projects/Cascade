import { useEffect, useRef, useState } from "react";
import useApi from "../../api/useApi";
import Spinner from "../../components/ui/Spinner";
import { formatTime } from "../../utils/time";
import { clipMediaPath } from "./clips";
import "./ClipPlayer.css";

const RATIOS = { "9:16": 9 / 16, "1:1": 1, "4:5": 4 / 5, "16:9": 16 / 9, "4:3": 4 / 3 };
const POSITIONS = { top: "flex-start", middle: "center", bottom: "flex-end" };

// "#000000" + opacity 0.5 -> "rgba(0, 0, 0, 0.5)"
function withOpacity(hex, opacity) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${opacity})`;
}

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

  // Stay inside the trim: jump back to the start when the end is reached
  function handleTimeUpdate() {
    const video = videoRef.current;
    if (video.currentTime >= state.end || video.currentTime < state.start - 0.05) video.currentTime = state.start;
    setTime(video.currentTime);
  }

  function togglePlay() {
    const video = videoRef.current;
    if (video.paused) video.play();
    else video.pause();
  }

  if (error) return <div className="clip-player-message" role="alert">{error}</div>;
  if (!url) return <div className="clip-player-message"><Spinner label="Loading clip" /> Loading clip…</div>;

  const { composition, captions } = state;
  const audioOnly = info.has_video === false;
  const ratio = audioOnly ? 16/9 : composition.ratio === "original" ? info.width / info.height : RATIOS[composition.ratio];
  const cueIndex = info.cues.findIndex((cue) => cue.start <= time && time < cue.end);
  const caption = cueIndex >= 0 ? state.texts?.[cueIndex] ?? info.cues[cueIndex].text : null;
  const outputHeight = Math.max(info.height, 1);
  // The biggest frame of this shape that fits the space
  const frameWidth = Math.min(stage.width, stage.height * ratio);
  const frameHeight = frameWidth / ratio;

  return (
    <div className="clip-player">
      <div ref={stageRef} className="clip-player-stage">
        <div className="clip-player-frame" style={{ width: frameWidth, height: frameHeight, background: composition.background }}>
          {audioOnly ? <>
            <p style={{textAlign:'center',padding:'2rem',color:'#f5f0de'}}>🎧 Audio recording</p>
            <audio ref={videoRef} src={url} aria-label="Edited audio preview"
              onLoadedMetadata={e => {e.target.currentTime=state.start;}}
              onTimeUpdate={handleTimeUpdate} onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)} />
          </> : <video
            ref={videoRef}
            src={url}
            playsInline
            className="clip-player-video"
            style={{
              objectFit: composition.mode === "fill" ? "cover" : "contain",
              objectPosition: `${composition.x * 100}% ${composition.y * 100}%`,
            }}
            onLoadedMetadata={(e) => (e.target.currentTime = state.start)}
            onTimeUpdate={handleTimeUpdate}
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
      </div>
    </div>
  );
}

export default ClipPlayer;
