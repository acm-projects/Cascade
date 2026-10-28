import { fileSafe } from '../editor/clips.js';

export function exportEdit(state, settings) {
  return { ...state, resolution: settings.resolution,
    captions: { ...state.captions, enabled: settings.includeCaptions && state.captions.enabled } };
}

export function downloadName(project, number, audio = false) {
  return `${fileSafe(project, 'cascade')}-selected-${number}.${audio ? 'mp3' : 'mp4'}`;
}

export { downloadBlob as saveBlob } from '../editor/clips.js';
