import Icon from '../../../components/ui/Icon';

const nf = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 });
const count = v => (Number.isFinite(v) ? nf.format(v) : null);
function age(iso) {
  const ms = Date.now() - new Date(iso || '').getTime();
  if (!Number.isFinite(ms) || ms < 0) return null;
  const days = Math.floor(ms / 864e5);
  return days < 1 ? 'today' : days === 1 ? '1 day ago' : `${days} days ago`;
}

/** The trending references ranked by views per hour, drawn as bars. Every number is as YouTube reports it. */
export default function Viral({ references, active, onPick, colors }) {
  if (!references.length) return null;
  const top = Math.max(...references.map(r => r.views_per_hour || 0), 1);
  return <ol className="ta-viral" aria-label="Trending videos, fastest growing first">
    {references.map((r, i) => {
      const rate = r.views_per_hour;
      const facts = [[count(r.view_count), 'views'], [count(r.like_count), 'likes'], [count(r.comment_count), 'comments']].filter(([v]) => v != null);
      return <li key={r.id} className={i === active ? 'is-active' : ''} style={{ '--series': colors[i % colors.length] }}>
        <button type="button" className="ta-viral-main" onClick={() => onPick?.(i)} aria-pressed={i === active}>
          <span className="ta-viral-rank">{i + 1}</span>
          <span className="ta-viral-text"><strong>{r.title || 'Untitled video'}</strong>
            <small>{[r.channel, age(r.published_at), r.user_added && 'Added by you'].filter(Boolean).join(' · ')}</small></span>
        </button>
        <div className="ta-viral-bar" title={rate ? `${Math.round(rate).toLocaleString()} views per hour since it was posted` : 'No upload time reported'}>
          <i style={{ width: `${rate ? Math.max(6, (rate / top) * 100) : 0}%` }} />
          <span>{rate ? `${count(rate)} views/hour` : 'Rate not available'}</span>
        </div>
        <p className="ta-viral-facts">{facts.length ? facts.map(([v, l]) => <span key={l}><b>{v}</b> {l}</span>) : <span className="ta-muted">No engagement numbers reported</span>}</p>
        {r.url && <a className="ta-viral-link" href={r.url} target="_blank" rel="noreferrer" aria-label={`Open ${r.title || 'video'} on YouTube`}><Icon name="youtube" /> Watch</a>}
      </li>;
    })}
  </ol>;
}
