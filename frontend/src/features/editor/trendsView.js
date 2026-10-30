import { timelineClock } from './reelTiming.js';
export const TITLES = { hook: 'Tighten the opening', pause_removal: 'Give the story a tighter pace', captions: 'Make the words easier to follow', punch_in: 'Emphasize the reaction', broll: 'Add a purposeful cutaway', music: 'Support the scene with music' };
export const ACTIONS = { hook: 'Start at the selected complete phrase.', pause_removal: 'Remove confirmed pauses while keeping spoken phrases.', captions: 'Apply short, bold animated caption groups.', punch_in: 'Add one timed punch-in zoom.', broll: 'Search and insert one relevant stock cutaway.', music: 'Add quiet background music with fades.' };
export function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k, stable(value[k])]));
  return value;
}
export const same = (a, b) => JSON.stringify(stable(a)) === JSON.stringify(stable(b));
export function concise(value, limit = 220, sentences = 2) {
  let text = String(value || '').replace(/\b(visual_style|audio_style|hook_style|call_to_action)\b/g, x => x.replaceAll('_', ' ')).replace(/\s+/g, ' ').trim();
  text = (text.match(/.+?(?:[.!?]+[”"')\]]*(?=\s|$)|$)/g) || [text]).slice(0, sentences).join(' ').replace(/\s+/g, ' ').trim();
  if (text.length > limit) text = text.slice(0, limit - 1).replace(/\s+\S*$/, '') + '…';
  return text;
}
export function unique(items = [], limit = Infinity) {
  const seen = new Set();
  return items.filter(x => { const key = String(x).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim(); if (!key || seen.has(key)) return false; seen.add(key); return true; }).slice(0, limit);
}
export function youtubeUrl(ref) {
  const id = ref?.video_id || ref?.id || ref?.reference_id;
  return /^[\w-]{11}$/.test(id || '') ? `https://www.youtube.com/watch?v=${id}` : null;
}
export function speechWarning(result, info) {
  if (result?.speech_evidence?.status === 'timestamped_transcript' || info?.cues?.length) return '';
  if (result?.speech_evidence?.status === 'no_audio_stream' || info?.has_audio === false) return 'This clip has no audio stream.';
  return 'Speech is not confirmed. Missing speech timestamps do not mean this clip has no dialogue.';
}
export function unavailable(s, state, info) {
  if (s.executable === false) return s.unavailable_reason || 'This action is not available.';
  if (!TITLES[s.technique]) return 'This technique is not supported by the editor.';
  if (['hook', 'punch_in', 'broll'].includes(s.technique) && !Number.isFinite(s.at)) return 'The analysis did not locate a specific moment.';
  if (['captions', 'hook', 'pause_removal'].includes(s.technique) && !info?.cues?.length) return 'Reliable speech timestamps are needed before this edit can be applied.';
  if (Number.isFinite(s.at) && (s.at < state.start || s.at >= state.end)) return 'This moment is outside the current clip.';
  if (['punch_in', 'broll'].includes(s.technique) && Number.isFinite(s.at)) {
    const clock = timelineClock(state);
    if (clock.output(Math.min(state.end, s.at + .1)) - clock.output(s.at) <= .001) return 'This moment was removed from the current clip.';
  }
  return '';
}
export function clipTime(s, state) {
  if (['captions', 'pause_removal'].includes(s.technique)) return 'Whole current clip';
  if (!Number.isFinite(s.at)) return ['music', 'captions', 'pause_removal'].includes(s.technique) ? 'Whole clip · no specific moment located' : 'Timing not located';
  const time = timelineClock(state).output(s.at);
  return `${Math.floor(time / 60)}:${(time % 60).toFixed(2).padStart(5, '0')} · current clip time`;
}
export function viewData(record, state, info) {
  const result = record?.result || {};
  const references = (result.references || record?.references || []).filter((ref, i, all) => all.findIndex(r => r.id === ref.id) === i);
  const evidenceWarning = speechWarning(result, info);
  const uncertain = /(?:no|without|lack(?:s|ing)?) (?:spoken |clear |detected )?(?:dialogue|speech)|dialogue.free/i;
  const honest = text => evidenceWarning ? String(text || '').replace(/(?:with )?no speech detected[,;]?/gi, 'With speech timing unconfirmed,').replace(/having no detected speech/gi, 'having uncertain speech timing').replace(/dialogue.free/gi, 'speech timing unconfirmed') : text;
  let summary = concise(result.summary, 440, 3);
  if (!references.length) summary = 'No YouTube references have been successfully analyzed for this report. Any ideas shown below are AI suggestions, not trend findings.';
  else if (evidenceWarning && uncertain.test(summary)) summary = 'The audio evidence is incomplete, so this analysis cannot establish whether the clip contains dialogue. Review the grounded visual suggestions below; audio-dependent edits need reliable speech timestamps.';
  const strengths = unique((result.strengths || []).filter(s => !evidenceWarning || !uncertain.test(s)).map(s => concise(s, 150, 1)), 3);
  const seen = new Set();
  const suggestions = (result.suggestions || []).map((s, index) => ({ ...s, index, title: TITLES[s.technique] || 'Review this technique', action: ACTIONS[s.technique], limitation: /stabili[sz]|reduce.{0,25}(?:handheld )?shake/i.test(s.text || '') ? 'Camera stabilization is an additional idea; it is not implemented by Apply.' : '', shortText: concise(honest(s.text)), benefit: concise(honest(s.reason), 170), source_ids: (s.source_ids || []).filter(id => references.some(r => r.id === id)), unavailable: unavailable(s, state, info) }))
    .filter(s => { const key = `${s.technique}:${s.at ?? 'none'}`; if (seen.has(key)) return false; seen.add(key); return true; }).sort((a, b) => Number(!!a.unavailable) - Number(!!b.unavailable)).slice(0, 6);
  if (references.length && evidenceWarning && uncertain.test(concise(result.summary, 440, 3))) {
    const tags = result.your_video_tags || {};
    const pace = { fast: 'moves quickly', medium: 'has a steady pace', slow: 'takes a slower pace' }[tags.pacing];
    summary = [pace && `This clip ${pace}.`, tags.tone && `Its tone is ${String(tags.tone).split(',')[0].toLowerCase()}.`, 'Speech presence remains uncertain; review the visual opportunities below.'].filter(Boolean).join(' ');
  }
  const examples = references.filter(r => r.kind === 'example').length, tutorials = references.filter(r => r.kind === 'tutorial').length;
  const patterns = unique((result.observed_patterns || []).filter(p => p.count >= 2).map(p => `${p.count === 2 && p.examples === 2 ? 'Both analyzed examples' : `${p.count} of ${p.examples} analyzed examples`}: ${concise(p.trait, 170, 1)}`), 3);
  return { result, references, summary, strengths, suggestions, examples, tutorials, patterns, evidenceWarning };
}
export function referenceLearning(ref) {
  if (ref.learned?.length) return unique(ref.learned.map(x => concise(x, 160, 1)), 3);
  if (ref.kind === 'tutorial') return unique((ref.techniques || []).map(x => concise(x, 160, 1)), 3);
  const tags = ref.observed_tags || {};
  return unique([['visual_style', 'Visuals'], ['pacing', 'Pacing'], ['hook_style', 'Opening'], ['tone', 'Tone']].flatMap(([key, label]) => (Array.isArray(tags[key]) ? tags[key] : [tags[key]]).filter(Boolean).map(v => `${label}: ${concise(v, 140, 1)}`)), 3);
}
