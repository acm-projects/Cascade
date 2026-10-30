import { useCallback, useEffect, useState } from 'react';
import useApi from '../../api/useApi';
import { audioAssetPath } from '../../api/editor';
import Spinner from '../../components/ui/Spinner';
import './EditorControls.css';

function AudioPreview({ path }) {
  const api = useApi();
  const [url, setUrl] = useState(null);
  const [error, setError] = useState('');
  async function load() {
    try { setUrl(URL.createObjectURL(await api.getMedia(path))); } catch (e) { setError(e.message); }
  }
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  return url ? <audio controls preload="metadata" src={url} aria-label="Track audio preview" /> : <><button type="button" className="editor-choice" onClick={load}>Preview audio</button>{error && <p role="alert">{error}</p>}</>;
}

export default function MusicControls({ projectId, clip, state, duration, change }) {
  const api = useApi();
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const reload = useCallback(() => {
    setLoading(true); setError('');
    return api.listAudioAssets(projectId, clip.job_id, clip.clip_index).then(data => setAssets(data.assets)).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, [api, projectId, clip.job_id, clip.clip_index]);
  useEffect(() => { reload(); }, [reload]);
  const segments = state.audio || [];
  function add(asset) {
    const start = state.start;
    const segment = { id: crypto.randomUUID().replaceAll('-', ''), asset_id: asset.id, track: asset.kind, start,
      duration: asset.kind === 'music' ? state.end - start : Math.min(asset.duration, state.end - start), offset: 0,
      volume: asset.kind === 'music' ? .18 : .55, fade_in: asset.kind === 'music' ? .3 : .01,
      fade_out: asset.kind === 'music' ? .5 : .05, duck: asset.kind === 'music', duck_gain: .25, loop: asset.kind === 'music' };
    change(s => ({ ...s, reel: s.reel && asset.kind === 'music' ? { ...s.reel, beat_sync_current: false } : s.reel, audio: [...(s.audio || []).filter(a => asset.kind !== 'music' || a.track !== 'music'), segment] }));
  }
  function update(id, key, value) {
    change(s => ({ ...s, reel: s.reel && ['start','offset','duration','loop'].includes(key) ? { ...s.reel, beat_sync_current: false } : s.reel, audio: (s.audio || []).map(a => {
      if (a.id !== id) return a;
      const next = { ...a, [key]: value };
      if (key === 'start') { next.start = Math.max(0, Math.min(duration-.05, value)); next.duration = Math.min(a.duration, duration-next.start); }
      if (!next.loop) { const asset = assets.find(item => item.id === a.asset_id); if (asset) next.duration = Math.max(.05, Math.min(next.duration, asset.duration-next.offset)); }
      return next;
    }) }));
  }
  async function upload(e) {
    const file = e.target.files[0]; if (!file) return;
    setUploading(true); setError('');
    try { const item = await api.uploadAudioAsset(projectId, clip.job_id, clip.clip_index, file); setAssets(items => [...items, item]); }
    catch (err) { setError(err.message); }
    finally { setUploading(false); e.target.value = ''; }
  }
  return <div className="editor-controls music-controls">
    <label className="editor-control">Upload your music<input type="file" accept="audio/*" aria-label="Upload music" onChange={upload} disabled={uploading} /></label>
    <p className="editor-control-note">Use audio you have permission to use. Built-in tracks below are actual procedural synth recordings. Dialogue stays audible; ducking follows transcript speech windows.</p>
    {uploading && <p role="status">Uploading and validating audio…</p>}
    {error && <p role="alert">{error} <button className="editor-choice" onClick={reload}>Retry</button></p>}
    {loading && <Spinner label="Loading available music" />}
    {!loading && !assets.length && <p>No tracks available. Upload your own audio.</p>}
    <h3>On your timeline</h3>
    {!segments.length && <p>No added audio. Choose a track below or ask the chat.</p>}
    {segments.map(segment => <fieldset className="editor-controls music-segment" key={segment.id}><legend>{assets.find(a => a.id === segment.asset_id)?.name || 'Saved audio'} · {segment.track}</legend>
      <label className="editor-control">Volume · {Math.round(segment.volume * 100)}%<input aria-label={`${segment.track} volume`} type="range" min="0" max="2" step=".01" value={segment.volume} onChange={e => update(segment.id, 'volume', Number(e.target.value))} /></label>
      {[['start', 'Timeline start (s)', 0, duration], ['duration', 'Duration (s)', .05, duration - segment.start], ['offset', 'Source trim start (s)', 0, assets.find(a => a.id === segment.asset_id)?.duration || 1200], ['fade_in', 'Fade in (s)', 0, 30], ['fade_out', 'Fade out (s)', 0, 30]].map(([key,label,min,max]) => <label className="editor-control" key={key}>{label}<input type="number" min={min} max={max} step=".05" value={segment[key]} onChange={e => update(segment.id, key, Number(e.target.value))} /></label>)}
      <label className="editor-control-row"><input type="checkbox" checked={segment.loop} onChange={e => update(segment.id, 'loop', e.target.checked)} />Loop source</label>
      <label className="editor-control-row"><input type="checkbox" checked={segment.duck} onChange={e => update(segment.id, 'duck', e.target.checked)} />Duck during dialogue</label>
      {segment.duck && <label className="editor-control">Speech level · {Math.round(segment.duck_gain * 100)}%<input type="range" min="0" max="1" step=".05" value={segment.duck_gain} onChange={e => update(segment.id, 'duck_gain', Number(e.target.value))} /></label>}
      <button className="editor-choice" onClick={() => change(s => ({ ...s, reel: s.reel ? { ...s.reel, beat_sync_current: false } : null, audio: s.audio.filter(a => a.id !== segment.id) }))}>Remove audio</button>
    </fieldset>)}
    <h3>Available music &amp; sounds</h3>
    {assets.map(asset => <div className="music-asset" key={asset.id}><strong>{asset.name}</strong><small>{asset.kind} · {asset.duration.toFixed(1)}s · {asset.license}</small>
      <AudioPreview path={audioAssetPath(projectId, clip.job_id, clip.clip_index, asset.id)} />
      <button type="button" className="editor-choice" disabled={uploading} onClick={() => add(asset)}>{asset.kind === 'music' && segments.some(s => s.track === 'music') ? 'Replace music' : 'Add'}</button>
    </div>)}
  </div>;
}
