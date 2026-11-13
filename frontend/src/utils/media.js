export const MEDIA_ACCEPT = '.mp4,.mov,.webm,.mkv,.mp3,.wav,.m4a,.flac,.avi,.m4v';
const extensions = new Set(MEDIA_ACCEPT.split(','));
export const isSupportedMedia = file => extensions.has('.'+(file?.name || '').split('.').pop().toLowerCase());
export const isAudioClip = clip => clip?.media_kind === 'audio' || clip?.clip_url?.endsWith('.mp3');

// Video files only (for editing your own clip)
export const VIDEO_ACCEPT = '.mp4,.mov,.webm,.mkv,.avi,.m4v';
export const isVideoFile = (file) => VIDEO_ACCEPT.split(',').includes(`.${file?.name?.split('.').pop()?.toLowerCase()}`);
