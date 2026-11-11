// "Your Edit" and "Trending Reference", side by side in equal panels.
// Each plays on its own; "Compare openings" restarts both. Only one of them is ever heard.
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import useApi from '../../../api/useApi';
import Icon from '../../../components/ui/Icon';
import { clipMediaPath } from '../clips';
import { timelineClock } from '../reelTiming';
import { aspect, clock } from './trendMetrics';

const RATIOS = { '9:16': 9 / 16, '1:1': 1, '4:5': 4 / 5, '16:9': 16 / 9, '4:3': 4 / 3 };
const number = n => (Number.isFinite(n) ? Intl.NumberFormat(undefined, { notation: n >= 10000 ? 'compact' : 'standard' }).format(n) : null);
const day = iso => { const d = new Date(iso); return iso && !Number.isNaN(d.getTime()) ? d.toLocaleDateString(undefined, { timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric' }) : null; };

/** Your edit: the same server render the Editor previews (falls back to the source while it renders). */
export const EditVideo = forwardRef(function EditVideo({ projectId, clip, state, info, audible, onPlay }, ref) {
  const api = useApi();
  const video = useRef(null);
  const [source, setSource] = useState(null), [rendered, setRendered] = useState(null), [problem, setProblem] = useState('');
  const time = useMemo(() => timelineClock(state), [state]);
  const snapshot = JSON.stringify(state);
  useEffect(() => {
    let active = true, url;
    api.getMedia(clipMediaPath(projectId, clip)).then(blob => { url = URL.createObjectURL(blob); if (active) setSource(url); }).catch(e => active && setProblem(e.message));
    return () => { active = false; if (url) URL.revokeObjectURL(url); };
  }, [api, projectId, clip]);
  useEffect(() => {
    let active = true, url;
    api.exportClip(projectId, clip.job_id, clip.clip_index, JSON.parse(snapshot))
      .then(blob => { url = URL.createObjectURL(blob); if (active) setRendered(url); })
      .catch(() => {}); // the source keeps playing; the note below says so
    return () => { active = false; if (url) URL.revokeObjectURL(url); };
  }, [api, projectId, clip.job_id, clip.clip_index, snapshot]);
  useImperativeHandle(ref, () => ({
    seek(t, play = false) { // t = seconds in the edited video
      const v = video.current; if (!v) return;
      v.currentTime = rendered ? t : time.source(t);
      if (play) v.play().catch(() => {});
    },
    restart() { this.seek(0, true); },
    pause() { video.current?.pause(); },
  }), [rendered, time]);
  const ratio = state.composition?.ratio && state.composition.ratio !== 'original' ? RATIOS[state.composition.ratio] : aspect(info?.width, info?.height, 16 / 9);
  return <div className="ta-player" style={{ '--ar': ratio }}>
    {problem ? <p className="ta-unavailable" role="alert">This video couldn’t load: {problem}</p>
      : !source && !rendered ? <div className="ta-skeleton ta-player-frame" aria-label="Loading your edit" />
      : <video ref={video} className="ta-player-frame" src={rendered || source} controls playsInline muted={!audible} preload="metadata"
          onLoadedMetadata={e => { if (!rendered) e.currentTarget.currentTime = state.start; }}
          onPlay={() => onPlay?.('edit')} aria-label="Your edit" />}
    <small className="ta-player-note">{rendered ? 'Rendered edit · same file Export saves' : 'Rendering your edit… showing the original source until it’s ready'}</small>
  </div>;
});

/** A YouTube reference, controlled through the embed's postMessage API (no extra script). */
export const ReferenceVideo = forwardRef(function ReferenceVideo({ reference, audible, onPlay, start }, ref) {
  const frame = useRef(null);
  const id = reference.video_id || reference.id;
  const send = (func, args = []) => frame.current?.contentWindow?.postMessage(JSON.stringify({ event: 'command', func, args }), '*');
  useImperativeHandle(ref, () => ({
    seek(t, play = false) { send('seekTo', [t, true]); if (play) send('playVideo'); },
    restart() { send('seekTo', [0, true]); send('playVideo'); },
    pause() { send('pauseVideo'); },
  }));
  useEffect(() => { send(audible ? 'unMute' : 'mute'); }, [audible]);
  useEffect(() => {
    function listen(event) {
      if (!/youtube(-nocookie)?\.com$/.test(new URL(event.origin).hostname) || event.source !== frame.current?.contentWindow) return;
      try {
        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
        const state = data?.event === 'onStateChange' ? data.info : data?.info?.playerState;
        if (state === 1) onPlay?.('reference');
      } catch { /* not a player message */ }
    }
    window.addEventListener('message', listen);
    return () => window.removeEventListener('message', listen);
  }, [onPlay]);
  const hello = () => {
    frame.current?.contentWindow?.postMessage(JSON.stringify({ event: 'listening', id, channel: 'widget' }), '*');
    send(audible ? 'unMute' : 'mute');
  };
  const m = reference.measured || {};
  const origin = typeof window !== 'undefined' ? encodeURIComponent(window.location.origin) : '';
  return <div className="ta-player" style={{ '--ar': aspect(m.width, m.height) }}>
    <iframe ref={frame} className="ta-player-frame" title={`Reference: ${reference.title || 'YouTube video'}`} onLoad={hello}
      src={`https://www.youtube-nocookie.com/embed/${id}?enablejsapi=1&playsinline=1&rel=0&modestbranding=1&origin=${origin}${Number.isFinite(start) ? `&start=${Math.floor(start)}&autoplay=1` : ''}`}
      allow="autoplay; encrypted-media; picture-in-picture" allowFullScreen loading="lazy" />
    <small className="ta-player-note">Plays from YouTube · {reference.channel || 'Unknown channel'}</small>
  </div>;
});

/** Why this reference, and the engagement YouTube reported when it was checked. */
export function ReferenceFacts({ reference, checkedAt, topic }) {
  const facts = [
    ['Posted', day(reference.published_at)],
    ['Views', number(reference.view_count)],
    ['Likes', number(reference.like_count)],
    ['Comments', number(reference.comment_count)],
  ];
  const reasons = [reference.user_added ? 'You added this reference' : topic && `Matches your topic: “${topic}”`,
    reference.measured?.duration && `${clock(reference.measured.duration)} long`,
    reference.measured?.height > reference.measured?.width && 'Vertical short-form format'].filter(Boolean);
  return <div className="ta-facts">
    <p className="ta-why"><Icon name="target" /> <span><strong>Why this reference:</strong> {reference.selected_reason || reasons.join(' · ') || 'Found by searching YouTube for recent videos on your topic.'}</span></p>
    {reference.selected_reason && reasons.length > 0 && <p className="ta-reason-tags">{reasons.map(r => <span key={r}>{r}</span>)}</p>}
    <dl>{facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? <span className="ta-muted">Not available</span>}</dd></div>)}</dl>
    <small className="ta-muted">{checkedAt ? `Last checked ${new Date(checkedAt * 1000).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}` : 'Check time not recorded'} · Engagement as reported by YouTube.</small>
  </div>;
}
