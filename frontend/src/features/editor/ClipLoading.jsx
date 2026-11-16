import Icon from "../../components/ui/Icon";
import "./ClipPlayer.css";

// What shows while a clip loads, where the video is about to appear (so the page doesn't jump): a patch of
// deep blue water with light rays drifting across it and a few bubbles rising, and a softly pulsing play button.
function ClipLoading() {
  return (
    <div className="clip-loading">
      <div className="clip-loading-screen" role="status">
        <span className="clip-loading-bubble" aria-hidden="true" />
        <span className="clip-loading-bubble" aria-hidden="true" />
        <span className="clip-loading-bubble" aria-hidden="true" />
        <span className="clip-loading-play" aria-hidden="true"><Icon name="play" size={26} /></span>
        Loading clip…
      </div>
    </div>
  );
}

export default ClipLoading;
