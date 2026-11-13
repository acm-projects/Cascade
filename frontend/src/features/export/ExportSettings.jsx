// "3. Configure export" for downloads: a preset card row, then the details.
// The presets are shortcuts for the resolution the server renders at (backend/editor_backend.py):
// "original" keeps the source size, "1080p" / "720p" shrink the short side. Videos are MP4, audio clips MP3.
//   settings - { resolution, includeCaptions }      onChange(settings)
//   downloads - from useDownloads (working / progress / error)
const PRESETS = [
  { resolution: "1080p", title: "High Quality", text: "1080p · MP4" },
  { resolution: "original", title: "Original Quality", text: "Match source" },
  { resolution: "720p", title: "Smaller File", text: "720p · MP4" },
];

export default function ExportSettings({ settings, onChange, downloads, selectedCount, audioOnly }) {
  const locked = downloads.working;
  return (
    <div className="export-section">
      {!audioOnly && (
        <div className="export-field-group">
          <span className="export-label">Export preset</span>
          <div className="export-presets" role="radiogroup" aria-label="Export preset">
            {PRESETS.map((preset) => {
              const chosen = settings.resolution === preset.resolution;
              return (
                <button key={preset.resolution} type="button" role="radio" aria-checked={chosen} disabled={locked}
                  className={`export-preset${chosen ? " active" : ""}`}
                  onClick={() => onChange({ ...settings, resolution: preset.resolution })}>
                  <b>{preset.title}</b>
                  <span>{preset.text}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className="export-fields">
        <label className="export-field">
          Format
          <select value={audioOnly ? "mp3" : "mp4"} disabled>
            {audioOnly ? <option value="mp3">MP3 (audio)</option> : <option value="mp4">MP4</option>}
          </select>
        </label>
        <label className="export-field">
          Resolution
          <select value={settings.resolution} disabled={locked || audioOnly}
            onChange={(e) => onChange({ ...settings, resolution: e.target.value })}>
            <option value="original">Original</option>
            <option value="1080p">1080p (Full HD)</option>
            <option value="720p">720p (HD)</option>
          </select>
        </label>
      </div>

      <label className="export-check">
        <input type="checkbox" checked={settings.includeCaptions} disabled={locked}
          onChange={(e) => onChange({ ...settings, includeCaptions: e.target.checked })} />
        Include captions
      </label>

      <details className="export-help">
        <summary>Advanced settings</summary>
        <p>
          {audioOnly
            ? "Audio exports are MP3. Enabled transcript captions are included as VTT files in ZIP downloads; they can't be burned into audio."
            : "1080p and 720p set the video's short side, so vertical and wide clips both stay sharp. Smaller videos keep their size. Captions are burned into the picture."}
        </p>
      </details>

      {selectedCount > 10 && <p className="export-note" role="note">Rendering more than 10 clips may take a few minutes.</p>}
      {downloads.progressText && <p className="export-note" role="status" aria-live="polite">{downloads.progressText}</p>}
      {downloads.error && (
        <div className="export-note is-error" role="alert">
          {downloads.error}{" "}
          <button type="button" className="export-link" disabled={downloads.working} onClick={downloads.retry}>Retry download</button>
        </div>
      )}
    </div>
  );
}
