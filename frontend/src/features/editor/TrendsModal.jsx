import Modal from '../../components/ui/Modal';
import { useEffect } from 'react';
import ClipPlayer from './ClipPlayer';
import TrendsPanel from './TrendsPanel';
import './TrendsPanel.css';

export default function TrendsModal({ projectId, clip, state, info, flush, onApply, disabled, onClose, children }) {
  useEffect(() => {
    document.querySelectorAll('video, audio').forEach(media => { if (!media.closest('.trends-modal')) media.pause(); });
  }, []);
  return <Modal title="Trends · YouTube research" onClose={onClose} className="trends-modal">
    <TrendsPanel key={`${projectId}:${clip.job_id}:${clip.clip_index}`} projectId={projectId} clip={clip} state={state} info={info} flush={flush} onApply={onApply} disabled={disabled} preview={
      <section className="trends-modal-preview" aria-label="Selected clip">
        <h3>{clip.title || 'Selected clip'}</h3>
        {info && state && <ClipPlayer projectId={projectId} clip={clip} state={state} info={info} />}
        {children}
      </section>
    } />
  </Modal>;
}
