export default function ExportSettings({ settings, onChange, downloads, selectedCount }) {
  return <div className="export-section">
    <h3 className="export-section-title">Download settings</h3>
    <label>Resolution cap <select value={settings.resolution} disabled={downloads.working}
      onChange={e => onChange({ ...settings, resolution: e.target.value })}>
      <option value="original">Original</option><option value="1080p">1080p short side</option>
      <option value="720p">720p short side</option>
    </select></label>
    <label className="export-check"><input type="checkbox" checked={settings.includeCaptions}
      disabled={downloads.working} onChange={e => onChange({ ...settings, includeCaptions: e.target.checked })}/>
      Include enabled captions</label>
    <p>Applies to MP4 and ZIP downloads. Smaller videos stay at their current size. Burned-in captions remain.</p>
    {selectedCount > 10 && <p role="note">Rendering more than 10 clips may take a few minutes.</p>}
    {downloads.progressText && <p role="status" aria-live="polite">{downloads.progressText}</p>}
    {downloads.error && <div role="alert">{downloads.error} <button type="button" disabled={downloads.working} onClick={downloads.retry}>Retry download</button></div>}
  </div>;
}
