// Trend Analysis: compare your edit with relevant trending videos, see what they share,
// where your edit differs, and preview specific changes. Opens as a window over the Editor (and Export).
//
// Honesty rules this page follows:
//  - Numbers and charts come from measurements (FFmpeg on the files, or your edit's settings).
//  - AI judgments are written observations, never chart data, and never a "virality" score.
//  - Anything we couldn't measure or can't do says so, instead of showing a made-up value.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import useApi from '../../../api/useApi';
import Icon from '../../../components/ui/Icon';
import { problemText, referenceLearning, same, viewData } from '../trendsView';
import { timelineClock } from '../reelTiming';
import Guide, { Step } from './TrendGuide';
import Viral from './TrendViral';
import { EditVideo, ReferenceFacts, ReferenceVideo } from './TrendVideos';
import { AudioChart, PacingChart, ShotTimeline } from './TrendCharts';
import { ChangePreview, Improvements, Strengths } from './TrendReview';
import usePreview from './usePreview';
import { clock, countWhere, editCues, editFindings, kept, measuredVideo, musicSpans, range, secs } from './trendMetrics';
import { useCountUp, useReveal, useSimpleMotion } from './motion';
import './TrendAnalysis.css';

const DEFAULT_GOAL = 'Help me improve this clip’s editing.';
const EDIT_COLOR = 'var(--ta-edit)';
const REF_COLORS = ['var(--ta-ref)', 'var(--ta-ref-2)', 'var(--ta-ref-3)', 'var(--ta-ref-4)'];

