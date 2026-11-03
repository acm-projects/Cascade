import { useEffect, useState } from 'react';
import useApi from '../../api/useApi';
import { audioAssetPath } from '../../api/editor';
import { audioPeaks, thumbnailTimes, waveformPath } from './timelineLayout';

function mediaEvent(element, name, signal) {
  return new Promise((resolve, reject) => {
    const finish = error => {
      clearTimeout(timer);
      element.removeEventListener(name, done);
      element.removeEventListener('error', failed);
      signal.removeEventListener('abort', canceled);
      if (error) reject(error); else resolve();
    };
    const done = () => finish(), failed = () => finish(new Error('Media unavailable'));
    const canceled = () => finish(new Error('Canceled'));
    const timer = setTimeout(failed, 15000);
    element.addEventListener(name, done, { once: true });
    element.addEventListener('error', failed, { once: true });
    signal.addEventListener('abort', canceled, { once: true });
    if (signal.aborted) canceled();
  });
}

export function Filmstrip({ url, duration, hasVideo = true }) {
  const [frames, setFrames] = useState([]);
  const [status, setStatus] = useState('Loading frames…');
  useEffect(() => {
    if (!url || !hasVideo || !(duration > 0)) return;
    const controller = new AbortController();
    const video = document.createElement('video');
    video.muted = true; video.playsInline = true; video.preload = 'auto';
    const urls = [];
    const run = async () => {
      try {
        const loaded = mediaEvent(video, 'loadeddata', controller.signal);
        video.src = url;
        await loaded;
        const canvas = document.createElement('canvas');
        canvas.width = 160; canvas.height = Math.max(1, Math.round(160 * video.videoHeight / video.videoWidth));
        const context = canvas.getContext('2d');
        const times = thumbnailTimes(duration, Math.min(48, Math.max(8, Math.ceil(duration / 2))));
        for (const time of times) {
          if (controller.signal.aborted) return;
          const target = Math.min(time, Math.max(0, video.duration - .04));
          if (Math.abs(video.currentTime - target) > .001) {
            const sought = mediaEvent(video, 'seeked', controller.signal);
            video.currentTime = target;
            await sought;
          }
          context.drawImage(video, 0, 0, canvas.width, canvas.height);
          const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', .7));
          if (controller.signal.aborted) return;
          if (!blob) throw new Error('Frame unavailable');
          const image = URL.createObjectURL(blob); urls.push(image);
          setFrames(current => [...current, { time, image, width: duration / times.length }]);
        }
        setStatus('');
      } catch { if (!controller.signal.aborted) setStatus('Some frames unavailable'); }
    };
    run();
    return () => {
      controller.abort(); video.removeAttribute('src'); video.load();
      urls.forEach(image => URL.revokeObjectURL(image));
    };
  }, [url, duration, hasVideo]);
  return <div className="timeline-filmstrip" aria-label={hasVideo ? 'Clip frames at source timestamps' : 'Audio source'}>
    {frames.map(frame => <img key={frame.time} src={frame.image} alt="" draggable="false"
      data-time={frame.time} title={`Source frame ${frame.time.toFixed(2)}s`}
      style={{ left: `${frame.time / duration * 100}%`, width: `${frame.width / duration * 100}%` }} />)}
    {!frames.length && <span>{hasVideo ? status : 'Audio recording'}</span>}
    {frames.length > 0 && status === 'Some frames unavailable' && <span>{status}</span>}
  </div>;
}

export function StockThumbnail({ projectId, clip, asset }) {
  const api = useApi();
  const [url, setUrl] = useState(null);
  const jobId = clip?.job_id, index = clip?.clip_index;
  useEffect(() => {
    if (!projectId || !jobId || !asset?.id) return;
    let active = true, objectUrl;
    api.getBrollMedia(projectId, jobId, index, asset.id, 'thumbnail').then(blob => {
      if (!active) return;
      objectUrl = URL.createObjectURL(blob); setUrl(objectUrl);
    }).catch(() => {});
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [api, projectId, jobId, index, asset?.id]);
  return url ? <img src={url} alt="" draggable="false" /> : null;
}

export function AudioWaveform({ projectId, clip, segment }) {
  const api = useApi();
  const [audio, setAudio] = useState(null);
  const [status, setStatus] = useState('Loading waveform…');
  const jobId = clip?.job_id, index = clip?.clip_index;
  useEffect(() => {
    if (!projectId || !jobId || !segment.asset_id) return;
    let active = true, context;
    const load = async () => {
      try {
        const Audio = window.AudioContext || window.webkitAudioContext;
        if (!Audio) throw new Error('Decoder unavailable');
        const blob = await api.getMedia(audioAssetPath(projectId, jobId, index, segment.asset_id));
        if (!active) return;
        context = new Audio();
        const buffer = await context.decodeAudioData(await blob.arrayBuffer());
        if (active) setAudio({ peaks: audioPeaks(buffer), duration: buffer.duration });
      } catch { if (active) setStatus('Waveform unavailable'); }
      finally { if (context && context.state !== 'closed') context.close().catch(() => {}); }
    };
    load();
    return () => { active = false; if (context && context.state !== 'closed') context.close().catch(() => {}); };
  }, [api, projectId, jobId, index, segment.asset_id]);
  return audio ? <svg className="timeline-waveform" viewBox="0 0 160 40" preserveAspectRatio="none" role="img" aria-label="Source audio waveform before mixing">
    <title>Actual source audio · includes source offset and looping · before volume, fades and ducking</title>
    <path d={waveformPath(audio.peaks, audio.duration, segment)} />
  </svg> : <span className="timeline-waveform-note">{status}</span>;
}
