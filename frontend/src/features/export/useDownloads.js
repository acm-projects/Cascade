import { useRef, useState } from 'react';
import { needsFraming } from '../editor/useAutoFraming';
import { fileSafe } from '../editor/clips';
import { downloadName, exportEdit, saveBlob } from './downloads';

export default function useDownloads(api, projectId, projectName, settings) {
  const [working, setWorking] = useState(false);
  const [progressText, setProgressText] = useState('');
  const [error, setError] = useState(null);
  const busy = useRef(false), last = useRef(null);

  async function run(clips, batch, number = 1) {
    if (busy.current) return null;
    busy.current = true; setWorking(true); setError(null);
    last.current = { clips, batch, number };
    setProgressText(batch ? `Rendering ${clips.length} clips…` : 'Rendering clip 1 of 1…');
    try {
      const entries = [];
      for (const clip of clips) {
        const info = await api.getDraft(projectId, clip.job_id, clip.clip_index);
        if (needsFraming(info.draft.state, info) && !info.draft.state.reframe.analysis_id)
          throw Error(`Automatic framing for “${clip.title || 'Clip'}” is not ready. Open it in Export first or use Fit in the Editor.`);
        entries.push({ job_id: clip.job_id, clip_index: clip.clip_index,
          edit: exportEdit(info.draft.state, settings) });
      }
      const blob = batch ? await api.exportSelected(projectId, entries)
        : await api.exportClip(projectId, entries[0].job_id, entries[0].clip_index, entries[0].edit);
      const filename = batch ? `cascade-${fileSafe(projectName, 'project')}.zip` : downloadName(projectName, number);
      saveBlob(blob, filename);
      setProgressText('Download ready.');
      return { blob, filename };
    } catch (err) {
      setError(err.message); setProgressText(''); return null;
    } finally { busy.current = false; setWorking(false); }
  }
  return { working, progressText, error,
    downloadOne: (clip, number) => run([clip], false, number),
    downloadSelected: clips => run(clips, true),
    retry: () => last.current && run(last.current.clips, last.current.batch, last.current.number) };
}