/** Server errors in plain words: never raw JSON, never a stack of field names. */
function friendly(e) {
  const m = String(e?.message || e || '').trim();
  if (/extra_forbidden|Extra inputs|Failed to fetch|NetworkError|Load failed/i.test(m)) return 'Couldn’t reach Cascade just now. Please try again in a moment.';
  if (/^[[{]/.test(m)) return 'Something went wrong starting the analysis. Please try again.';
  return m || 'Something went wrong. Please try again.';
}
/** Why no trending video could be used, from the saved diagnostics. */
function whyNone(failures = []) {
  const codes = new Set(failures.map(f => f.code));
  if (codes.has('youtube_bot_challenge')) return 'YouTube asked this computer to prove it isn’t a bot, so videos couldn’t be downloaded.';
  if (codes.has('rate_limited') || codes.has('quota_or_credit_exhausted')) return 'YouTube or the AI service is limiting requests right now.';
  if (codes.has('no_recent_results')) return 'Nothing recent matched this topic.';
  if (codes.size) return 'The videos found couldn’t be downloaded or analyzed.';
  return '';
}

/** A section that fades up once when it scrolls into view. */
function Reveal({ scrollRef, as: Tag = 'section', className = '', children, ...rest }) {
  const [ref, shown] = useReveal(scrollRef);
  return <Tag ref={ref} className={`ta-reveal${shown ? ' is-in' : ''} ${className}`} {...rest}>
    {typeof children === 'function' ? children(shown) : children}
  </Tag>;
}

/** One at-a-glance measurement: yours next to the reference (or reference range). */
function Finding({ label, value, unit, format = v => v.toFixed(1), refText, note, shown, cardRef, empty }) {
  const counted = useCountUp(value, shown);
  return <article className="ta-finding" ref={cardRef}>
    <h3>{label}</h3>
    <div className="ta-finding-values">
      <div><small><i className="ta-key ta-key-edit" /> Your edit</small>
        <p className="ta-big">{Number.isFinite(value) ? <>{format(counted)}<span>{unit}</span></> : <span className="ta-na">{empty || 'Not measured'}</span>}</p></div>
      <div><small><i className="ta-key ta-key-ref" /> References</small>
        <p className="ta-mid">{refText || <span className="ta-na">Not measured</span>}</p></div>
    </div>
    <p className="ta-finding-note">{note}</p>
  </article>;
}

function rangeText(r, fmt = v => v.toFixed(1), unit = ' s') {
  if (!r) return null;
  return r.count === 1 || Math.abs(r.max - r.min) < 0.05 ? `${fmt(r.min)}${unit}` : `${fmt(r.min)}–${fmt(r.max)}${unit}`;
}

/** The caption style from your edit, drawn the way the player draws it (scaled down). */
function CaptionSample({ captions, text, emphasis = [] }) {
  const c = captions || {};
  const words = text.split(/\s+/).slice(0, c.max_words || 8);
  const hot = new Set(emphasis.map(w => w.toLowerCase()));
  const stroke = c.thickness ? `0 0 ${c.thickness}px ${c.stroke}, `.repeat(4).slice(0, -2) : 'none';
  return <div className={`ta-phone ta-phone-${c.position || 'bottom'}`}>
    <p style={{ fontFamily: c.font, fontSize: `${Math.max(10, (c.size || 32) * 0.42)}px`, fontWeight: c.bold ? 800 : 500, color: c.color,
      textShadow: stroke, background: c.opacity ? `color-mix(in srgb, ${c.background} ${Math.round(c.opacity * 100)}%, transparent)` : 'none' }}>
      {words.map((w, i) => <span key={i} style={hot.has(w.toLowerCase().replace(/\W/g, '')) ? { color: c.highlight } : undefined}>{w} </span>)}
    </p>
  </div>;
}

export default function TrendAnalysis({ projectId, clip, state, info, flush, change, onClose, onOpenEditor, clips = [], onSelectClip }) {
  const api = useApi();
  const simple = useSimpleMotion();
  const backdrop = useRef(null), sheet = useRef(null), scrollRef = useRef(null), workspace = useRef(null);
  const editVideo = useRef(null), refVideo = useRef(null);
  const targets = useRef({});
  const [record, setRecord] = useState(null), [previous, setPrevious] = useState(null);
  const [error, setError] = useState(''), [starting, setStarting] = useState(false);
  const [topic, setTopic] = useState(''), [links, setLinks] = useState([]), [linkDraft, setLinkDraft] = useState('');
  const [adding, setAdding] = useState(false), [linkError, setLinkError] = useState('');
  const [active, setActive] = useState(0);
  const [audio, setAudio] = useState('edit'); // whose sound is on
  const [accepted, setAccepted] = useState([]);
  const [startAt, setStartAt] = useState(null); // open the next reference at this second
  const alive = useRef(true);

  // ---------- data (same endpoints the Trends popup used) ----------
  useEffect(() => {
    alive.current = true; let cancelled = false;
    api.getTrends(projectId, clip.job_id, clip.clip_index)
      .then(data => { if (!cancelled) { setRecord(data); setTopic(data.topic_override || ''); } })
      .catch(e => !cancelled && setError(friendly(e)));
    return () => { cancelled = true; alive.current = false; };
  }, [api, projectId, clip.job_id, clip.clip_index]);
  useEffect(() => {
    if (record?.status !== 'running') return undefined;
    const timer = setTimeout(() => api.getTrends(projectId, clip.job_id, clip.clip_index, record.id)
      .then(data => { if (alive.current) { setRecord(data); setError(''); } })
      .catch(e => { if (alive.current) { setError(friendly(e)); setRecord(r => ({ ...r, status: 'error' })); } }), 1600);
    return () => clearTimeout(timer);
  }, [api, projectId, clip.job_id, clip.clip_index, record]);

  async function analyze(force = false) {
    setStarting(true); setError(''); if (record?.result) setPrevious(record);
    try {
      await flush?.();
      const data = await api.analyzeTrends(projectId, clip.job_id, clip.clip_index, { state, goal: record?.goal || DEFAULT_GOAL, topic: topic.trim(), ...(links.length ? { references: links } : {}), force });
      if (alive.current) { setRecord(data); setActive(0); }
    } catch (e) { if (alive.current) setError(friendly(e)); }
    finally { if (alive.current) setStarting(false); }
  }

  // ---------- the window behaves like a dialog: Esc, click outside, focus, background inert ----------
  const review = usePreview({ projectId, clip, state, researchId: (record?.result ? record : previous)?.id });
  const closeRef = useRef(onClose); const reviewRef = useRef(review);
  useEffect(() => { closeRef.current = onClose; reviewRef.current = review; });
  useEffect(() => {
    document.querySelectorAll('video, audio').forEach(m => m.pause());
    const previousFocus = document.activeElement;
    const others = Array.from(document.body.children).filter(n => n !== backdrop.current && n instanceof HTMLElement);
    const inert = others.map(n => n.inert); others.forEach(n => { n.inert = true; });
    const overflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
    sheet.current?.focus();
    const key = e => {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      if (reviewRef.current.preview) reviewRef.current.close(); else closeRef.current?.();
    };
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('keydown', key);
      others.forEach((n, i) => { n.inert = inert[i]; });
      document.body.style.overflow = overflow; previousFocus?.focus?.();
    };
  }, []);

  // ---------- derived view ----------
  const running = starting || record?.status === 'running';
  const analysis = record?.result ? record : previous || record;
  const view = viewData(analysis, state, info);
  const { result, references, suggestions } = view;
  const finished = Boolean(analysis?.result);
  const changed = finished && !running && !same(analysis.edit_state, state);
  const problem = error || (record?.status === 'error' ? problemText(record.message) : '');
  const examples = references.filter(r => r.kind !== 'tutorial');
  const tutorials = references.filter(r => r.kind === 'tutorial');
  const reference = examples[Math.min(active, examples.length - 1)];
  const multiple = examples.length >= 2;
  const modeLabel = multiple ? 'Trend Analysis' : 'Reference Comparison';
  const demo = /mock|fixture|offline/i.test(result.coverage || '');
  const checkedAt = result.checked_at || analysis?.researched_at;
  const time = useMemo(() => timelineClock(state), [state]);

  const editM = measuredVideo(result.edit_measured);
  const refMs = examples.map(r => measuredVideo(r.measured));
  const f = editFindings(state, info, editM);
  const cues = editCues(state, info);
  const music = musicSpans(state);
  const duration = editM?.duration ?? time.duration;
  const avgRange = range(refMs.map(m => m?.avgShot));
  const firstCut = refMs.map(m => (m?.cuts ? (m.cuts[0] ?? m.span) : null));
  const fastOpen = countWhere(firstCut, t => t <= 3);
  const quickShots = countWhere(refMs.map(m => m?.avgShot ?? null), v => v <= 2.5);
  const vertical = countWhere(refMs.map(m => (m?.width ? m.height > m.width : null)), Boolean);

  const toOutput = useCallback(at => (Number.isFinite(at) && kept(at, state) ? time.output(at) : null), [state, time]);
  const top = suggestions.slice(0, 3).map(s => {
    const out = toOutput(s.at);
    const when = ['captions', 'pause_removal'].includes(s.technique) || out == null ? null : s.technique === 'hook' ? [0, out] : [out, null];
    const cited = s.source_ids.length;
    const fallback = cited ? `Seen in ${cited} of ${references.length} reference${references.length === 1 ? '' : 's'}.` : 'AI suggestion based on your edit; no reference showed this directly.';
    const observed = {
      hook: f.firstWords != null ? `Your first spoken words start at ${secs(f.firstWords)}.${fastOpen.of ? ` ${fastOpen.hits} of ${fastOpen.of} reference${fastOpen.of === 1 ? '' : 's'} change shot within the first 3 s.` : ''}` : null,
      pause_removal: editM?.avgShot != null && avgRange ? `Your shots average ${secs(editM.avgShot)}; references average ${rangeText(avgRange)}.` : null,
      captions: f.captionCoverage != null ? (f.captionsOn ? `Captions are on screen for ${Math.round(f.captionCoverage * 100)}% of your edit.` : 'Captions are turned off in your edit.') : null,
      music: f.conflicts.length ? `Music may cover speech at ${f.conflicts.map(c => `${clock(c.start)}–${clock(c.end)}`).slice(0, 2).join(', ')}.` : f.hasMusic ? `Music plays at ${Math.round(f.musicLevel * 100)}% under speech.` : 'Your edit has no music track.',
      punch_in: editM?.cuts && avgRange ? `${editM.cuts.length} shot changes in your edit; references average a new shot every ${rangeText(avgRange)}.` : null,
      broll: editM?.cuts && avgRange ? `${editM.cuts.length} shot changes in your edit; references average a new shot every ${rangeText(avgRange)}.` : null,
    }[s.technique] || fallback;
    return { ...s, range: when, observed };
  });
  const strengths = view.strengths.map(text => ({ text }));

  // ---------- playback ----------
  const playing = useCallback(who => {
    setAudio(who);
    if (who === 'edit') refVideo.current?.pause(); else editVideo.current?.pause();
  }, []);
  function seekEdit(t) {
    setAudio('edit'); refVideo.current?.pause();
    workspace.current?.scrollIntoView({ behavior: simple ? 'auto' : 'smooth', block: 'start' });
    editVideo.current?.seek(t, true);
  }
  function seekRef(t) {
    setAudio('reference'); editVideo.current?.pause();
    workspace.current?.scrollIntoView({ behavior: simple ? 'auto' : 'smooth', block: 'start' });
    refVideo.current?.seek(t, true);
  }
  function compareOpenings() { editVideo.current?.restart(); refVideo.current?.restart(); }
  function openEditor(t) {
    if (Number.isFinite(t)) onOpenEditor?.(time.source(t)); else onOpenEditor?.();
  }
  function accept(p) {
    change?.(p.candidate);
    setAccepted(a => [...a, p.index]);
    review.close();
  }

  // ---------- add reference ----------
  function addLink(e) {
    e.preventDefault();
    const value = linkDraft.trim();
    if (!/(?:youtu\.be\/|youtube\.com\/(?:watch\?.*v=|shorts\/|embed\/|live\/))[\w-]{11}/.test(value)) { setLinkError('Paste a YouTube video or Shorts link.'); return; }
    if (links.length >= 3) { setLinkError('You can add up to 3 references.'); return; }
    setLinks(l => (l.includes(value) ? l : [...l, value])); setLinkDraft(''); setLinkError(''); setAdding(false);
  }

  const c = state.captions || {};
  const bindTarget = key => el => { targets.current[key] = el; };
  const timelineRows = [
    { id: 'edit', label: 'Your edit', color: EDIT_COLOR, cuts: editM?.cuts ?? null, span: editM?.span ?? duration, onSeek: seekEdit },
    ...examples.map((r, i) => ({ id: r.id, label: `Ref ${i + 1}`, color: REF_COLORS[i % 4], cuts: refMs[i]?.cuts ?? null, span: refMs[i]?.span ?? 0,
      onSeek: i === active ? seekRef : t => { setAudio('reference'); editVideo.current?.pause(); setActive(i); setStartAt(t); workspace.current?.scrollIntoView({ behavior: simple ? 'auto' : 'smooth', block: 'start' }); } })),
  ];
  const editTags = result.your_video_tags || {};
  const hookStyle = (() => { const v = examples.find(r => r.observed_tags?.hook_style)?.observed_tags.hook_style; return v ? String([].concat(v)[0]).slice(0, 80) : null; })();
  const refObservations = examples.flatMap((r, i) => (r.observed_tags?.visual_style ? [].concat(r.observed_tags.visual_style) : []).filter(v => /caption|text|subtitle|word|font/i.test(v)).map(v => [`Ref ${i + 1}`, v]));

  const status = <div className="ta-status">
    {running && <div className="ta-progress" role="status"><span className="ta-spinner" aria-hidden="true" /><div><strong>{starting ? 'Getting your clip ready…' : record?.message || 'Analyzing…'}</strong><small>This takes a few minutes. You can go back to editing and return.</small></div></div>}
    {problem && !running && <div className="ta-problem" role="alert"><p>{problem}</p><button type="button" className="btn btn-small" onClick={() => analyze(true)} disabled={!state}>Try again</button></div>}
    {changed && <p className="ta-note" role="status"><Icon name="alert" /> You’ve edited this clip since this analysis. Measurements describe the analyzed version; analyze again to include your changes.</p>}
    {demo && <p className="ta-note ta-note-demo"><Icon name="alert" /> Demonstration data — this report uses test fixtures, not live YouTube analysis.</p>}
  </div>;

  const body = !record && !error ? <div className="ta-loading" role="status" aria-label="Loading analysis">
    <div className="ta-skeleton" style={{ height: 320 }} /><div className="ta-skeleton" style={{ height: 120 }} /></div>
    : !finished ? <section className="ta-empty">
      <Icon name="sparkles" size={34} />
      <h2>{running ? 'Your comparison is on its way' : 'No comparison yet'}</h2>
      <p>{running ? 'We’re finding relevant videos on YouTube and measuring their cuts and audio next to yours.' : 'Analyze this clip to compare it with recent YouTube videos on the same topic. Analyzing never changes your edit.'}</p>
      {!running && <button type="button" className="btn btn-small btn-primary" onClick={() => analyze()} disabled={!state}><Icon name="sparkles" /> Analyze clip</button>}
    </section>
    : <>
      {/* The short version, from the guide */}
      <Reveal scrollRef={scrollRef} className="ta-section ta-verdict" aria-labelledby="ta-verdict-title">
        <Guide tone="done"><strong>Here’s what I found.</strong> {view.summary}</Guide>
        {top.length > 0 && <div className="ta-verdict-list"><h3 id="ta-verdict-title">The changes I’d make first</h3>
          <ol>{top.map(sug => <li key={sug.index}><b>{sug.title}</b><span>{sug.benefit || sug.shortText}</span></li>)}</ol></div>}
      </Reveal>

      <Step number={1} title="What’s trending right now" id="ta-trend-title">
        {examples.length ? `I looked at currently trending videos on “${result.search_topic || analysis.topic}” and ranked them by how fast they’re gaining views. Tap one to compare it with your edit.` : 'I couldn’t use any trending videos this time, so the rest is based on your edit alone.'}
      </Step>
      <Reveal scrollRef={scrollRef} className="ta-section" aria-labelledby="ta-trend-title">
        {examples.length > 0 ? <Viral references={examples} active={Math.min(active, examples.length - 1)} colors={REF_COLORS} onPick={i => { setStartAt(null); setActive(i); }} />
          : <p className="ta-unavailable">{whyNone(result.failures) || 'No recent videos matched.'} Try a broader topic, add a reference link above, or press Analyze again in a few minutes.</p>}
        <p className="ta-muted ta-small">“Views per hour” is a ranking proxy for what’s trending, not a measure of quality. All numbers are as YouTube reports them.</p>
      </Reveal>

      <Step number={2} title="What the most viral ones share" id="ta-share-title">
        {multiple ? 'These are the patterns that repeat across the videos above.' : 'One video isn’t a trend, so I’m showing what this one does. Add more reference links for repeated patterns.'}
      </Step>
      {/* 7. Reference patterns */}
      <Reveal scrollRef={scrollRef} className="ta-section" aria-labelledby="ta-patterns-title">
        <header className="ta-section-head"><div><small className="ta-eyebrow">{modeLabel}</small><h2 id="ta-patterns-title">{multiple ? 'What the trend has in common' : 'What this reference does'}</h2></div>
          <p className="ta-muted ta-head-note">{multiple ? `Repeated across ${examples.length} relevant videos.` : 'One reference isn’t a trend. Add more references to see repeated patterns.'}</p></header>
        <ul className="ta-patterns">
          {fastOpen.of > 0 && <li><b>{fastOpen.hits} of {fastOpen.of}</b> {fastOpen.of === 1 ? 'reference' : 'references'} change shot within the first 3 seconds <small>measured</small></li>}
          {quickShots.of > 0 && <li><b>{quickShots.hits} of {quickShots.of}</b> average a new shot every 2.5 s or faster <small>measured</small></li>}
          {vertical.of > 0 && <li><b>{vertical.hits} of {vertical.of}</b> are vertical (9:16-style) videos <small>measured</small></li>}
          {view.patterns.map(p => <li key={p}>{p} <small>observed</small></li>)}
          {!fastOpen.of && !quickShots.of && !view.patterns.length && <li className="ta-muted">No repeated patterns could be established from these references.</li>}
        </ul>
        {tutorials.length > 0 && <div className="ta-observations"><h4>Technique notes <span className="ta-muted">· from tutorials; explanations, not trend evidence</span></h4>
          <ul>{tutorials.flatMap(t => referenceLearning(t).map(x => <li key={t.id + x}>{x}</li>))}</ul></div>}
      </Reveal>


      <Step number={3} title="How your edit compares" id="ta-compare-step">
        Your edit sits next to the top trending video. The charts show cuts, pacing and sound for both.
      </Step>
      {/* 2. Video comparison workspace */}
      <Reveal scrollRef={scrollRef} className="ta-section ta-workspace" aria-labelledby="ta-compare-title">
        <header className="ta-section-head" ref={workspace}>
          <div><small className="ta-eyebrow">{modeLabel}</small><h2 id="ta-compare-title">Side by side</h2></div>
          <div className="ta-head-actions">
            <button type="button" className="btn btn-small" onClick={compareOpenings} disabled={!reference}><Icon name="repeat" /> Compare openings</button>
            <span className="ta-audio-pill" role="status"><Icon name="volume" /> Sound: {audio === 'edit' ? 'Your edit' : 'Reference'}</span>
          </div>
        </header>
        <div className="ta-compare">
          <article className="ta-panel" ref={bindTarget('video')}>
            <header><span className="ta-tag ta-tag-edit">Your Edit</span><h3>{clip.title || 'Untitled clip'}</h3>
              <p className="ta-muted">{clock(duration)} · {clip.sessionName || 'Your project'}</p></header>
            <EditVideo ref={editVideo} projectId={projectId} clip={clip} state={state} info={info} audible={audio === 'edit'} onPlay={playing} />
            <button type="button" className="ta-sound" aria-pressed={audio === 'edit'} onClick={() => playing('edit')}><Icon name={audio === 'edit' ? 'volume' : 'mute'} /> {audio === 'edit' ? 'Sound on' : 'Hear this one'}</button>
          </article>
          <article className="ta-panel">
            {reference ? <>
              <header><span className="ta-tag ta-tag-ref">Trending Reference{examples.length > 1 ? ` ${Math.min(active, examples.length - 1) + 1} of ${examples.length}` : ''}</span>
                <h3>{reference.title || 'Untitled video'}</h3>
                <p className="ta-muted">{reference.measured?.duration ? clock(reference.measured.duration) : 'Length not measured'} · {reference.user_added ? 'Added by you' : 'YouTube'}</p></header>
              {examples.length > 1 && <div className="ta-ref-tabs" role="tablist" aria-label="References">{examples.map((r, i) =>
                <button key={r.id} type="button" role="tab" aria-selected={i === active} className={i === active ? 'is-active' : ''} onClick={() => { setStartAt(null); setActive(i); }} style={{ '--series': REF_COLORS[i % 4] }}>Ref {i + 1}</button>)}</div>}
              <ReferenceVideo key={reference.id} ref={refVideo} reference={reference} start={startAt} audible={audio === 'reference'} onPlay={playing} />
              <button type="button" className="ta-sound" aria-pressed={audio === 'reference'} onClick={() => playing('reference')}><Icon name={audio === 'reference' ? 'volume' : 'mute'} /> {audio === 'reference' ? 'Sound on' : 'Hear this one'}</button>
              <ReferenceFacts reference={reference} checkedAt={checkedAt} topic={result.search_topic || analysis.topic} />
            </> : <div className="ta-unavailable ta-panel-empty"><Icon name="youtube" size={28} /><p>No example videos could be analyzed in this run{tutorials.length ? ' (only tutorials were found)' : ''}. Try again, change the topic, or add a reference link.</p></div>}
          </article>
        </div>
      </Reveal>

      {/* 3. At-a-glance findings */}
      <Reveal scrollRef={scrollRef} className="ta-section" aria-labelledby="ta-glance-title">
        {shown => <>
          <header className="ta-section-head"><div><small className="ta-eyebrow">At a glance</small><h2 id="ta-glance-title">Four measurements</h2></div>
            <p className="ta-muted ta-head-note">Measured from the video files and your edit’s settings. No scores or predictions.</p></header>
          <div className="ta-findings">
            <Finding shown={shown} cardRef={bindTarget('insight')} label="Time until the hook" value={f.firstWords} unit=" s" empty="No captions to time"
              refText={hookStyle && <span className="ta-observation">Observed: {hookStyle}</span>}
              note={`When your first spoken line begins.${top.find(s => s.technique === 'hook' && s.range) ? ` AI located the main point at ${clock(top.find(s => s.technique === 'hook').range[1])}.` : ''}`} />
            <Finding shown={shown} cardRef={bindTarget('pace')} label="Average shot length" value={editM?.avgShot} unit=" s"
              refText={rangeText(avgRange)} note={editM?.cuts ? `${editM.cuts.length} shot changes in ${secs(editM.span, 0)} of your edit.` : 'Analyze again to measure shot changes.'} />
            <Finding shown={shown} cardRef={bindTarget('caption')} label="Caption coverage" value={f.captionCoverage == null ? null : f.captionCoverage * 100} unit="%" format={v => Math.round(v).toString()}
              empty={info?.cues?.length ? 'Not measured' : 'No captions'} refText={<span className="ta-na">Not measured — on-screen text in YouTube videos isn’t detected</span>}
              note="Share of your runtime with a caption line on screen." />
            <Finding shown={shown} label="Speech and music balance" value={f.hasMusic ? f.musicLevel * 100 : 0} unit="%" format={v => Math.round(v).toString()}
              refText={<span className="ta-na">Not separable — references are mixed audio</span>}
              note={f.hasMusic ? `Music level under speech, relative to your voice. ${f.conflicts.length ? `${f.conflicts.length} moment${f.conflicts.length === 1 ? '' : 's'} may cover words.` : 'No moments where it likely covers words.'}` : 'No music in your edit, so speech is never covered.'} />
          </div>
        </>}
      </Reveal>

      {/* 4. Interactive analysis */}
      <Reveal scrollRef={scrollRef} className="ta-section" aria-labelledby="ta-detail-title">
        {shown => <>
          <header className="ta-section-head"><div><small className="ta-eyebrow">In detail</small><h2 id="ta-detail-title">Where the edits differ</h2></div>
            <p className="ta-muted ta-head-note">Click any marker to jump the video there.</p></header>
          <div className="ta-analysis">
            <div className="ta-col">
              <article className="ta-panel"><h3>Shot changes</h3><p className="ta-muted">Each tick is a cut detected in the video file.</p>
                <ShotTimeline rows={timelineRows} shown={shown} /></article>
              <article className="ta-panel"><h3>Pacing</h3><p className="ta-muted">Cuts per 5 seconds. Higher means faster cutting.</p>
                <PacingChart shown={shown} series={timelineRows.map(r => ({ id: r.id, label: r.label, color: r.color, cuts: r.cuts, span: r.span }))} /></article>
            </div>
            <div className="ta-col">
              <article className="ta-panel"><h3>Captions</h3><p className="ta-muted">Your caption style, as viewers see it.</p>
                {cues.length ? <div className="ta-captions">
                  <div className="ta-caption-examples">{cues.slice(0, 2).map(cue => <button type="button" key={cue.index} className="ta-caption-example" onClick={() => seekEdit(cue.start)} aria-label={`Play from ${clock(cue.start)}`}>
                    <CaptionSample captions={c} text={cue.text} emphasis={c.emphasis} /><span className="ta-stamp"><Icon name="play" /> {clock(cue.start)}</span></button>)}</div>
                  <dl className="ta-specs">
                    <div><dt>Size</dt><dd>{c.size ?? 32} px</dd></div><div><dt>Placement</dt><dd>{{ top: 'Top', middle: 'Middle', bottom: 'Bottom' }[c.position] || 'Bottom'}</dd></div>
                    <div><dt>Emphasis</dt><dd>{c.bold ? 'Bold' : 'Regular'}{c.emphasis?.length ? ` · ${c.emphasis.length} highlighted word${c.emphasis.length === 1 ? '' : 's'}` : ''}</dd></div>
                    <div><dt>Words per line</dt><dd>{c.max_words || 'Full line'}</dd></div>
                    <div><dt>Showing</dt><dd>{f.captionsOn ? 'On' : 'Off'}</dd></div>
                  </dl>
                </div> : <p className="ta-unavailable">This clip has no caption lines yet, so there’s nothing to compare. Add captions in the Editor’s Captions tab.</p>}
                <div className="ta-observations"><h4>In the references <span className="ta-muted">· written observations, from 5 sampled frames</span></h4>
                  {refObservations.length ? <ul>{refObservations.slice(0, 3).map(([who, text]) => <li key={who + text}><b>{who}:</b> {text}</li>)}</ul>
                    : <p className="ta-muted">No caption details were observed in the reference frames.</p>}</div>
              </article>
              <article className="ta-panel"><h3>Audio</h3><p className="ta-muted">Your edit’s loudness, with speech and music lanes. Shaded areas: music may cover speech.</p>
                <AudioChart shown={shown} duration={Math.max(1, duration)} loudness={editM?.loudness} window={editM?.window} cues={cues} music={music} conflicts={f.conflicts} onSeek={seekEdit}
                  references={examples.map((r, i) => ({ id: r.id, color: REF_COLORS[i % 4], loudness: refMs[i]?.loudness, window: refMs[i]?.window || .5 }))} />
                {editTags.audio_style && <p className="ta-observation">Observed in your edit: {[].concat(editTags.audio_style).join(', ')}</p>}
              </article>
            </div>
          </div>
        </>}
      </Reveal>


      <Step number={4} title="What I’d change" id="ta-change-step">
        Review each idea, preview it on your clip, and accept the ones you like. Nothing changes until you accept, and Undo in the Editor reverses it. These ideas aren’t a promise of more views.
      </Step>
      {/* 5. What's working / What to improve + 6. Review changes */}
      <Reveal scrollRef={scrollRef} className="ta-section ta-advice" aria-labelledby="ta-advice-title">
        {shown => <>
          <header className="ta-section-head"><div><small className="ta-eyebrow">Next steps</small><h2 id="ta-advice-title">What to keep, what to change</h2></div></header>
          <div className="ta-advice-grid">
            <article className="ta-panel ta-working"><h3><Icon name="checkCircle" /> What’s working</h3><Strengths items={strengths} onSeek={seekEdit} /></article>
            <article className="ta-panel ta-improve"><h3><Icon name="target" /> What to improve <span className="ta-muted">· top {top.length}</span></h3>
              {top.length ? <Improvements items={top} reveal={shown} onSeek={seekEdit} onOpenEditor={openEditor} canPreview={Boolean(change)}
                previewing={review.previewing} onPreview={review.open} /> : <p className="ta-unavailable">No changes were suggested for this edit.</p>}
              {accepted.length > 0 && <p className="ta-safe" role="status"><Icon name="check" /> {accepted.length} change{accepted.length === 1 ? '' : 's'} accepted. Use Undo in the Editor to reverse.</p>}
            </article>
          </div>
          <ChangePreview preview={review.preview} projectId={projectId} clip={clip} info={info} state={state} onAccept={accept} onClose={review.close} />
        </>}
      </Reveal>

      <footer className="ta-footnote">
        <p>{result.coverage || 'YouTube references only.'} This is guidance, not a prediction of how your clip will perform.</p>
        {view.evidenceWarning && <p>{view.evidenceWarning}</p>}
      </footer>
    </>;

  return createPortal(<div className="ta-backdrop" ref={backdrop} onMouseDown={e => { if (e.target === e.currentTarget && !review.preview) onClose?.(); }}>
   <div className="ta-sheet" ref={sheet} role="dialog" aria-modal="true" aria-labelledby="ta-title" tabIndex={-1}>
    <div className="ta-topbar">
      <span className="ta-mode"><Icon name="sparkles" /> {finished ? modeLabel : 'Trend Analysis'}</span>
      <button type="button" className="btn btn-small" onClick={onClose} aria-label="Close trend analysis"><Icon name="close" /> Close</button>
    </div>
    <div className="ta-scroll" ref={scrollRef}>
      <header className="ta-hero ta-hero-compact">
        <div className="ta-hero-copy">
          <small className="ta-eyebrow ta-eyebrow-light">Trends · {clip.title || 'This clip'}</small>
          <h1 id="ta-title">What’s working right now. <span>Make your edit better.</span></h1>
          <p className="ta-lede">Cascade looks at currently trending videos on your topic, finds what the most viral ones have in common, compares them with your edit, and suggests specific changes.</p>
        <form className="ta-controls" onSubmit={e => { e.preventDefault(); analyze(); }}>
          <label className="ta-field"><span>Edited video</span>
            <select value={`${clip.job_id}:${clip.clip_index}`} onChange={e => onSelectClip?.(clips.find(x => `${x.job_id}:${x.clip_index}` === e.target.value))} disabled={!onSelectClip || clips.length < 2}>
              {(clips.length ? clips : [clip]).map((x, i) => <option key={`${x.job_id}:${x.clip_index}`} value={`${x.job_id}:${x.clip_index}`}>{i + 1}. {x.title || 'Clip'}</option>)}
            </select></label>
          <label className="ta-field ta-field-grow"><span>Topic</span>
            <input value={topic} onChange={e => setTopic(e.target.value)} maxLength={160} placeholder={analysis?.topic || 'Detected from your clip'} /></label>
          <div className="ta-control-actions">
            <button type="button" className="btn btn-small" onClick={() => setAdding(a => !a)} aria-expanded={adding}><Icon name="plus" /> Add Reference</button>
            <button type="submit" className="btn btn-small btn-primary" disabled={running || !state}><Icon name="sparkles" /> {running ? 'Analyzing…' : finished ? 'Analyze again' : 'Analyze'}</button>
          </div>
        </form>
        {adding && <form className="ta-add" onSubmit={addLink}>
          <label htmlFor="ta-link">Paste a YouTube link</label>
          <div><input id="ta-link" value={linkDraft} onChange={e => setLinkDraft(e.target.value)} placeholder="https://youtube.com/shorts/…" autoFocus />
            <button type="submit" className="btn btn-small">Add</button></div>
          {linkError && <small role="alert" className="ta-error">{linkError}</small>}
          <small className="ta-muted"><Icon name="alert" /> Uploading a reference file isn’t available yet — links only.</small>
        </form>}
        {links.length > 0 && <ul className="ta-chips" aria-label="References you added">{links.map(l => <li key={l}>{l.replace(/^https?:\/\/(www\.)?/, '').slice(0, 38)}
          <button type="button" aria-label={`Remove ${l}`} onClick={() => setLinks(x => x.filter(y => y !== l))}><Icon name="close" /></button></li>)}
          <li className="ta-muted">Used on the next Analyze</li></ul>}
        </div>
        <Guide big live tone={problem && !running ? 'warn' : 'info'}>
          {running ? <>I’m on it. {record?.message || 'Starting…'}</>
            : problem ? <>That didn’t work, but your clip is safe. {problem}</>
            : finished ? <>All done! I found {examples.length ? `${examples.length} trending video${examples.length === 1 ? '' : 's'}` : 'no trending videos this time'} and compared them with your edit. Scroll down, I’ll walk you through it.</>
            : <>Hi, I’m your Cascade guide! Pick a topic (or leave it blank) and press Analyze. I’ll look at what’s trending, find what the most viral videos share, and show you how to improve your edit.</>}
        </Guide>
      </header>
      <main className="ta-main">{status}{body}</main>
    </div>
   </div>
  </div>, document.body);
}
