// "What's working", "What to improve" and the preview/accept flow for one change at a time.
// Previewing never touches the draft. Accepting goes through the editor's normal change(), so
// Undo in the editor reverses it.
import { useEffect, useRef } from 'react';
import Icon from '../../../components/ui/Icon';
import { describeChanges } from '../chatChanges';
import { EditVideo } from './TrendVideos';
import { clock } from './trendMetrics';

function Stamp({ range, onSeek }) {
  if (!range) return <span className="ta-stamp ta-stamp-quiet">Whole clip</span>;
  return <button type="button" className="ta-stamp" onClick={() => onSeek(range[0])} aria-label={`Play your edit from ${clock(range[0])}`}>
    <Icon name="play" /> {clock(range[0])}{range[1] != null && range[1] - range[0] >= 1 ? `–${clock(range[1])}` : ''}
  </button>;
}

export function Strengths({ items, onSeek }) {
  if (!items.length) return <p className="ta-unavailable">No clear strengths were identified in this analysis.</p>;
  return <ul className="ta-strengths">{items.map(item => <li key={item.text}>
    <Icon name="checkCircle" />
    <div><p>{item.text}</p>{item.range && <Stamp range={item.range} onSeek={onSeek} />}{item.measured && <small className="ta-muted">{item.measured}</small>}</div>
  </li>)}</ul>;
}

export function Improvements({ items, onSeek, onOpenEditor, canPreview, previewing, onPreview, reveal }) {
  return <ol className="ta-recs">{items.map((s, i) => <li key={s.index} className={`ta-rec ta-reveal${reveal ? ' is-in' : ''}`} style={{ '--i': i }}>
    <span className="ta-rec-rank" aria-hidden="true">{i + 1}</span>
    <div className="ta-rec-body">
      <header><h4>{s.title}</h4><Stamp range={s.range} onSeek={onSeek} /></header>
      <dl>
        <div><dt>Observed difference</dt><dd>{s.observed}</dd></div>
        <div><dt>Suggested change</dt><dd>{s.shortText}</dd></div>
        {s.benefit && <div><dt>Why it may help</dt><dd>{s.benefit}</dd></div>}
      </dl>
      <div className="ta-rec-actions">
        {s.unavailable_reason || !canPreview
          ? <span className="ta-unavailable-inline" title={s.unavailable_reason || undefined}><Icon name="alert" /> {s.unavailable_reason ? 'Preview unavailable: ' + s.unavailable_reason : 'Preview is available in the Editor'}</span>
          : <button type="button" className="btn btn-small btn-primary" onClick={() => onPreview(s)} disabled={previewing != null} aria-haspopup="dialog">
            <Icon name="sparkles" /> {previewing === s.index ? 'Preparing preview…' : 'Preview change'}</button>}
        <button type="button" className="btn btn-small" onClick={() => onOpenEditor(s.range?.[0])}><Icon name="pencil" /> Open in Editor</button>
      </div>
    </div>
  </li>)}</ol>;
}

/** One suggested change: rendered preview + the exact edits, then Accept or Discard. */
export function ChangePreview({ preview, projectId, clip, info, state, onAccept, onClose }) {
  const box = useRef(null);
  const index = preview?.index;
  useEffect(() => { if (index != null) box.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [index]);
  if (!preview) return null;
  const changes = preview.candidate ? describeChanges(state, preview.candidate) : [];
  return <section ref={box} className="ta-review" role="dialog" aria-modal="false" aria-labelledby="ta-review-title">
    <header>
      <div><small className="ta-eyebrow">Review change</small><h3 id="ta-review-title">{preview.title}</h3></div>
      <button type="button" className="btn btn-small btn-ghost" onClick={onClose} aria-label="Close preview"><Icon name="close" /></button>
    </header>
    {preview.status === 'loading' && <div className="ta-progress" role="status"><span className="ta-spinner" aria-hidden="true" /> Building this change on a copy of your edit…</div>}
    {preview.status === 'error' && <p className="ta-problem" role="alert">{preview.message}</p>}
    {preview.status === 'ready' && (preview.candidate ? <div className="ta-review-grid">
      <EditVideo projectId={projectId} clip={clip} info={info} state={preview.candidate} audible />
      <div className="ta-review-text">
        <h4>What changes</h4>
        {changes.length ? <ul>{changes.map(c => <li key={c}>{c}</li>)}</ul> : <p className="ta-muted">Settings changed without a visible summary.</p>}
        {preview.message && <p className="ta-muted">{preview.message}</p>}
        <p className="ta-safe"><Icon name="checkCircle" /> Speaker audio stays untouched and cuts keep complete sentences. Undo in the Editor reverses this.</p>
        <div className="ta-rec-actions">
          <button type="button" className="btn btn-small btn-primary" onClick={() => onAccept(preview)}><Icon name="check" /> Accept change</button>
          <button type="button" className="btn btn-small" onClick={onClose}>Discard</button>
        </div>
      </div>
    </div> : <p className="ta-unavailable">{preview.message || 'This suggestion didn’t change the edit.'}</p>)}
  </section>;
}
