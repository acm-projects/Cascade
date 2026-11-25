import { fileSafe } from '../editor/clips.js';

export function exportEdit(state, settings) {
  return { ...state, resolution: settings.resolution,
    captions: { ...state.captions, enabled: settings.includeCaptions && state.captions.enabled } };
}

export function downloadName(project, number, audio = false) {
  return `${fileSafe(project, 'cascade')}-selected-${number}.${audio ? 'mp3' : 'mp4'}`;
}

/** What to paste into TikTok or Instagram: the caption, then the hashtags. */
export function postText(post) {
  return [post?.caption?.trim(), (post?.hashtags ?? []).join(' ')].filter(Boolean).join('\n\n');
}

export { downloadBlob as saveBlob } from '../editor/clips.js';
