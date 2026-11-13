// Charts for the Trend Analysis page. All of them draw measured data only, draw themselves once
// when they first appear, and show a floating tooltip for the exact point under the pointer/focus.
import { useEffect, useRef, useState } from 'react';
import { clock, pacing, secs } from './trendMetrics';

const pct = (t, max) => `${Math.max(0, Math.min(100, (t / max) * 100))}%`;

function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/** The floating card that follows a hovered data point. x/y are px inside the chart box. */
export function Tooltip({ tip }) {
  if (!tip) return null;
  return <div className="ta-tooltip" role="tooltip" style={{ left: tip.x, top: tip.y }}>
    {tip.title && <strong>{tip.title}</strong>}
    {tip.lines.map(line => <span key={line}>{line}</span>)}
  </div>;
}

/** Where each video cuts: one row per video, a tick per shot change. Click a tick to jump there. */
export function ShotTimeline({ rows, shown }) {
  const box = useRef(null);
  const [tip, setTip] = useState(null);
  const max = Math.max(1, ...rows.map(r => r.span || 0));
  const show = (event, row, t, i) => {
    const area = box.current.getBoundingClientRect(), mark = event.currentTarget.getBoundingClientRect();
    const next = row.cuts[i + 1] ?? row.span;
    setTip({ x: mark.left - area.left + mark.width / 2, y: mark.top - area.top - 6, title: `${row.label} · cut ${i + 1}`,
      lines: [`At ${secs(t, 2)} (${clock(t)})`, `Next shot lasts ${secs(next - t)}`] });
  };
  const ticks = [];
  for (let t = 0; t <= max + 0.01; t += max > 40 ? 10 : 5) ticks.push(t);
  return <div className={`ta-timeline${shown ? ' is-drawn' : ''}`} ref={box} onPointerLeave={() => setTip(null)}>
    {rows.map(row => <div className="ta-timeline-row" key={row.id}>
      <span className="ta-timeline-label"><i style={{ background: row.color }} />{row.label}</span>
      <div className="ta-timeline-track" style={{ '--row': row.color }}>
        {row.cuts == null ? <span className="ta-unavailable-inline">Cuts not measured for this video</span> : <>
          <span className="ta-timeline-extent" style={{ width: pct(row.span, max) }} />
          {row.cuts.map((t, i) => <button type="button" key={t} className="ta-cut" style={{ left: pct(t, max), '--i': i }}
            aria-label={`${row.label}: cut at ${secs(t, 2)}. ${row.onSeek ? 'Jump there.' : ''}`}
            onPointerEnter={e => show(e, row, t, i)} onFocus={e => show(e, row, t, i)} onBlur={() => setTip(null)}
            onClick={() => row.onSeek?.(t)} disabled={!row.onSeek} />)}
          {row.cuts.length === 0 && <span className="ta-unavailable-inline">No shot changes detected</span>}
        </>}
      </div>
    </div>)}
    <div className="ta-axis" aria-hidden="true">{ticks.map(t => <span key={t} style={{ left: pct(t, max) }}>{clock(t)}</span>)}</div>
    <Tooltip tip={tip} />
  </div>;
}

/** Cuts per 5 seconds for each video, as lines. */
export function PacingChart({ series, shown, window = 5 }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const height = 190, pad = { l: 34, r: 12, t: 14, b: 28 };
  const lines = series.filter(s => s.cuts != null).map(s => ({ ...s, points: pacing(s.cuts, s.span, window) }));
  const maxT = Math.max(window, ...lines.map(s => s.span));
  const maxY = Math.max(2, ...lines.flatMap(s => s.points.map(p => p.count)));
  const w = Math.max(0, width - pad.l - pad.r), h = height - pad.t - pad.b;
  const x = t => pad.l + (t / maxT) * w, y = c => pad.t + h - (c / maxY) * h;
  const mid = p => (p.t + p.end) / 2;
  const bins = Math.ceil(maxT / window);
  if (!lines.length) return <p className="ta-unavailable">Shot changes weren’t measured for these videos, so pacing can’t be charted. Analyze again to measure them.</p>;
  const tip = hover == null ? null : {
    x: x(hover * window + window / 2), y: pad.t - 4, title: `${clock(hover * window)}–${clock((hover + 1) * window)}`,
    lines: lines.filter(s => s.points[hover]).map(s => `${s.label}: ${s.points[hover].count} cut${s.points[hover].count === 1 ? '' : 's'}`),
  };
  return <div className={`ta-chart${shown ? ' is-drawn' : ''}`} ref={ref} onPointerLeave={() => setHover(null)}>
    {width > 0 && <svg width={width} height={height} role="img" aria-label={`Cuts per ${window} seconds. ${lines.map(s => `${s.label}: ${s.points.map(p => p.count).join(', ')}`).join('. ')}`}>
      {Array.from({ length: maxY + 1 }, (_, c) => c).filter(c => c % Math.ceil(maxY / 4) === 0).map(c => <g key={c} className="ta-grid">
        <line x1={pad.l} x2={width - pad.r} y1={y(c)} y2={y(c)} /><text x={pad.l - 8} y={y(c) + 4} textAnchor="end">{c}</text>
      </g>)}
      {Array.from({ length: bins + 1 }, (_, i) => i * window).filter((t, i) => i % Math.ceil(bins / 6) === 0).map(t =>
        <text key={t} className="ta-grid" x={x(t)} y={height - 8} textAnchor="middle">{clock(t)}</text>)}
      {hover != null && <line className="ta-guide" x1={x(hover * window + window / 2)} x2={x(hover * window + window / 2)} y1={pad.t} y2={pad.t + h} />}
      {lines.map(s => <g key={s.id} style={{ '--series': s.color }}>
        <path className="ta-line" pathLength="1" d={s.points.map((p, i) => `${i ? 'L' : 'M'}${x(mid(p))},${y(p.count)}`).join(' ')} />
        {s.points.map((p, i) => <circle key={p.t} className={`ta-dot${hover === i ? ' is-hot' : ''}`} cx={x(mid(p))} cy={y(p.count)} r={hover === i ? 5 : 3.5} />)}
      </g>)}
      {Array.from({ length: bins }, (_, i) => <rect key={i} className="ta-hit" x={x(i * window)} y={pad.t} width={Math.max(1, x(window) - x(0))} height={h}
        tabIndex={0} aria-label={`${clock(i * window)} to ${clock((i + 1) * window)}`} onPointerEnter={() => setHover(i)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} />)}
    </svg>}
    <Tooltip tip={tip} />
  </div>;
}

