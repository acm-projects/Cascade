import { ComponentType } from 'react';
import { KineticKeyword } from './KineticKeyword';
import { BrollOverlay } from './BrollOverlay';
import { PlainSpeaker } from './PlainSpeaker';
import { ScribbleHighlight } from './ScribbleHighlight';
import { TextBehindSubject } from './TextBehindSubject';
import { SpeakerCutoutIcons } from './SpeakerCutoutIcons';
import { Collage } from './Collage';
import { NumberCounter } from './NumberCounter';
import { MapCallout } from './MapCallout';
import { ScreenshotCallout } from './ScreenshotCallout';

/** Template name (from the plan) -> component. Unknown names render as PLAIN_SPEAKER. */
export const TEMPLATES: Record<string, ComponentType> = {
  KINETIC_KEYWORD: KineticKeyword,
  BROLL_OVERLAY: BrollOverlay,
  PLAIN_SPEAKER: PlainSpeaker,
  SCRIBBLE_HIGHLIGHT: ScribbleHighlight,
  TEXT_BEHIND_SUBJECT: TextBehindSubject,
  SPEAKER_CUTOUT_ICONS: SpeakerCutoutIcons,
  COLLAGE: Collage,
  NUMBER_COUNTER: NumberCounter,
  MAP_CALLOUT: MapCallout,
  SCREENSHOT_CALLOUT: ScreenshotCallout,
};
