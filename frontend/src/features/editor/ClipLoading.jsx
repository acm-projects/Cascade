import "./ClipPlayer.css";
import PreviewLeaves from "./PreviewLeaves";

// What shows while a clip loads: a dark screen where the video is about to appear, so the page doesn't jump.
function ClipLoading() {
  return (
    <div className="clip-loading">
      <div className="clip-loading-screen" role="status">
        <PreviewLeaves />
      </div>
    </div>
  );
}

export default ClipLoading;