/** Your edit's loudness with where people talk and where music plays; red-brown where music may cover words. */
export function AudioChart({ duration, loudness, window = 0.5, cues, music, conflicts, references = [], onSeek, shown }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const height = 170, pad = { l: 40, r: 12, t: 12, b: 50 };
  const w = Math.max(0, width - pad.l - pad.r), h = height - pad.t - pad.b;
  const x = t => pad.l + (Math.min(t, duration) / duration) * w;
  const y = db => pad.t + h - ((Math.max(-60, db) + 60) / 60) * h;
  const area = loudness?.length ? `M${x(0)},${y(-60)} ` + loudness.map((db, i) => `L${x((i + .5) * window)},${y(db)}`).join(' ') + ` L${x(Math.min(duration, loudness.length * window))},${y(-60)} Z` : null;
  const at = t => ({ db: loudness?.[Math.floor(t / window)], speech: cues.find(c => t >= c.start && t < c.end), song: music.find(m => t >= m.start && t < m.end) });
  function move(event) {
    const box = event.currentTarget.getBoundingClientRect();
    const t = ((event.clientX - box.left - pad.l) / w) * duration;
    setHover(t >= 0 && t <= duration ? t : null);
  }
  const info = hover == null ? null : at(hover);
  const tip = info && {
    x: x(hover), y: pad.t - 4, title: clock(hover) + ` (${secs(hover)})`,
    lines: [Number.isFinite(info.db) ? `Loudness ${info.db} dBFS` : 'Loudness not measured',
      info.speech ? `Speech: “${info.speech.text.slice(0, 42)}${info.speech.text.length > 42 ? '…' : ''}”` : 'No caption line here',
      info.song ? `Music at ${Math.round(info.song.underSpeech * 100)}% while speaking` : 'No music'],
  };
  const lanes = [['Speech', cues, 'ta-lane-speech'], ['Music', music, 'ta-lane-music']];
  return <div className={`ta-chart ta-audio${shown ? ' is-drawn' : ''}`} ref={ref} onPointerLeave={() => setHover(null)}>
    {width > 0 && <svg width={width} height={height} role="img" aria-label={`Your edit's audio over ${secs(duration)}. ${conflicts.length} moment${conflicts.length === 1 ? '' : 's'} where music may cover speech.`}
      onPointerMove={move}>
      {[-60, -30, 0].map(db => <g key={db} className="ta-grid"><line x1={pad.l} x2={width - pad.r} y1={y(db)} y2={y(db)} /><text x={pad.l - 6} y={y(db) + 4} textAnchor="end">{db}</text></g>)}
      {conflicts.map(c => <rect key={c.start} className="ta-conflict" x={x(c.start)} y={pad.t} width={Math.max(2, x(c.end) - x(c.start))} height={h} />)}
      {area ? <path className="ta-area" d={area} /> : <text className="ta-grid" x={pad.l + 8} y={pad.t + h / 2}>Loudness not measured for this analysis</text>}
      {references.filter(r => r.loudness?.length).map(r => <path key={r.id} className="ta-ref-line" style={{ '--series': r.color }} pathLength="1"
        d={r.loudness.filter((_, i) => i * r.window <= duration).map((db, i) => `${i ? 'L' : 'M'}${x((i + .5) * r.window)},${y(db)}`).join(' ')} />)}
      {lanes.map(([label, spans, className], lane) => <g key={label} className={className}>
        <text className="ta-grid" x={pad.l - 6} y={pad.t + h + 16 + lane * 16} textAnchor="end">{label}</text>
        {spans.map(s => <rect key={s.start + label} x={x(s.start)} y={pad.t + h + 8 + lane * 16} width={Math.max(2, x(s.end) - x(s.start))} height={10} rx={3} />)}
      </g>)}
      {hover != null && <line className="ta-guide" x1={x(hover)} x2={x(hover)} y1={pad.t} y2={pad.t + h} />}
    </svg>}
    <Tooltip tip={tip} />
    {conflicts.length > 0 && <div className="ta-annotations">{conflicts.map(c =>
      <button type="button" key={c.start} className="ta-stamp ta-stamp-warn" onClick={() => onSeek?.(c.start)}>
        {clock(c.start)}–{clock(c.end)} <span>music at {Math.round(c.ratio * 100)}% of speech</span>
      </button>)}</div>}
  </div>;
}
