// What the editing AI changed, as short labels for the chips under its reply in the Chat tab.
// Compares the draft before and after: describeChanges(before, after) -> ["Trim 3.0–30.0 s", "Caption color: #ffd400"]

const seconds = (value) => `${value.toFixed(1)} s`;
const onOff = (value) => (value ? "on" : "off");

const CAPTION_LABELS = [
  ["enabled", "Captions", onOff],
  ["color", "Caption color", String],
  ["size", "Caption size", String],
  ["bold", "Bold captions", onOff],
  ["position", "Caption position", String],
  ["font", "Caption font", String],
];

export function describeChanges(before, after) {
  if (!before || !after) return [];
  const changes = [];
  if (before.start !== after.start || before.end !== after.end) {
    changes.push(`Trim ${after.start.toFixed(1)}–${seconds(after.end)}`);
  }
  const was = before.captions ?? {};
  const now = after.captions ?? {};
  for (const [field, label, format] of CAPTION_LABELS) {
    if (was[field] !== now[field] && now[field] !== undefined) changes.push(`${label}: ${format(now[field])}`);
  }
  if (JSON.stringify(before.texts ?? {}) !== JSON.stringify(after.texts ?? {})) changes.push("Caption text");
  const frame = after.composition ?? {};
  if (before.composition?.ratio !== frame.ratio) changes.push(`Frame: ${frame.ratio}`);
  if (before.composition?.mode !== frame.mode) changes.push(frame.mode === "fill" ? "Crop to fill" : "Fit whole video");
  if (before.reframe?.enabled !== after.reframe?.enabled) changes.push(`Follow speaker: ${onOff(after.reframe?.enabled)}`);
  if ((before.broll?.length ?? 0) !== (after.broll?.length ?? 0)) changes.push(`B-roll: ${after.broll?.length ?? 0} segment(s)`);
  return changes;
}
