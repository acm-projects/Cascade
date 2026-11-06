import "./ClipPlayer.css";
import Icon from "../../components/ui/Icon";

// What shows while a clip loads: a dark screen where the video is about to appear, so the page doesn't jump.
function ClipLoading() {
  return (
    <div className="clip-loading">
      <div className="clip-loading-screen" role="status">
        <Icon name="leaf" size={36} className="clip-loading-leaf" />
        <span>Loading clip…</span>
      </div>
    </div>
  );
}

export default ClipLoading;
