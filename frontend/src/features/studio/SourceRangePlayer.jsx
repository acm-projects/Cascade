import { useEffect, useRef, useState } from "react";
import { formatTime } from "../../utils/time";

// Plays start–end of the original video as if it were the clip itself: it starts at `start`, stops at
// `end`, and its scrubber runs 0:00 → clip length. How the Studio shows every clip.
// The video streams (the browser fetches just the part it needs) instead of downloading first;
// the sign-in cookie goes along with the request.
function SourceRangePlayer({ src, start, end, audio = false }) {
  const media = useRef(null);
  const [at, setAt] = useState(0); // seconds into the clip
  const [playing, setPlaying] = useState(false);
  const length = Math.max(0, end - start);

  // Another clip (or the same video at another range): start it from the top
  useEffect(() => {
    setAt(0);
    const element = media.current;
    if (element && element.readyState >= 1) {
      element.currentTime = start;
      element.play().catch(() => {});
    }
  }, [src, start, end]);

  function onLoaded(event) {
    event.currentTarget.currentTime = start;
    event.currentTarget.play().catch(() => {}); // autoplay may be blocked: the play button still works
  }

  function onTime(event) {
    const element = event.currentTarget;
    if (element.currentTime >= end) {
      element.pause();
      element.currentTime = end;
    }
    setAt(Math.min(length, Math.max(0, element.currentTime - start)));
  }

  function toggle() {
    const element = media.current;
    if (!element) return;
    if (!element.paused) return element.pause();
    if (element.currentTime >= end - 0.05 || element.currentTime < start) element.currentTime = start;
    element.play().catch(() => {});
  }

  function seek(event) {
    const value = Number(event.target.value);
    setAt(value);
    if (media.current) media.current.currentTime = start + value;
  }

  const Tag = audio ? "audio" : "video";
  return (
    <div className="range-player">
      <Tag ref={media} className={audio ? "range-player-audio" : "studio-preview-video"} src={`${src}#t=${start},${end}`}
        preload="metadata" playsInline onLoadedMetadata={onLoaded} onTimeUpdate={onTime}
        onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onClick={toggle} />
      <div className="range-player-controls">
        <button type="button" className="btn btn-small" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
          {playing ? "❚❚" : "▶"}
        </button>
        <input type="range" min={0} max={length} step={0.1} value={at} onChange={seek} aria-label="Position in the clip" />
        <span className="range-player-time">{formatTime(at)} / {formatTime(length)}</span>
      </div>
    </div>
  );
}

export default SourceRangePlayer;
