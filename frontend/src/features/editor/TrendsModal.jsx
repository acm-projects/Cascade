import Modal from '../../components/ui/Modal';
import { useEffect } from 'react';
import TrendsPanel from './TrendsPanel';
import './TrendsPanel.css';

export default function TrendsModal({ projectId, clip, state, info, flush, onClose }) {
  useEffect(() => {
    document.querySelectorAll('video, audio').forEach(media => media.pause());
  }, []);
  return <Modal title="Trends analysis" onClose={onClose} className="trends-modal">
    <TrendsPanel key={`${projectId}:${clip.job_id}:${clip.clip_index}`} projectId={projectId} clip={clip} state={state} info={info} flush={flush} />
  </Modal>;
}
