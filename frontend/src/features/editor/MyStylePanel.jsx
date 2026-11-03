import { useEffect, useState } from "react";
import useApi from "../../api/useApi";
import "./MyStylePanel.css";

// My Style: build a style sheet from your own reference reels, review it, approve it,
// then let the AI Editor edit any clip in that style (backend/editor/style_profile.py).
const OPTIONS = {
  look: ["natural", "vivid", "warm", "teal_orange", "bw", "sepia"],
  pacing: ["slow", "medium", "fast"],
  captions: ["pop", "karaoke", "clean", "none"],
  emphasis_font: ["impact", "poster", "typewriter", "script", "grunge"],
  transitions: ["cut", "flash", "dissolve"],
  music: ["none", "Quiet reflection", "Tension pulse", "Reel pulse", "Playful plucks"],
  broll: ["low", "medium", "high"],
};
const LABELS = { look: "Look", pacing: "Pacing", captions: "Captions", emphasis_font: "Key-word font", transitions: "Transitions", music: "Music", broll: "B-roll" };
const TOGGLES = { punch_ins: "Punch-in zooms", words_behind: "Big words behind speaker", glitch_accents: "Glitch accents",
  sound_fx: "Whooshes & hits", tighten_pauses: "Cut pauses", motion_cards: "HyperFrames hook card" };
const STORE = "cascade-my-style";

export default function MyStylePanel({ projectId, onApply, disabled }) {
  const api = useApi();
  const [styles, setStyles] = useState([]);
  const [activeId, setActiveId] = useState(() => { try { return localStorage.getItem(STORE) || ""; } catch { return ""; } });
  const [files, setFiles] = useState([]);
  const [links, setLinks] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api.listStyles(projectId).then(r => setStyles(r.styles)).catch(e => setError(e.message));
  }, [api, projectId]);

  const active = styles.find(s => s.id === activeId) || styles[0];
  function choose(id) {
    setActiveId(id);
    try { localStorage.setItem(STORE, id); } catch { /* private mode: selection lasts this visit */ }
  }
  function replace(profile) {
    setStyles(all => [profile, ...all.filter(s => s.id !== profile.id)]);
    choose(profile.id);
  }

  async function build() {
    setBusy("Watching your references…"); setError("");
    try {
      const urls = links.split(/\s+/).map(u => u.trim()).filter(Boolean);
      replace(await api.createStyle(projectId, files, urls));
      setFiles([]); setLinks(""); setOpen(false);
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }
  async function save(choices, approve) {
    setBusy(approve ? "Approving…" : "Saving…"); setError("");
    try { replace(await api.updateStyle(projectId, active.id, choices, approve)); }
    catch (e) { setError(e.message); } finally { setBusy(""); }
  }
  async function remove() {
    if (!window.confirm(`Delete the style "${active.choices.name}"?`)) return;
    try { await api.deleteStyle(projectId, active.id); setStyles(all => all.filter(s => s.id !== active.id)); }
    catch (e) { setError(e.message); }
  }
  const edit = (field, value) => save({ ...active.choices, [field]: value }, false);

  return <details className="my-style" open={!active || open} onToggle={e => setOpen(e.currentTarget.open)}>
    <summary>My Style {active && <span className={`my-style-badge ${active.status}`}>{active.choices.name} · {active.status}</span>}</summary>
    {styles.length > 1 && <select aria-label="Saved styles" value={active?.id} onChange={e => choose(e.target.value)}>
      {styles.map(s => <option key={s.id} value={s.id}>{s.choices.name} ({s.status})</option>)}
    </select>}

    {active && <div className="my-style-sheet">
      <ul>{active.choices.summary.map((line, i) => <li key={i}>{line}</li>)}</ul>
      <p className="my-style-meta">From {active.references.length} reference(s) · chosen by {active.chosen_by}</p>
      <div className="my-style-grid">
        {Object.entries(OPTIONS).map(([field, values]) => <label key={field}>{LABELS[field]}
          <select value={active.choices[field]} disabled={!!busy} onChange={e => edit(field, e.target.value)}>
            {values.map(v => <option key={v} value={v}>{v.replace("_", " ")}</option>)}
          </select></label>)}
        <label>Words on screen
          <input type="number" min="1" max="4" value={active.choices.caption_words} disabled={!!busy}
            onChange={e => edit("caption_words", Math.max(1, Math.min(4, Number(e.target.value) || 1)))} /></label>
        <label>Accent colour
          <input type="color" value={active.choices.accent} disabled={!!busy} onChange={e => edit("accent", e.target.value)} /></label>
        <label>Caption colour
          <input type="color" value={active.choices.caption_color} disabled={!!busy} onChange={e => edit("caption_color", e.target.value)} /></label>
      </div>
      <div className="my-style-toggles">
        {Object.entries(TOGGLES).map(([field, label]) => <label key={field}>
          <input type="checkbox" checked={active.choices[field]} disabled={!!busy} onChange={e => edit(field, e.target.checked)} /> {label}</label>)}
      </div>
      <div className="my-style-actions">
        {active.status === "draft"
          ? <button type="button" className="editor-choice primary" disabled={!!busy} onClick={() => save(active.choices, true)}>Approve style sheet</button>
          : <button type="button" className="editor-choice primary" disabled={disabled || !!busy}
              onClick={() => onApply(`Edit this clip in my "${active.choices.name}" style.`, active.id)}>Edit this clip in my style</button>}
        <button type="button" className="editor-choice" disabled={!!busy} onClick={remove}>Delete</button>
      </div>
    </div>}

    <div className="my-style-new">
      <b>{active ? "New style from references" : "Give Cascade 3–5 reels you like"}</b>
      <label className="my-style-file">Videos
        <input type="file" accept="video/mp4,video/quicktime,video/webm,.mov,.m4v" multiple disabled={!!busy}
          onChange={e => setFiles([...e.target.files].slice(0, 8))} /></label>
      <textarea rows={2} placeholder="…or paste Instagram / TikTok / YouTube links, one per line" value={links}
        disabled={!!busy} onChange={e => setLinks(e.target.value)} />
      <button type="button" className="editor-choice" disabled={!!busy || (!files.length && !links.trim())} onClick={build}>
        Build style sheet{files.length ? ` from ${files.length} video${files.length > 1 ? "s" : ""}` : ""}</button>
    </div>
    {busy && <p className="my-style-status" aria-live="polite">{busy}</p>}
    {error && <p className="my-style-error" role="alert">{error}</p>}
  </details>;
}
