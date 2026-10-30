import { useEffect, useRef, useState } from "react";
import useApi from "../../api/useApi";
import { insertBroll, updateBroll, validateBroll } from "./brollTiming";
import "./BrollPanel.css";

function useStockUrl(api, projectId, clip, id, kind, enabled = true) {
  const [result, setResult] = useState({ url: null, error: "" });
  useEffect(() => {
    if (!enabled || !id) return;
    let active = true, url;
    api.getBrollMedia(projectId, clip.job_id, clip.clip_index, id, kind).then(blob => {
      if (!active) return;
      url = URL.createObjectURL(blob);
      setResult({ url, error: "" });
    }).catch(error => { if (active) setResult({ url: null, error: error.message }); });
    return () => { active = false; if (url) URL.revokeObjectURL(url); };
  }, [api, projectId, clip.job_id, clip.clip_index, id, kind, enabled]);
  return result;
}

function StockResult({ api, projectId, clip, asset, selected, onSelect }) {
  const [hover, setHover] = useState(false);
  const [loadMedia, setLoadMedia] = useState(false);
  const [playbackError, setPlaybackError] = useState("");
  const video = useRef(null);
  const thumb = useStockUrl(api, projectId, clip, asset.id, "thumbnail");
  const media = useStockUrl(api, projectId, clip, asset.id, "media", loadMedia);
  return <article className={`broll-result${selected ? " selected" : ""}`}>
    <button type="button" aria-pressed={selected} aria-label={`Select stock by ${asset.creator}, ${asset.duration} seconds`}
      onClick={() => onSelect(asset.id)} onMouseEnter={() => { setHover(true); setLoadMedia(true); }} onMouseLeave={() => { video.current?.pause(); setHover(false); }}
      onFocus={() => { setHover(true); setLoadMedia(true); }} onBlur={() => { video.current?.pause(); setHover(false); }}>
      {hover && media.url ? <video ref={video} src={media.url} autoPlay muted playsInline loop aria-label="Muted stock preview" onError={() => setPlaybackError("Stock preview cannot be played. Choose another result.")} />
        : thumb.url ? <img src={thumb.url} alt={`Stock footage by ${asset.creator}`} /> : <span>Loading thumbnail…</span>}
      <span>{asset.duration}s · {asset.creator}</span>
    </button>
    {(thumb.error || media.error || playbackError) && <small role="alert">{thumb.error || media.error || playbackError}</small>}
    <a href={asset.source_url} target="_blank" rel="noopener noreferrer">Video by {asset.creator} on Pexels ↗</a>
  </article>;
}

export default function BrollPanel({ projectId, clip, state, duration, player, change, search, onSearch, selectedId, onSelect, onClose, disabled }) {
  const api = useApi();
  const [query, setQuery] = useState(search?.query || "");
  const [chosenId, setChosenId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef(0);
  useEffect(() => () => { ++request.current; }, []);
  const selected = state.broll?.find(s => s.id === selectedId);
  const chosen = search?.results.find(a => a.id === chosenId);

  async function find(event, more = false) {
    event?.preventDefault();
    const text = more ? search.query : query.trim();
    if (!text) return;
    const count = ++request.current;
    setBusy(true); setError("");
    try {
      const result = await api.searchBroll(projectId, clip.job_id, clip.clip_index, text, more ? search.page + 1 : 1);
      if (count !== request.current) return;
      const results = more ? [...new Map([...search.results, ...result.results].map(a => [a.id, a])).values()] : result.results;
      onSearch({ ...result, results: results.slice(0, 120) });
      if (!more) setChosenId(null);
    } catch (e) { if (count === request.current) setError(e.message); }
    finally { if (count === request.current) setBusy(false); }
  }

  function insert() {
    try {
      const id = crypto.randomUUID().replaceAll("-", "");
      const next = insertBroll(state, chosen, player.current?.getTime(), id);
      validateBroll(next.broll, duration);
      change(next); onSelect(id); setError("");
      player.current?.seek(next.broll.at(-1).start + .001);
    } catch (e) { setError(e.message); }
  }

  function update(event) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      const changes = { start: Number(data.get("start")), duration: Number(data.get("duration")), offset: Number(data.get("offset")), mode: data.get("mode") };
      change(updateBroll(state, selected.id, changes, duration)); setError("");
    } catch (e) { setError(e.message); }
  }

  return <aside className="broll-drawer wood-panel" aria-label="B-roll panel">
    <header><h2>B-roll</h2><button type="button" className="btn btn-ghost btn-small" aria-label="Close B-roll" onClick={onClose}>✕</button></header>
    <p>Search Pexels stock footage. Your original dialogue stays.</p>
    <form className="broll-search" onSubmit={find}>
      <label>Search stock footage<input value={query} onChange={e => setQuery(e.target.value)} maxLength={160} required placeholder="e.g. city skyline" /></label>
      <button className="btn btn-small" disabled={busy || disabled}>{busy ? "Searching…" : "Search"}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    <div className="broll-results" aria-label="Stock search results">
      {search?.results.map(asset => <StockResult key={asset.id} api={api} projectId={projectId} clip={clip} asset={asset} selected={asset.id === chosenId} onSelect={setChosenId} />)}
    </div>
    {search?.results.length === 0 && <p>No footage found. Try another search.</p>}
    {search?.has_more && search.results.length < 120 && <button className="btn btn-small" disabled={busy || disabled} onClick={() => find(null, true)}>More results</button>}
    <button className="btn btn-primary btn-small" disabled={!chosen || busy || disabled || state.broll.length >= 30} onClick={insert}>Insert at playhead</button>
    <small>Up to 3 seconds, shortened to fit the available timeline space.</small>
    {selected && <form key={JSON.stringify(selected)} className="broll-timing" onSubmit={update}>
      <h3>Selected B-roll segment</h3>
      {[['start', 'Start', duration], ['duration', 'Duration', Math.min(duration, selected.asset.duration)], ['offset', 'Stock offset', selected.asset.duration]].map(([name,label,max]) =>
        <label key={name}>{label} (seconds)<input name={name} type="number" step="any" min={name === 'duration' ? .05 : 0} max={max} defaultValue={selected[name]} required /></label>)}
      <label>Framing<select name="mode" defaultValue={selected.mode}><option value="fill">Fill</option><option value="fit">Fit</option></select></label>
      <button className="btn btn-small" disabled={disabled}>Update timing</button>
      <button className="btn btn-ghost btn-small" type="button" disabled={disabled} onClick={() => { change({ ...state, broll: state.broll.filter(s => s.id !== selectedId) }); onSelect(null); }}>Remove selected B-roll</button>
    </form>}
  </aside>;
}
