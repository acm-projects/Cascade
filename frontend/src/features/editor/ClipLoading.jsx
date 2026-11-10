import "./ClipPlayer.css";

// What shows while a clip loads: a plain dark screen where the video is about to appear, so the page doesn't jump.
function ClipLoading() {
  return (
    <div className="clip-loading">
      <div className="clip-loading-screen" role="status">
        Loading clip…
      </div>
    </div>
  );
}

export default ClipLoading;
