import { useEffect, useRef, useState } from 'react';
import useApi from '../../api/useApi';
import { clipTime, problemText, referenceLearning, same, viewData, youtubeUrl } from './trendsView';
import './TrendsPanel.css';
import Icon from '../../components/ui/Icon';

const DEFAULT_GOAL = 'Help me improve this clip’s editing.';
const shownGoal = goal => (goal && goal !== DEFAULT_GOAL ? goal : '');
const count = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const seconds = n => new Date(n * 1000).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });

function published(ref) {
  const date = new Date(ref.published_at);
  return ref.published_at && !Number.isNaN(date.getTime()) ? date.toLocaleDateString(undefined, { timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric' }) : '';
}

function Source({ reference: ref, number }) {
  const [failed, setFailed] = useState(false);
  const url = youtubeUrl(ref), learned = referenceLearning(ref);
  const facts = [ref.channel, Number.isFinite(ref.view_count) && `${ref.view_count.toLocaleString()} views`, published(ref)].filter(Boolean);
  return <article className="trends-source" id={`trends-source-${ref.id}`} tabIndex={-1}>
    {url && !failed && <a className="trends-thumbnail" href={url} target="_blank" rel="noreferrer" tabIndex={-1} aria-hidden="true">
      <img src={`https://i.ytimg.com/vi/${ref.video_id || ref.id}/mqdefault.jpg`} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
    </a>}
    <div className="trends-source-text">
      <small className="trends-source-kind">[{number}] {ref.kind === 'tutorial' ? 'Tutorial' : 'Example'}</small>
      <h4>{url ? <a href={url} target="_blank" rel="noreferrer">{ref.title || 'Untitled video'} <Icon name="external" /></a> : ref.title || 'Untitled video'}</h4>
      {facts.length > 0 && <small>{facts.join(' · ')}</small>}
      {learned.length > 0 && <ul>{learned.map(item => <li key={item}>{item}</li>)}</ul>}
    </div>
  </article>;
}

function Improvement({ suggestion: s, number, state, references }) {
  const when = clipTime(s, state);
  function openSource(id) {
    const card = document.getElementById(`trends-source-${id}`);
    card?.scrollIntoView({ behavior: 'smooth', block: 'center' }); card?.focus({ preventScroll: true });
  }
  return <li className="trends-improvement">
    <span className="trends-number" aria-hidden="true">{number}</span>
    <div>
      <h4>{s.title}{when && <small className="trends-time">{when}</small>}</h4>
      {s.shortText && <p>{s.shortText}</p>}
      {s.benefit && <p className="trends-why">Why: {s.benefit}</p>}
      {s.source_ids.length > 0 && <span className="trends-cites">Seen in {s.source_ids.map(id => {
        const place = references.findIndex(r => r.id === id) + 1;
        return <button type="button" key={id} className="trends-cite" onClick={() => openSource(id)} aria-label={`Go to source ${place}`}>[{place}]</button>;
      })}</span>}
    </div>
  </li>;
}

export default function TrendsPanel({ projectId, clip, state, info, flush }) {
  const api = useApi();
  const [record, setRecord] = useState(null), [previous, setPrevious] = useState(null);
  const [goal, setGoal] = useState(''), [error, setError] = useState(''), [starting, setStarting] = useState(false);
  const alive = useRef(true);
  const running = starting || record?.status === 'running';
  const analysis = record?.result ? record : previous || record;
  const view = viewData(analysis, state, info);
  const { result, references, suggestions } = view;
  const finished = !!analysis?.result;
  const changed = finished && !running && !same(analysis.edit_state, state);
  const skipped = (result.failures || []).filter(f => f.title).length;
  const problem = error || (record?.status === 'error' ? problemText(record.message) : '');

  useEffect(() => {
    alive.current = true; let cancelled = false;
    api.getTrends(projectId, clip.job_id, clip.clip_index)
      .then(data => { if (!cancelled) { setRecord(data); setGoal(shownGoal(data.goal)); } })
      .catch(e => !cancelled && setError(e.message));
    return () => { cancelled = true; alive.current = false; };
  }, [api, projectId, clip.job_id, clip.clip_index]);
  useEffect(() => {
    if (record?.status !== 'running') return;
    const timer = setTimeout(() => api.getTrends(projectId, clip.job_id, clip.clip_index, record.id)
      .then(data => { if (alive.current) { setRecord(data); setError(''); } })
      .catch(e => { if (alive.current) { setError(e.message); setRecord(r => ({ ...r, status: 'error' })); } }), 1600);
    return () => clearTimeout(timer);
  }, [api, projectId, clip.job_id, clip.clip_index, record]);

  async function analyze(force = false) {
    setStarting(true); setError(''); if (record?.result) setPrevious(record);
    try {
      await flush?.();
      const data = await api.analyzeTrends(projectId, clip.job_id, clip.clip_index, { state, goal: goal.trim() || DEFAULT_GOAL, topic: '', force });
      if (alive.current) setRecord(data);
    } catch (e) { if (alive.current) setError(e.message); }
    finally { if (alive.current) setStarting(false); }
  }

  return <div className="trends-report">
    <form className="trends-goal" onSubmit={e => { e.preventDefault(); analyze(); }}>
      <label htmlFor="trends-goal-input">What do you want to improve? <span>Optional</span></label>
      <div>
        <input id="trends-goal-input" maxLength={600} value={goal} onChange={e => setGoal(e.target.value)} placeholder="e.g. keep people watching past the first 3 seconds" />
        <button className="editor-choice trends-analyze" type="submit" disabled={running || !state}>{running ? 'Analyzing…' : finished ? 'Analyze again' : 'Analyze clip'}</button>
      </div>
    </form>

    <div className="trends-scroll" tabIndex={0} aria-label="Clip analysis">
      {running && <div className="trends-progress" role="status"><span className="trends-spinner" aria-hidden="true" /><div><strong>{starting ? 'Getting your clip ready…' : record?.message || 'Analyzing…'}</strong><small>This can take a few minutes. You can close this and come back.</small></div></div>}
      {problem && !running && <div className="trends-problem" role="alert"><p>{problem}</p><button className="editor-choice" onClick={() => analyze(true)} disabled={!state}>Try again</button></div>}
      {changed && <p className="trends-note" role="status">You’ve edited this clip since this analysis. Analyze again to include your changes.</p>}
      {/mock|fixture|offline/i.test(result.coverage || '') && <p className="trends-note">Test data — not live YouTube analysis.</p>}
      {!record && !error && <p className="trends-empty" role="status">Loading…</p>}
      {record && !finished && !running && !problem && <p className="trends-empty">Compare this clip with recent YouTube edits and tutorials to see what’s working and what to improve. Analyzing won’t change your clip.</p>}

      {finished && <>
        <section className="trends-summary"><h3>The short version</h3><p>{view.summary}</p>{view.evidenceWarning && <small>{view.evidenceWarning}</small>}</section>
        {view.strengths.length > 0 && <section><h3>What’s working</h3><ul className="trends-strengths">{view.strengths.map(item => <li key={item}>{item}</li>)}</ul></section>}
        {suggestions.length > 0 && <section><h3>What to improve</h3><ol className="trends-improvements">{suggestions.map((s, i) => <Improvement key={s.index} suggestion={s} number={i + 1} state={state} references={references} />)}</ol></section>}
        {view.patterns.length > 0 && <section><h3>What the examples have in common</h3><ul className="trends-strengths">{view.patterns.map(item => <li key={item}>{item}</li>)}</ul></section>}
        {references.length > 0 && <section><h3>Sources</h3><div className="trends-sources">{references.map((ref, i) => <Source key={ref.id} reference={ref} number={i + 1} />)}</div></section>}
        <footer className="trends-footnote">
          <p>Based on {count(view.examples, 'example')} and {count(view.tutorials, 'tutorial')} from YouTube{skipped ? ` (${count(skipped, 'other video')} couldn’t be analyzed)` : ''}. This is guidance, not a prediction of how your clip will perform.</p>
          <p>{analysis.researched_at ? `Updated ${seconds(analysis.researched_at)}` : ''}</p>
        </footer>
      </>}
    </div>
  </div>;
}
