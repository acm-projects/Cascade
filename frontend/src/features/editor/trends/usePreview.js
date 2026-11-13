import { useState } from 'react';
import useApi from '../../../api/useApi';

/** Ask the backend for the edited state one suggestion would produce (nothing is saved). */
export default function usePreview({ projectId, clip, state, researchId }) {
  const api = useApi();
  const [preview, setPreview] = useState(null);
  async function open(s) {
    setPreview({ index: s.index, title: s.title, status: 'loading' });
    try {
      const result = await api.applyTrends(projectId, clip.job_id, clip.clip_index, { state, research_id: researchId, suggestion: s.index });
      const outcome = result.outcomes?.[0];
      const changed = JSON.stringify(result.state) !== JSON.stringify(state);
      setPreview({ index: s.index, title: s.title, status: 'ready', candidate: changed ? result.state : null,
        message: outcome && outcome.status !== 'applied' ? outcome.message : outcome?.message || '' });
    } catch (e) {
      setPreview({ index: s.index, title: s.title, status: 'error', message: e.status === 409 ? 'Your edit changed since this analysis. Analyze again to preview this change.' : e.message });
    }
  }
  return { preview, open, close: () => setPreview(null), previewing: preview?.status === 'loading' ? preview.index : null };
}
