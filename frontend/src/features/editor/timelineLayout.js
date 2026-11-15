// All timeline geometry stays in source seconds, including trims and retimed previews.
export function thumbnailTimes(duration, count) {
  if (!(duration > 0) || count < 1) return [];
  return Array.from({ length: count }, (_, i) => i * duration / count);
}

// Assign overlapping events separate lanes without changing their time or width.
export function layoutLanes(items) {
  const ends = [];
  const placed = [...items].sort((a, b) => a.start - b.start).map(item => {
    let lane = ends.findIndex(end => end <= item.start + 1e-6);
    if (lane < 0) lane = ends.length;
    ends[lane] = item.start + item.duration;
    return { ...item, lane };
  });
  return { items: placed, lanes: Math.max(1, ends.length) };
}

export function audioPeaks(buffer, count = 2048) {
  const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) => buffer.getChannelData(i));
  return Array.from({ length: count }, (_, i) => {
    let peak = 0;
    const start = Math.floor(i * buffer.length / count), end = Math.floor((i + 1) * buffer.length / count);
    for (const channel of channels) for (let j = start; j < end; j++) peak = Math.max(peak, Math.abs(channel[j]));
    return peak;
  });
}

// Waveform represents the source audio (before mixing/ducking), respecting offset and looping.
export function waveformPath(peaks, sourceDuration, segment, count = 160) {
  const values = Array.from({ length: count }, (_, i) => {
    let t = (segment.offset || 0) + i / (count - 1) * segment.duration;
    if (segment.loop) t %= sourceDuration;
    if (t < 0 || t >= sourceDuration || !(sourceDuration > 0)) return 0;
    return Math.min(1, peaks[Math.min(peaks.length - 1, Math.floor(t / sourceDuration * peaks.length))] || 0) * 17;
  });
  return values.map((v, i) => `${i ? 'L' : 'M'}${i},${20 - v}`).join(' ') + ' ' + values.map((_, j) => {
    const i = count - 1 - j;
    return `L${i},${20 + values[i]}`;
  }).join(' ') + ' Z';
}
