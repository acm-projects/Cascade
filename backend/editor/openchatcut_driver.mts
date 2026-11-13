// Cascade → OpenChatCut executor. Applies a complete, already-validated edit
// plan to a fresh OpenChatCut project in ONE offline edit session (no browser,
// no OpenChatCut LLM agent, no network), commits it atomically, then renders the
// committed timeline with OpenChatCut's own export pipeline (`occ render`).
//
// Usage: tsx openchatcut_driver.mts <spec.json> <result.json>
// Required env: OCC_DIR (OpenChatCut checkout), OPENCHATCUT_DATA_DIR (isolated library).
import { spawn } from 'node:child_process';
import { readFile, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

interface Shot {
  media: string; sourceStart: number; sourceEnd: number; speed?: number; mute?: boolean;
  zoom?: Effect | null; fx?: Effect[]; transition?: { assetId: string; frames: number } | null;
}
interface Effect { assetId: string; overrides?: Record<string, number> }
interface AudioClip { media: string; at: number; sourceStart?: number; duration: number; volume: number; fadeIn?: number; fadeOut?: number; lane: string }
interface TextClip { text: string; at: number; duration: number; fontSize: number; color: string; fontWeight?: number; y: number; pop?: boolean; lane?: string }
interface Spec {
  name: string; width: number; height: number; fps: number;
  media: Record<string, string>;
  shots: Shot[];
  grade?: { brightness?: number; contrast?: number; saturate?: number; look?: string | null; lookIntensity?: number; fx?: (string | Effect)[] };
  audio?: AudioClip[];
  texts?: TextClip[];
  output: string; resolution?: string;
  framing?: 'fit' | 'blur' | 'cover'; frameScale?: number;
}

const [specPath, resultPath] = process.argv.slice(2);
const spec: Spec = JSON.parse(await readFile(specPath, 'utf8'));
const OCC = process.env.OCC_DIR!;
const mod = (p: string) => import(pathToFileURL(`${OCC}/${p}`).href);
const steps: { tool: string; ok: boolean; note?: string }[] = [];

function check(tool: string, result: any): any {
  const failed = result && typeof result === 'object' && (result.ok === false || result.error || result.status === 'failed');
  steps.push({ tool, ok: !failed, ...(failed ? { note: JSON.stringify(result).slice(0, 600) } : {}) });
  if (failed) throw new Error(`${tool} failed: ${JSON.stringify(result).slice(0, 600)}`);
  return result;
}

const { createProject } = await mod('cli/store.ts');
const { OfflineExternalEditRuntime } = await mod('server/external-agent/offline-runtime.ts');
const project = await createProject({ name: spec.name, fps: spec.fps, width: spec.width, height: spec.height });
const runtime = await OfflineExternalEditRuntime.create(project.id, `http://localhost:5199/#/editor/${project.id}`);
let committed = false;
process.on('uncaughtException', async (error) => {
  steps.push({ tool: 'driver', ok: false, note: String(error?.message ?? error).slice(0, 800) });
  await writeFile(resultPath, JSON.stringify({ projectId: project.id, committed: false, steps, rendered: false }, null, 1));
  process.exit(1);
});
try {
  const begun: any = await runtime.execute('begin_edit_session', { clientName: 'Cascade AI Editor', approvalMode: 'auto' });
  const sid = begun.editSessionId;
  const call = async (tool: string, args: Record<string, unknown>) => check(tool, await runtime.execute(tool, { ...args, editSessionId: sid }));

  // 1. Media pool: one batched import.
  const keys = Object.keys(spec.media);
  const imported: any = await call('import_assets', { paths: keys.map((k) => spec.media[k]) });
  const assetOf: Record<string, string> = {};
  const byName = new Map<string, string>(imported.imported.map((a: any) => [a.name, a.id]));
  for (const key of keys) {
    const id = byName.get(spec.media[key].split('/').pop()!);
    if (!id) throw new Error(`asset ${key} was not imported: ${JSON.stringify(imported).slice(0, 500)}`);
    assetOf[key] = id;
  }

  // Large tool results are archived by OpenChatCut; read them back through the artifact API.
  const readValue = async (tool: string, pointer: string): Promise<any> => {
    const result: any = await call(tool, {});
    if (!result?.archived) return pointer.split('/').slice(1).reduce((node: any, key) => node?.[key], result);
    let text = ''; let offset = 0;
    for (;;) {
      const slice: any = await call('read_agent_artifact', { artifactId: result.artifactId, pointer, offset, limit: 12000 });
      text += slice.content ?? '';
      if (!slice.hasMore) break;
      offset = slice.nextOffset;
    }
    return JSON.parse(text);
  };
  const timelineItems = async (): Promise<any[]> => {
    const items = await readValue('read_timeline', '/items');
    if (!Array.isArray(items)) throw new Error('read_timeline returned no items');
    return items;
  };
  // edit_item reports every placed item; ids come from the call that created them.
  const placedIds = (result: any, expected: number): string[] => {
    const ids = (result?.results ?? []).map((r: any) => r?.placed?.itemId).filter(Boolean);
    if (ids.length !== expected) throw new Error(`expected ${expected} placed items, got ${ids.length}: ${JSON.stringify(result).slice(0, 300)}`);
    return ids;
  };

  // 2. Shots, in order, on V1. Speed retimes duration, so the cursor follows the
  //    actual committed length rather than a guessed one.
  let cursor = 0;
  const shotIds: string[] = [];
  for (const shot of spec.shots) {
    const added = await call('edit_item', { adds: [{ type: 'video', assetId: assetOf[shot.media], track: 'V1', fromFrame: cursor,
      sourceStartSeconds: shot.sourceStart, sourceEndSeconds: shot.sourceEnd }] });
    const [id] = placedIds(added, 1);
    const update: Record<string, unknown> = { type: 'video', itemId: id };
    if (shot.speed && shot.speed !== 1) update.speed = shot.speed;
    if (shot.mute) update.volume = 0;
    const g = spec.grade;
    if (g && (g.brightness || g.contrast || g.saturate)) update.filters = { brightness: g.brightness ?? 1, contrast: g.contrast ?? 1, saturate: g.saturate ?? 1 };
    // Landscape footage in a portrait frame: blurred fill behind a scaled clip, or a full cover crop.
    // Any canvas the scaled picture leaves uncovered shows a blurred copy, never transparency.
    if (spec.framing === 'blur' || spec.framing === 'cover') {
      update.backgroundFill = true; update.backgroundFillStrength = 60; update.transform = { scale: spec.frameScale ?? 1 };
    }
    if (Object.keys(update).length > 2) await call('edit_item', { updates: [update] });
    const placed = (await timelineItems()).find((i: any) => i.id === id);
    if (!placed) throw new Error(`shot ${id} missing after placement`);
    cursor = (placed.startFrame ?? placed.fromFrame) + placed.durationInFrames;
    shotIds.push(id);
  }

  // 3. Effects and transitions in one batched call (they reference committed ids).
  const adds: Record<string, unknown>[] = [];
  spec.shots.forEach((shot, i) => {
    const target = shotIds[i];
    for (const fx of [...(shot.zoom ? [shot.zoom] : []), ...(shot.fx ?? [])]) {
      adds.push({ type: 'effect', targetItemId: target, assetId: fx.assetId, ...(fx.overrides ? { propertyOverrides: fx.overrides } : {}) });
    }
    if (spec.grade?.look) adds.push({ type: 'effect', targetItemId: target, assetId: spec.grade.look, propertyOverrides: { intensity: spec.grade.lookIntensity ?? .6 } });
    for (const fx of spec.grade?.fx ?? []) {
      const effect = typeof fx === 'string' ? { assetId: fx } : fx;
      adds.push({ type: 'effect', targetItemId: target, assetId: effect.assetId, ...(effect.overrides ? { propertyOverrides: effect.overrides } : {}) });
    }
    if (i > 0 && shot.transition) adds.push({ type: 'transition', assetId: shot.transition.assetId, incomingItemId: target,
      outgoingItemId: shotIds[i - 1], durationInFrames: shot.transition.frames });
  });
  if (adds.length) await call('edit_item', { adds });

  // 4. Audio lanes (music bed, SFX) and caption/title text, each lane on its own track,
  //    batched per lane: one add call and one update call.
  const tracks: Record<string, string> = {};
  const trackFor = async (lane: string, kind: 'audio' | 'video') => {
    if (tracks[lane]) return tracks[lane];
    const before = new Set<string>((await readValue('read_project', '/timeline/tracks')).map((t: any) => t.id));
    await call('edit_track', { action: 'create', json: JSON.stringify({ trackType: kind, name: lane }) });
    const created = (await readValue('read_project', '/timeline/tracks')).find((t: any) => !before.has(t.id));
    if (!created) throw new Error(`track ${lane} was not created`);
    return (tracks[lane] = created.id);
  };
  const lanes = <T extends { lane?: string }>(clips: T[], fallback: string) => clips.reduce((all, clip) => {
    (all[clip.lane ?? fallback] ??= []).push(clip); return all;
  }, {} as Record<string, T[]>);
  for (const [lane, clips] of Object.entries(lanes(spec.audio ?? [], 'music'))) {
    const track = await trackFor(lane, 'audio');
    const added = await call('edit_item', { adds: clips.map((clip) => ({ type: 'audio', assetId: assetOf[clip.media], trackId: track,
      fromFrame: Math.round(clip.at * spec.fps), sourceStartSeconds: clip.sourceStart ?? 0, sourceEndSeconds: (clip.sourceStart ?? 0) + clip.duration })) });
    const ids = placedIds(added, clips.length);
    await call('edit_item', { updates: clips.map((clip, i) => ({ type: 'audio', itemId: ids[i], volume: clip.volume,
      ...(clip.fadeIn ? { fadeInSeconds: clip.fadeIn } : {}), ...(clip.fadeOut ? { fadeOutSeconds: clip.fadeOut } : {}) })) });
  }
  for (const [lane, texts] of Object.entries(lanes(spec.texts ?? [], 'captions'))) {
    const track = await trackFor(lane, 'video');
    const added = await call('edit_item', { adds: texts.map((t) => ({ type: 'text', text: t.text, trackId: track,
      fromFrame: Math.round(t.at * spec.fps), durationInFrames: Math.max(2, Math.round(t.duration * spec.fps)),
      fontSize: t.fontSize, color: t.color, fontWeight: t.fontWeight ?? 800, align: 'center' })) });
    const ids = placedIds(added, texts.length);
    await call('edit_item', { updates: texts.map((t, i) => ({ type: 'text', itemId: ids[i], transform: { y: t.y },
      ...(t.pop ? { keyframes: { scale: [{ frame: 0, value: .7, easing: 'easeOut' }, { frame: 4, value: 1 }] } } : {}) })) });
  }

  const review: any = await runtime.execute('review_edit_session', { editSessionId: sid, summary: 'Cascade AI Editor plan' });
  check('review_edit_session', review);
  committed = review.status === 'applied';
  if (!committed) throw new Error(`edit session not applied: ${JSON.stringify(review).slice(0, 400)}`);
} catch (error: any) {
  steps.push({ tool: 'driver', ok: false, note: String(error?.message ?? error).slice(0, 800) });
  await runtime.dispose();
  await writeFile(resultPath, JSON.stringify({ projectId: project.id, committed: false, steps, rendered: false }, null, 1));
  process.exit(1);
}
await runtime.dispose();

// 5. Render with OpenChatCut's own export pipeline.
const render = await new Promise<{ code: number; log: string }>((resolve) => {
  const child = spawn(process.execPath, ['--import', 'tsx', `${OCC}/cli/main.ts`, 'render', project.id, '--out', spec.output,
    '--resolution', spec.resolution ?? '1080p', '--fps', String(spec.fps), '--quiet'], { cwd: OCC, env: process.env });
  let log = '';
  child.stdout.on('data', (d) => { log += d; });
  child.stderr.on('data', (d) => { log += d; });
  child.on('close', (code) => resolve({ code: code ?? 1, log: log.slice(-3000) }));
});
steps.push({ tool: 'occ render', ok: render.code === 0, ...(render.code ? { note: render.log } : {}) });
await writeFile(resultPath, JSON.stringify({ projectId: project.id, committed, steps, rendered: render.code === 0 }, null, 1));
process.exitCode = render.code === 0 ? 0 : 1;
