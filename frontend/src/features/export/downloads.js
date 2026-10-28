import { fileSafe } from '../editor/clips.js';

export function exportEdit(state, settings) {
  return { ...state, resolution: settings.resolution,
    captions: { ...state.captions, enabled: settings.includeCaptions && state.captions.enabled } };
}

export function downloadName(project, number) {
  return `${fileSafe(project, 'cascade')}-selected-${number}.mp4`;
}

export { downloadBlob as saveBlob } from '../editor/clips.js';
