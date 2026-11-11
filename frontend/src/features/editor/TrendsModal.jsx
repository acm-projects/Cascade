import TrendAnalysis from './trends/TrendAnalysis';

// The Trends button opens the full Trend Analysis page over the Editor/Export page.
// change: accept a previewed change into the draft (undoable). onOpenEditor(t): go edit at source second t.
export default function TrendsModal({ projectId, clip, state, info, flush, change, onClose, onOpenEditor, clips, onSelectClip }) {
  return <TrendAnalysis key={`${projectId}:${clip.job_id}:${clip.clip_index}`} projectId={projectId} clip={clip} state={state} info={info}
    flush={flush} change={change} onClose={onClose} onOpenEditor={onOpenEditor} clips={clips} onSelectClip={onSelectClip} />;
}
