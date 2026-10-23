import { useRef } from "react";
import "./ClipCard.css";
import { formatTime } from "../utils/time";

// One generated clip. Hover to play that piece of the video, click to select it.
// The circle in the top-right corner shows whether it's selected (from the wireframe).
function ClipCard({ sourceUrl, start, end, isSelected, onToggle }) {
  const videoRef = useRef(null);

  function jumpToStart() {
    if (videoRef.current) videoRef.current.currentTime = start;
  }

  function loopWithinClip() {
    if (videoRef.current.currentTime >= end) jumpToStart();
  }

  return (
    <button
      type="button"
      className={`clipcard${isSelected ? " selected" : ""}`}
      onClick={onToggle}
      onMouseEnter={() => videoRef.current?.play()}
      onMouseLeave={() => { videoRef.current?.pause(); jumpToStart(); }}
    >
      <video
        ref={videoRef}
        className="clipcard-video"
        src={sourceUrl}
        muted
        playsInline
        onLoadedMetadata={jumpToStart}
        onTimeUpdate={loopWithinClip}
      />
      <span className="clipcard-check">{isSelected ? "✓" : ""}</span>
      <span className="clipcard-time">
        {formatTime(start)} – {formatTime(end)}
      </span>
    </button>
  );
}

export default ClipCard;
