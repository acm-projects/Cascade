import { useEffect, useId, useRef, useState } from 'react';
import useApi from '../../api/useApi';
import { same, concise, viewData, referenceLearning, youtubeUrl, clipTime } from './trendsView';
import './TrendsPanel.css';

const when = n => n && !Number.isNaN(new Date(typeof n === 'number' ? n * 1000 : n).getTime()) ? new Date(typeof n === 'number' ? n * 1000 : n).toLocaleString() : 'Date unavailable';
const tabs = ['Overview', 'Suggested edits', 'References'];

function ReferenceCard({ reference: ref, number, supporting, cardRef }) {
  const [failed, setFailed] = useState(false);
  const url = youtubeUrl(ref), id = ref.video_id || ref.id, learned = referenceLearning(ref);
  return <article className="trends-source" tabIndex={-1} ref={cardRef} aria-label={`Reference ${number}: ${ref.title || 'Title unavailable'}`}>
    <div className="trends-source-head"><span className="trends-badge">[{number}] {ref.kind === 'tutorial' ? 'Tutorial' : 'Example edit'}</span><small>Analyzed</small></div>
    {url && <a href={url} target="_blank" rel="noreferrer" className="trends-thumbnail" aria-label={`Watch ${ref.title || 'reference'} on YouTube`}>
      {!failed ? <img src={`https://i.ytimg.com/vi/${id}/hqdefault.jpg`} alt={ref.title || 'YouTube thumbnail'} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} /> : <span>Thumbnail unavailable</span>}
    </a>}
    <h4>{ref.title || 'Title unavailable'}</h4><p>{ref.channel || 'Channel unavailable'}</p>
    <small>Published {ref.publication_precision === 'day' && ref.published_at ? new Date(ref.published_at).toLocaleDateString(undefined, { timeZone: 'UTC' }) : when(ref.published_at)}{ref.publication_precision === 'day' ? ' · upload day' : ''}</small>
    <small>{Number.isFinite(ref.view_count) ? `${ref.view_count.toLocaleString()} views at research time` : 'View count unavailable'}</small>
    <p><strong>Why this reference</strong><br />{concise(ref.selected_reason, 230) || 'Discovered by the YouTube research step. This earlier report did not retain a clip-specific selection rationale.'}</p>
    <div><strong>{ref.kind === 'tutorial' ? 'Techniques explained' : 'Observed editing choices'}</strong>{learned.length ? <ul>{learned.map(x => <li key={x}>{x}</li>)}</ul> : <p>No detailed technique notes were retained.</p>}</div>
    <p><strong>Supports</strong><br />{supporting.length ? supporting.map(s => s.title).join(' · ') : 'No direct suggestion-to-source link was retained.'}</p>
    {url ? <a className="editor-choice trends-watch" href={url} target="_blank" rel="noreferrer">Watch on YouTube ↗</a> : <small>Source link unavailable</small>}
  </article>;
}

