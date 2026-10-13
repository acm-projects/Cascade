import { useRef } from "react";
import { Link } from "react-router-dom";
import "./LandingVideo.css";

const START = 1; // seconds: where the loop begins
const END = 3;   // seconds: where it jumps back to START

function LandingVideo() {
  const videoRef = useRef(null);

  // When the video first loads, skip ahead to START
  function handleLoaded() {
    videoRef.current.currentTime = START;
  }

  // While playing, if we've passed END, jump back to START
  function handleTimeUpdate() {
    if (videoRef.current.currentTime >= END) {
      videoRef.current.currentTime = START;
    }
  }

  return (
    <div className="landing-video">
      <video
        ref={videoRef}
        className="landing-video-player"
        src="/landing.mp4"
        autoPlay
        muted
        playsInline
        onLoadedMetadata={handleLoaded}
        onTimeUpdate={handleTimeUpdate}
      />
      <Link to="/projects" className="wood-button landing-start">
        Get Started
      </Link>
    </div>
  );
}

export default LandingVideo;
