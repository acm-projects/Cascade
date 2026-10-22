import { useState } from "react";
import "./ExportPage.css";
import TopBar from "../components/TopBar";
import SequencePlayer from "../components/SequencePlayer";
import { useProject } from "../context/ProjectContext";

const socials = ["YouTube", "Instagram", "TikTok"];

// Built from the Figma "Export" wireframe (node 557:2263)
function ExportPage() {
  const { project, sourceVideo, selectedClips, stepsUnlocked, aspectRatio, setAspectRatio } = useProject();

  const [currentIndex, setCurrentIndex] = useState(0);
  const [format, setFormat] = useState("MP4");
  const [resolution, setResolution] = useState("1080p");
  const [includeCaptions, setIncludeCaptions] = useState(true);
  const [status, setStatus] = useState("idle");          // "idle" | "exporting" | "done"

  // FAKE export until the backend can render the video
  function handleExport() {
    setStatus("exporting");
    setTimeout(() => setStatus("done"), 2000);
  }

  return (
    <div className="export">
      <TopBar title={project?.name} activeStep="export" stepsUnlocked={stepsUnlocked} />

      <div className="export-body">
        {/* Video preview with play bar (1068 x 659) */}
        <section className="export-preview">
          <SequencePlayer
            sourceUrl={sourceVideo?.url ?? null}
            clips={selectedClips}
            currentIndex={currentIndex}
            onIndexChange={setCurrentIndex}
            aspectRatio={aspectRatio}
            showProgress
          />
        </section>

        {/* Export settings (551 x 659) */}
        <section className="export-settings">
          <h2 className="export-title">Export Settings</h2>

          <label className="export-field">
            Format
            <select value={format} onChange={(e) => setFormat(e.target.value)}>
              <option>MP4</option>
              <option>MOV</option>
            </select>
          </label>

          <label className="export-field">
            Resolution
            <select value={resolution} onChange={(e) => setResolution(e.target.value)}>
              <option>720p</option>
              <option>1080p</option>
              <option>4K</option>
            </select>
          </label>

          <label className="export-field">
            Aspect ratio
            <select value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)}>
              <option value="16:9">16:9 Horizontal</option>
              <option value="9:16">9:16 Vertical</option>
              <option value="1:1">1:1 Square</option>
            </select>
          </label>

          <label className="export-check">
            <input type="checkbox" checked={includeCaptions} onChange={(e) => setIncludeCaptions(e.target.checked)} />
            Include captions
          </label>

          <button
            type="button"
            className={`btn btn-small export-button ${stepsUnlocked ? "btn-primary" : "disabled"}`}
            disabled={!stepsUnlocked || status === "exporting"}
            onClick={handleExport}
          >
            {status === "exporting" ? "Exporting..." : "Export Video"}
          </button>
          {status === "done" && <p className="export-done">✓ Export finished (demo)</p>}
        </section>

        {/* Bottom: social posting (TBD in the wireframe) */}
        <section className="export-social">
          <h3 className="export-social-title">Also post to</h3>
          <div className="export-social-list">
            {socials.map((name) => (
              <label key={name} className="export-social-item">
                <input type="checkbox" disabled />
                {name}
              </label>
            ))}
          </div>
          <p className="export-social-note">Optimized posting for YouTube, Instagram, and TikTok is coming soon.</p>
        </section>
      </div>
    </div>
  );
}

export default ExportPage;
