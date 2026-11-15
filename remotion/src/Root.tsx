import { Composition } from 'remotion';
import { Edit } from './Edit';
import { RenderProps } from './lib/context';
import { totalFrames } from './lib/timing.js';
import example from '../example-props.json';

/** "Edit": the whole beat plan. Size, fps and length come from the props the backend writes (render.json). */
export function Root() {
  return <Composition id="Edit" component={Edit as any} defaultProps={example as unknown as RenderProps}
    durationInFrames={1} fps={60} width={1284} height={704}
    calculateMetadata={({ props }) => {
      const p = props as unknown as RenderProps;
      return { durationInFrames: totalFrames(p.plan, p.fps), fps: p.fps, width: p.width, height: p.height };
    }} />;
}
