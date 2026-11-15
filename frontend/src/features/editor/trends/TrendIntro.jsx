// The opening composition: four analysis panels floating at slightly different depths.
// As you scroll into the workspace they glide into the dashboard spots they stand for and fade
// into the real panels there, so the analysis visibly "comes together". Scrolling stays native:
// we only read scrollTop and set transforms. Phones and reduced-motion get a still version.
import { useEffect, useRef } from 'react';
import { clock } from './trendMetrics';

const PANELS = [
  { key: 'video', depth: 1.0, rotate: -3.5 },
  { key: 'pace', depth: 0.55, rotate: 2.5 },
  { key: 'caption', depth: 0.8, rotate: -1.5 },
  { key: 'insight', depth: 0.35, rotate: 3 },
];

export default function TrendIntro({ scrollRef, targets, simple, settle = true, children, thumbnail, title, pace, caption, insight }) {
  const hero = useRef(null);
  const slots = useRef({});
  const flyers = useRef({});

  // Scroll-driven settle (desktop only)
  useEffect(() => {
    const root = scrollRef.current;
    if (!root || simple) {
      Object.values(flyers.current).forEach(el => { if (el) { el.style.transform = ''; el.style.opacity = ''; } });
      return undefined;
    }
    let frame = 0;
    const update = () => {
      frame = 0;
      const height = hero.current?.offsetHeight || 1;
      // Nothing to settle into yet (no analysis): the panels just float.
      const p = settle ? Math.max(0, Math.min(1, root.scrollTop / (height * 0.9))) : 0;
      const eased = p * p * (3 - 2 * p);
      for (const { key, depth, rotate } of PANELS) {
        const slot = slots.current[key], fly = flyers.current[key], target = targets.current?.[key];
        if (!slot || !fly) continue;
        let dx = 0, dy = 0, scale = 1;
        if (target && settle) {
          const a = slot.getBoundingClientRect(), b = target.getBoundingClientRect();
          scale = Math.max(0.6, Math.min(2.2, b.width / Math.max(1, a.width)));
          dx = b.left - a.left; dy = b.top - a.top;
        }
        const lift = (1 - eased) * depth * -18; // deeper panels drift a little more (parallax)
        fly.style.transform = `translate3d(${dx * eased}px, ${dy * eased + lift}px, 0) scale(${1 + (scale - 1) * eased}) rotate(${rotate * (1 - eased)}deg)`;
        fly.style.opacity = String(p < 0.7 ? 1 : Math.max(0, 1 - (p - 0.7) / 0.3));
        fly.style.visibility = p >= 1 ? 'hidden' : '';
      }
    };
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(update); };
    update();
    root.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => { root.removeEventListener('scroll', onScroll); window.removeEventListener('resize', onScroll); cancelAnimationFrame(frame); };
  }, [scrollRef, targets, simple, settle]);

  // Small pointer parallax (desktop only). Only runs while the pointer moves; nothing loops.
  function drift(event) {
    if (simple) return;
    const box = hero.current.getBoundingClientRect();
    hero.current.style.setProperty('--mx', ((event.clientX - box.left) / box.width - 0.5).toFixed(3));
    hero.current.style.setProperty('--my', ((event.clientY - box.top) / box.height - 0.5).toFixed(3));
  }
  function rest() { hero.current?.style.setProperty('--mx', 0); hero.current?.style.setProperty('--my', 0); }

  const max = Math.max(1, ...pace.values);
  const panel = { // what each floating panel shows
    video: <div className="ta-float-card ta-float-video">
      {thumbnail ? <img src={thumbnail} alt="" /> : <div className="ta-float-thumb" />}
      <span className="ta-float-play" aria-hidden="true">▶</span>
      <strong>{title || 'Your edit'}</strong>
    </div>,
    pace: <div className="ta-float-card ta-float-pace">
      <small>Cuts per 5 s{pace.sample && <em className="ta-sample">Sample</em>}</small>
      <div className="ta-float-bars">{pace.values.map((v, i) => <i key={i} style={{ '--h': v / max, '--i': i }} />)}</div>
    </div>,
    caption: <div className="ta-float-card ta-float-caption">
      <small>Caption sample{caption.sample && <em className="ta-sample">Sample</em>}</small>
      <p style={caption.style}>{caption.text}</p>
    </div>,
    insight: <div className="ta-float-card ta-float-insight">
      <small>Insight{insight.sample && <em className="ta-sample">Sample</em>}</small>
      <strong>{insight.title}</strong>
      {insight.range && <span className="ta-stamp">{clock(insight.range[0])}{insight.range[1] != null ? `–${clock(insight.range[1])}` : ''}</span>}
    </div>,
  };

  return <section className={`ta-hero${simple ? ' is-simple' : ''}`} ref={hero} onPointerMove={drift} onPointerLeave={rest}>
    <div className="ta-hero-copy">{children}</div>
    <div className="ta-float-stage" aria-hidden="true">
      {PANELS.map(({ key, depth }) => <div key={key} className={`ta-float-slot ta-slot-${key}`} ref={el => { slots.current[key] = el; }}>
        <div className="ta-float-fly" ref={el => { flyers.current[key] = el; }}>
          <div className="ta-float-drift" style={{ '--depth': depth }}>{panel[key]}</div>
        </div>
      </div>)}
    </div>
  </section>;
}
