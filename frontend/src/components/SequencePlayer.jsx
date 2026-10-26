import { useEffect, useRef, useState } from "react";
import "./SequencePlayer.css";
import playIcon from "../assets/icons/play-button.svg";
import { formatTime } from "../utils/time";

// Plays a list of clips from one source video, one after another.
//   sourceUrl         - the video file (null = demo project with no file yet)
//   clips             - [{ id, start, end }] in play order
//   currentIndex      - which clip is showing
//   onIndexChange(i)  - called when it moves to another clip
//   aspectRatio       - "16:9", "9:16" or "1:1": shape of the video screen
//   showProgress      - show the progress bar (Export page)
function SequencePlayer({ sourceUrl, clips, currentIndex = 0, onIndexChange, aspectRatio = "16:9", showProgress = false }) {
  const videoRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [clipTime, setClipTime] = useState(0);          // seconds into the current clip

  const clip = clips[currentIndex];
  const totalLength = clips.reduce((sum, c) => sum + (c.end - c.start), 0);
  const timeBefore = clips.slice(0, currentIndex).reduce((sum, c) => sum + (c.end - c.start), 0);
  const elapsed = timeBefore + clipTime;

  // When the clip changes, jump the video to that clip's start
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !clip) return;
    video.currentTime = clip.start;
    setClipTime(0);
  }, [clip]);

  function handleTimeUpdate() {
    const video = videoRef.current;
    if (!clip) return;
    if (video.currentTime >= clip.end) {
      if (currentIndex < clips.length - 1) {
        onIndexChange(currentIndex + 1);           // go on to the next clip
      } else {
        video.pause();                             // finished the last clip
        setIsPlaying(false);
        onIndexChange(0);
      }
      return;
    }
    setClipTime(Math.max(0, video.currentTime - clip.start));
  }

  function togglePlay() {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      video.play();
      setIsPlaying(true);
    } else {
      video.pause();
      setIsPlaying(false);
    }
  }

  // From the wireframe: clicking the video enlarges it to fill the screen
  function enlarge() {
    videoRef.current?.requestFullscreen?.();
  }

  const [w, h] = aspectRatio.split(":");

  return (
    <div className="seqplayer">
      <div className="seqplayer-stage">
        {sourceUrl && clip ? (
          <video
            ref={videoRef}
            className="seqplayer-video"
            style={{ aspectRatio: `${w} / ${h}` }}
            src={sourceUrl}
            playsInline
            onLoadedMetadata={(e) => { if (clip) e.target.currentTime = clip.start; }}
            onTimeUpdate={handleTimeUpdate}
            onClick={enlarge}
            title="Click to enlarge"
          />
        ) : (
          <div className="seqplayer-placeholder" style={{ aspectRatio: `${w} / ${h}` }}>
            {clips.length === 0 ? "No clips yet" : "Demo project: no video file yet"}
          </div>
        )}
      </div>

      <div className="seqplayer-controls">
        <button type="button" className="seqplayer-play" onClick={togglePlay} disabled={!sourceUrl} title={isPlaying ? "Pause" : "Play"}>
          {isPlaying ? <span className="seqplayer-pause">❚❚</span> : <img src={playIcon} alt="" />}
        </button>
        <span className="seqplayer-time">
          {formatTime(elapsed)} / {formatTime(totalLength)}
        </span>
        {showProgress && (
          <div className="seqplayer-track">
            <div className="seqplayer-fill" style={{ width: `${totalLength ? (elapsed / totalLength) * 100 : 0}%` }} />
          </div>
        )}
      </div>
    </div>
  );
}

export default SequencePlayer;
