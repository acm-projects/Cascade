import { AbsoluteFill, Sequence } from 'remotion';
import { BeatContext, BeatInfo, RenderProps } from './lib/context';
import { beatFrames, transitionLength } from './lib/timing.js';
import { useFonts } from './lib/fonts';
import { TEMPLATES } from './templates';
import { Filters, Finish } from './components/Finish';
import { Transition } from './components/Transition';
import { Footage } from './components/Footage';

function Fallback() { return <Footage />; }

/** One beat's picture, at its own local frame (frames past its end keep going, which transitions use). */
export function BeatPicture({ info }: { info: BeatInfo }) {
  const Template = TEMPLATES[info.beat.template] || Fallback;
  return <BeatContext.Provider value={info}><AbsoluteFill><Template /></AbsoluteFill></BeatContext.Provider>;
}

/** The whole edit: each beat in its own Sequence; the transition into a beat also draws the previous beat's tail. */
export function Edit(props: RenderProps) {
  useFonts();
  const frames = beatFrames(props.plan, props.fps);
  return <AbsoluteFill style={{ background: '#000' }}>
    <Filters />
    {props.plan.beats.map((beat, index) => {
      const { from, to } = frames[index];
      const length = to - from;
      const info: BeatInfo = { beat, index, from, length, offset: from, assets: props.assets[String(beat.id)] || {}, props };
      const prev = index > 0 ? props.plan.beats[index - 1] : null;
      const prevLength = prev ? frames[index - 1].to - frames[index - 1].from : 0;
      // Drawn inside this beat's Sequence, shifted back by its own length, so its footage stays on the edit's clock.
      const prevInfo: BeatInfo | null = prev ? { beat: prev, index: index - 1, from: frames[index - 1].from,
        length: prevLength, offset: from - prevLength, assets: props.assets[String(prev.id)] || {}, props } : null;
      const overlap = prev ? transitionLength(beat.transition_in, length) : 0;
      return <Sequence key={beat.id} from={from} durationInFrames={length} name={`${beat.id} ${beat.template}`}>
        <Transition name={beat.transition_in} frames={overlap} prev={prevInfo} info={info} />
        {props.options?.labels && <Label text={`${beat.id} ${beat.template}`} />}
      </Sequence>;
    })}
    <Finish grain={props.options?.grain !== false} />
  </AbsoluteFill>;
}

function Label({ text }: { text: string }) {
  return <div style={{ position: 'absolute', top: 8, right: 10, font: '600 16px Inter', color: '#fff', background: 'rgba(0,0,0,.5)', padding: '2px 6px' }}>{text}</div>;
}

/** The previous beat drawn past its end, for transitions: its local frame continues from its own length. */
export function PrevPicture({ info }: { info: BeatInfo }) {
  return <Sequence from={-info.length} layout="none"><BeatPicture info={info} /></Sequence>;
}