export default function TrendsPanel({ projectId, clip, state, info, preview, flush, onApply, disabled = false }) {
  const api = useApi(), uid = useId();
  const [record, setRecord] = useState(null), [previous, setPrevious] = useState(null);
  const [goal, setGoal] = useState('Help me improve this clip’s editing.'), [topic, setTopic] = useState(''), [topicEdited, setTopicEdited] = useState(false);
  const [tab, setTab] = useState('Overview'), [target, setTarget] = useState(null);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [activity, setActivity] = useState('');
  const [selected, setSelected] = useState([]), [statuses, setStatuses] = useState({}), [report, setReport] = useState('');
  const [speaking, setSpeaking] = useState(false), [now, setNow] = useState(() => Date.now());
  const alive = useRef(true), speech = useRef(null), cards = useRef(new Map()), scrollArea = useRef(null);
  const analysis = record?.result ? record : previous || record;
  const view = viewData(analysis, state, info), { result, references, suggestions } = view;
  const receipt = record?.applications?.findLast(a => same(a.edit_state, state));
  const applied = new Set(receipt?.applied_indices || []);
  const stale = !!record?.result && ((!same(record.edit_state, state) && !receipt) || record.expires_at * 1000 <= now || (record.goal || 'Help me improve this clip’s editing.').trim() !== goal.trim() || (topicEdited && record.topic?.trim() !== topic.trim()));
  const unavailable = busy || disabled || record?.status === 'running';
  const cannotApply = unavailable || stale || record?.status !== 'done';
  const selectable = suggestions.filter(s => !s.unavailable && !applied.has(s.index));
  const chosen = selected.filter(i => selectable.some(s => s.index === i));
  const nextEdit = suggestions.find(s => !s.unavailable && !applied.has(s.index));
  const guideText = applied.size && !nextEdit ? 'Your selected edits are in place. Compare Original and Edited, or undo to try another direction.' : nextEdit ? `I’d start with “${nextEdit.title.toLowerCase()}.” ${concise(nextEdit.benefit, 115, 1)}` : 'Tell me what you want to improve, then analyze this clip. We’ll review the findings before editing.';
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(timer); }, []);
  function accept(data) { setRecord(data); setGoal(data.goal || 'Help me improve this clip’s editing.'); setTopic(data.topic || ''); setTopicEdited(false); }
  useEffect(() => {
    alive.current = true; let cancelled = false;
    api.getTrends(projectId, clip.job_id, clip.clip_index).then(data => { if (!cancelled) accept(data); }).catch(e => !cancelled && setError(e.message));
    return () => { cancelled = true; alive.current = false; if (speech.current) window.speechSynthesis?.cancel(); };
  }, [api, projectId, clip.job_id, clip.clip_index]);
  useEffect(() => {
    if (record?.status !== 'running') return;
    const timer = setTimeout(() => api.getTrends(projectId, clip.job_id, clip.clip_index, record.id).then(data => { if (alive.current) { setRecord(data); setError(''); } }).catch(e => { if (alive.current) { setError(e.message); setRecord(r => ({ ...r, status: 'error' })); } }), 1600);
    return () => clearTimeout(timer);
  }, [api, projectId, clip.job_id, clip.clip_index, record]);
  useEffect(() => {
    if (!target || tab !== 'References') return;
    const element = cards.current.get(target); element?.focus(); element?.scrollIntoView({ block: 'nearest' });
  }, [tab, target]);
  useEffect(() => { if (scrollArea.current && (tab !== 'References' || !target)) scrollArea.current.scrollTop = 0; }, [tab, target]);
  function openReference(id) { setTab('References'); setTarget(id); }
  function chips(s) { return s.source_ids?.length ? <span className="trends-chips" aria-label="Supporting references">{s.source_ids.map(id => <button className="trends-chip" key={id} onClick={() => openReference(id)} aria-label={`Open reference ${references.findIndex(r => r.id === id) + 1}`}>[{references.findIndex(r => r.id === id) + 1}]</button>)}</span> : <small className="trends-badge">AI suggestion</small>; }
  async function analyze(force = false) {
    setBusy(true); setError(''); setReport(''); setActivity('Preparing your clip…'); if (record?.result) setPrevious(record);
    try {
      await flush?.();
      const data = await api.analyzeTrends(projectId, clip.job_id, clip.clip_index, { state, goal, topic: topicEdited ? topic : '', force: force || stale });
      if (alive.current) { setRecord(data); setGoal(data.goal || goal); setTopic(data.topic || ''); setTopicEdited(false); setStatuses({}); setSelected([]); }
    } catch (e) { if (alive.current) setError(e.message); }
    finally { if (alive.current) setBusy(false); }
  }
  async function apply(indices) {
    setBusy(true); setError(''); setActivity('Applying selected edits…');
    setStatuses(s => ({ ...s, ...Object.fromEntries(indices.map(i => [i, { status: 'applying' }])) }));
    try {
      await flush?.(); const response = await onApply(record.id, indices);
      if (!response) throw Error('The editor did not confirm an edit. Your previous draft is preserved.');
      if (alive.current) {
        setReport(response.message); setSelected([]);
        setStatuses(s => ({ ...s, ...Object.fromEntries((response.outcomes || indices.map(index => ({ index, status: 'failed', message: 'No per-edit outcome was returned.' }))).map(o => [o.index, o])) }));
        if (response.application) setRecord(r => ({ ...r, applications: [...(r.applications || []), response.application] }));
      }
    } catch (e) { if (alive.current) { setError(e.message); setStatuses(s => ({ ...s, ...Object.fromEntries(indices.map(i => [i, { status: 'failed', message: e.message }])) })); } }
    finally { if (alive.current) setBusy(false); }
  }
  async function retry() {
    if (record) return analyze(true);
    setBusy(true); setError(''); setActivity('Loading saved research…');
    try { const data = await api.getTrends(projectId, clip.job_id, clip.clip_index); if (alive.current) accept(data); }
    catch (e) { if (alive.current) setError(e.message); }
    finally { if (alive.current) setBusy(false); }
  }
  function stop() { window.speechSynthesis?.cancel(); setSpeaking(false); }
  function read() {
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) { setError('Read aloud is unavailable. The fox’s explanation is shown as text.'); return; }
    stop(); const line = new SpeechSynthesisUtterance(concise(guideText, 380, 3));
    const voices = window.speechSynthesis.getVoices(); if (voices.length) line.voice = voices.find(v => v.lang.startsWith('en')) || voices[0];
    line.onend = () => alive.current && setSpeaking(false); line.onerror = () => { if (alive.current) { setSpeaking(false); setError('Speech playback is unavailable. Read the fox’s explanation instead.'); } };
    speech.current = line; setSpeaking(true); window.speechSynthesis.speak(line);
  }
  const failures = [...(record?.failures || []), ...(result.failures || [])];
  const showResult = !!analysis?.result || references.length > 0;
  return <div className="trends-workspace">
    <aside className="trends-preview-stack">{preview}
      <div className="trends-guide" aria-label="Fox editing guide"><span aria-hidden="true">🦊</span><div><strong>A little direction</strong><p>{concise(guideText, 300, 3)}</p><button className="editor-choice" onClick={read} disabled={speaking}>Read aloud</button>{speaking && <button className="editor-choice" onClick={stop}>Stop</button>}</div></div>
      <p className="trends-scope">YouTube-based research · Your clip changes only when you apply an edit.</p>
    </aside>
    <section className="trends-main" aria-label="Clip analysis">
      <div className="trends-goal"><label className="editor-control">Editing goal<textarea rows={2} maxLength={600} value={goal} onChange={e => setGoal(e.target.value)} /></label><button className="editor-choice" disabled={unavailable || !state} onClick={() => analyze()}>{record?.status === 'running' ? 'Analyzing…' : 'Analyze clip'}</button></div>
      <div role="tablist" aria-label="Research views" className="trends-tabs">{tabs.map((name, i) => <button key={name} id={`${uid}-tab-${i}`} role="tab" aria-selected={tab === name} aria-controls={`${uid}-panel`} tabIndex={tab === name ? 0 : -1} onClick={() => { setTarget(null); setTab(name); }} onKeyDown={e => { let next; if (e.key === 'ArrowRight') next = (i + 1) % 3; if (e.key === 'ArrowLeft') next = (i + 2) % 3; if (e.key === 'Home') next = 0; if (e.key === 'End') next = 2; if (next !== undefined) { e.preventDefault(); setTarget(null); setTab(tabs[next]); e.currentTarget.parentElement.children[next].focus(); } }}>{name}{name === 'References' && <span className="trends-tab-count">{references.length}</span>}</button>)}</div>
      <div className="trends-scroll" ref={scrollArea} role="tabpanel" id={`${uid}-panel`} aria-labelledby={`${uid}-tab-${tabs.indexOf(tab)}`} tabIndex={0}>
        {(busy || record?.status === 'running') && <p className="trends-notice" role="status">{busy ? activity : 'Researching recent examples and techniques…'}</p>}
        {(error || record?.status === 'error') && <div className="trends-error" role="alert"><p>{error || 'Research could not finish. Your current edit is unchanged.'}</p><button className="editor-choice" disabled={unavailable} onClick={retry}>Retry</button></div>}
        {stale && <p className="trends-notice" role="status">Outdated findings · the clip, goal or research window changed. Analyze again before applying.</p>}
        {previous && !record?.result && <p className="trends-notice">Previous findings are kept here for review. Apply is paused until fresh analysis is ready.</p>}
        {/mock|fixture|offline/i.test(result.coverage || '') && <p className="trends-error">Test data — not live YouTube analysis.</p>}
        {!record && !error && <p role="status">Loading this clip’s research…</p>}
        {tab === 'Overview' && <>
          <div className="trends-section-heading"><h3>Your next best edit</h3><small>Analyzed {view.examples} {view.examples === 1 ? 'example' : 'examples'} and {view.tutorials} {view.tutorials === 1 ? 'tutorial' : 'tutorials'}{analysis?.researched_at ? ` · Updated ${when(analysis.researched_at)}` : ''}</small></div>
          <p className="trends-summary">{showResult ? view.summary : 'Start with your editing goal. Cascade will compare this clip with relevant YouTube examples and tutorials, then suggest edits you can review.'}</p>
          {view.evidenceWarning && showResult && <p className="trends-scope">{view.evidenceWarning}</p>}
          {view.strengths.length > 0 && <section><h4>What works</h4><ul className="trends-strengths">{view.strengths.map(s => <li key={s}>{s}</li>)}</ul></section>}
          <section><h4>What to improve</h4>{suggestions.slice(0, 3).map((s, i) => <article className="trends-opportunity" key={s.index}><span className="trends-priority">{i + 1}</span><div><strong>{s.title}</strong><p>{s.shortText}</p><small>{s.benefit}</small>{chips(s)}</div></article>)}{!suggestions.length && <p>No clip-specific opportunities are ready yet.</p>}</section>
        </>}
        {tab === 'Suggested edits' && <><h3>Choose what to change</h3><p className="trends-scope">Apply only the edits you want. Each action stays in the same undoable, saved editor state.</p>
          {suggestions.map(s => {
            const outcome = statuses[s.index]; const status = s.unavailable ? 'unsupported' : applied.has(s.index) ? 'applied' : outcome?.status === 'applied' ? 'suggested' : outcome?.status || 'suggested';
            const label = status === 'skipped' ? 'Unsupported' : status.charAt(0).toUpperCase() + status.slice(1);
            return <article className="trends-suggestion" key={s.index} tabIndex={-1} aria-label={s.title}>
              <div className="trends-suggestion-head"><label><input type="checkbox" aria-label={`Select ${s.title}`} checked={chosen.includes(s.index)} disabled={cannotApply || !!s.unavailable || applied.has(s.index)} onChange={e => setSelected(a => e.target.checked ? [...a, s.index] : a.filter(i => i !== s.index))} /><strong>{s.title}</strong></label><span className={`trends-badge status-${status}`}>{label}</span></div>
              <small>{clipTime(s, state)}</small><p>{s.shortText}</p><p className="trends-benefit">{s.benefit}</p>{chips(s)}
              {s.action && <small><strong>Apply action:</strong> {s.action}{s.limitation && <> {s.limitation}</>}</small>}
              {(s.unavailable || outcome?.message) && <small>{s.unavailable || concise(outcome.message, 220)}</small>}
              <button className="editor-choice" disabled={cannotApply || !!s.unavailable || applied.has(s.index)} onClick={() => apply([s.index])}>{status === 'applying' ? 'Applying…' : status === 'applied' ? 'Applied' : 'Apply'}</button>
            </article>;
          })}{!suggestions.length && <p>No executable suggestions are ready. Analyze the clip first.</p>}</>}
        {tab === 'References' && <><h3>What informed this analysis</h3><p className="trends-scope">Examples show observed editing choices. Tutorials explain techniques. Only successfully analyzed sources appear here.</p>
          {!references.length && <p>No successfully analyzed references yet.</p>}
          <div className="trends-reference-grid">{references.map((ref, i) => <ReferenceCard key={ref.id} reference={ref} number={i + 1} supporting={suggestions.filter(s => s.source_ids.includes(ref.id))} cardRef={node => { if (node) cards.current.set(ref.id, node); else cards.current.delete(ref.id); }} />)}</div>
          {!!failures.length && <details><summary>Not analyzed · {failures.length} discovery or analysis gaps</summary><ul>{failures.map((f, i) => <li key={i}>{f.title || f.reference_id || 'Search attempt'}: {concise(f.reason, 170)}{youtubeUrl(f) && <a href={youtubeUrl(f)} target="_blank" rel="noreferrer"> Watch on YouTube</a>}</li>)}</ul></details>}
        </>}
        <details className="trends-details"><summary>Search details</summary><label className="editor-control">Derived search terms<input maxLength={160} value={topic} onChange={e => { setTopic(e.target.value); setTopicEdited(true); }} /></label><p className="trends-scope">Derived from your clip’s content and editing goal. Instructions are kept separate from search terms.</p>{result.search_topic && <small>Last search: {result.search_topic}</small>}</details>
        <details className="trends-details"><summary>Research details</summary><p>{result.coverage || 'YouTube references are not verified TikTok or Instagram trends. No virality guarantee.'}</p><p>Expires: {when(analysis?.expires_at)}</p><p>{result.speech_evidence?.message || view.evidenceWarning}</p>
          {view.patterns.length > 0 && <><h4>Reference observations · not clip defects</h4><ul>{view.patterns.map(p => <li key={p}>{p}</li>)}</ul></>}
          {record?.message && <p>Processing: {record.message}</p>}{!!failures.length && <ul>{failures.map((f, i) => <li key={i}>{f.stage || f.kind} · {f.code || 'failed'}: {f.reason}</li>)}</ul>}
          {report && <pre className="trends-report">{report}</pre>}
        </details>
      </div>
      <footer className="trends-actions">{tab !== 'Suggested edits' ? <button className="editor-choice trends-primary" onClick={() => setTab('Suggested edits')} disabled={!suggestions.length}>Review suggested edits →</button> : <><button className="editor-choice" disabled={cannotApply || !selectable.length} onClick={() => setSelected(chosen.length === selectable.length ? [] : selectable.map(s => s.index))}>{chosen.length === selectable.length && chosen.length ? 'Clear selection' : 'Select available edits'}</button><button className="editor-choice trends-primary" disabled={cannotApply || !chosen.length} onClick={() => apply(chosen)}>Apply selected edits{chosen.length ? ` (${chosen.length})` : ''}</button></>}</footer>
    </section>
  </div>;
}
