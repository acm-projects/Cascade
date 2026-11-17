// Plain-language Trend Analysis: your edit vs. the trending videos, in a few rows anyone can read,
// what each trending video does differently, and the request to send the AI Editor for each suggestion.

const finite = v => Number.isFinite(v);
const median = xs => {
  const v = xs.filter(finite).sort((a, b) => a - b);
  return v.length ? (v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2) : null;
};
const s = v => `${Math.round(v * 10) / 10} s`;
const length = v => (v >= 60 ? `${Math.floor(v / 60)}:${String(Math.round(v % 60)).padStart(2, '0')}` : `${Math.round(v)} s`);

/** When the picture first changes (the first cut), or null if not measured. */
export const firstCut = m => (m?.cuts ? (m.cuts[0] ?? m.span) : null);
export const shape = m => (m?.width && m?.height ? (m.height > m.width ? 'Vertical' : m.width > m.height ? 'Horizontal' : 'Square') : null);

/** Rows for "You vs. the top videos": { key, label, yours, theirs, good, verdict, tip }. Rows that can't be measured are left out. */
export function compareRows(edit, refs, editDuration) {
  const rows = [];
  const add = (key, label, yours, theirs, good, verdict, tip) => rows.push({ key, label, yours, theirs, good, verdict: good ? 'On par' : verdict, tip });
  const yourHook = firstCut(edit), theirHook = median(refs.map(firstCut));
  if (finite(yourHook) && finite(theirHook))
    add('hook', 'First change on screen', s(yourHook), s(theirHook), yourHook <= theirHook + 0.5, 'Slower start', 'Hook viewers faster: change the picture in the first 2 seconds.');
  const yourPace = edit?.avgShot, theirPace = median(refs.map(m => m?.avgShot));
  if (finite(yourPace) && finite(theirPace))
    add('pace', 'New shot every', s(yourPace), s(theirPace), yourPace <= theirPace * 1.25, 'Slower cuts', 'Cut faster: a new visual every 1 to 2 seconds.');
  const yourLength = edit?.duration ?? editDuration, theirLength = median(refs.map(m => m?.duration));
  if (finite(yourLength) && finite(theirLength))
    add('length', 'Length', length(yourLength), length(theirLength), yourLength <= theirLength * 1.35, 'Longer', 'Trim to the strongest part.');
  const shapes = refs.map(shape).filter(Boolean);
  const common = shapes.sort((a, b) => shapes.filter(x => x === b).length - shapes.filter(x => x === a).length)[0];
  const yours = shape(edit);
  if (yours && common) add('shape', 'Shape', yours, common, yours === common, 'Different shape', `Most top videos are ${common.toLowerCase()}.`);
  return rows;
}

/** Up to 3 short lines on how one trending video differs from your edit. */
export function differences(ref, m, edit) {
  const lines = [];
  const theirs = firstCut(m), yours = firstCut(edit);
  if (finite(theirs) && finite(yours) && Math.abs(theirs - yours) >= 0.7)
    lines.push(theirs < yours ? `Changes the picture after ${s(theirs)}; yours waits ${s(yours)}.` : `Opens slower than yours (${s(theirs)} vs ${s(yours)}).`);
  if (finite(m?.avgShot) && finite(edit?.avgShot)) {
    const ratio = edit.avgShot / m.avgShot;
    if (ratio >= 1.3) lines.push(`Cuts ${ratio >= 1.95 ? `about ${Math.round(ratio)}×` : 'a bit'} faster: a new shot every ${s(m.avgShot)} (yours: ${s(edit.avgShot)}).`);
    else if (ratio <= 0.75) lines.push(`Cuts slower than yours: a new shot every ${s(m.avgShot)}.`);
  }
  if (shape(m) && shape(edit) && shape(m) !== shape(edit)) lines.push(`${shape(m)} video; yours is ${shape(edit).toLowerCase()}.`);
  const hook = [].concat(ref?.observed_tags?.hook_style || [])[0];
  if (hook) lines.push(`Opens with: ${String(hook).replace(/\s+/g, ' ').slice(0, 90)}${String(hook).length > 90 ? '…' : ''}`);
  if (!lines.length && finite(m?.duration) && finite(edit?.duration)) lines.push(`${length(m.duration)} long; yours is ${length(edit.duration)}.`);
  return lines.slice(0, 3);
}

const PROMPTS = {
  hook: 'Make the hook punchier: open on the strongest line and change the picture in the first 2 seconds.',
  pause_removal: 'Make it faster: a new visual every 1 to 2 seconds and no dead pauses.',
  punch_in: 'Add punch-in zooms on the key words.',
  broll: 'Add more b-roll that shows what is being talked about.',
  captions: 'Make the on-screen words bigger and bolder so the key words read without sound.',
  music: 'Add background music under the speech, quiet enough that it never covers the words.',
};

/** The request the "Ask AI Editor" button sends for a suggestion. */
export function askPrompt(suggestion) {
  if (PROMPTS[suggestion?.technique]) return PROMPTS[suggestion.technique];
  const detail = String(suggestion?.shortText || '').split(/(?<=[.!?])\s/)[0];
  return [suggestion?.title, detail].filter(Boolean).join(': ').slice(0, 300) || 'Make this edit more engaging.';
}
