import ChatBox from '../../components/ChatBox';
import './AIEditorChat.css';

export const AI_EDITOR_PROMPT = 'Make this a high-energy Instagram Reel with beat-synced cuts, punch-in zooms, animated captions, shakes, and music. Preserve complete spoken phrases and existing manual edits.';
const suggestions = [
  { label: 'Create a high-energy Reel', prompt: AI_EDITOR_PROMPT },
  { label: 'Less shake', prompt: 'Less shake' },
  { label: 'Move the last zoom earlier', prompt: 'Move that zoom earlier by 0.5 seconds' },
  { label: 'Undo last AI edit', prompt: 'Undo your last edit' },
];

function engineLine(status) {
  if (!status) return null;
  if (status.provider !== 'openchatcut') return `Local AI planner (${status.provider})`;
  const quota = status.quota;
  return `${status.planner} · ${status.model} → ${status.engine}` +
    (quota ? ` · ${quota.exhausted ? 'daily free quota used up' : `${quota.used} of ${quota.limit} free requests used by Cascade today`} · resets ${quota.resets}` : '');
}

export default function AIEditorChat({ messages, onSend, onClear, disabled, typing, clip, result, status }) {
  const analysis = result?.analysis;
  const occ = status?.provider === 'openchatcut';
  const placeholder = typing
    ? (occ ? 'Planning with one free Gemini request, then applying with OpenChatCut…' : 'Analyzing footage and planning edits…')
    : 'Describe the edit, or refine the last change…';
  return <div className="ai-editor-chat">
    <ChatBox title="AI Editor" subtitle="Plans and applies real timeline edits. Preview shows the rendered result."
      messages={messages} onSend={onSend} disabled={disabled || status?.quota?.exhausted} typing={typing}
      tag={clip.title || 'Selected clip'} quickActions={suggestions} placeholder={placeholder} />
    {onClear && <button type="button" className="editor-choice ai-editor-clear" onClick={onClear} disabled={typing || !messages.length}>
      Clear chat history
    </button>}
    {status && <p className="ai-editor-engine" aria-live="polite">{engineLine(status)}</p>}
    {result && <details className="ai-editor-receipt">
      <summary>Editing plan &amp; execution details</summary>
      {analysis && <>
        <p>{analysis.engine && `${analysis.engine} · `}{analysis.provider} · {analysis.planning_method === 'direct_revision' ? 'direct revision of existing state (no AI request)' : analysis.model || 'configured model'} · {analysis.sampled_frames?.length || 0} sampled frames · {analysis.transcript_cues} transcript cues</p>
        {analysis.quota && <p>Free-tier requests today: {analysis.quota.used}/{analysis.quota.limit} · resets {analysis.quota.resets}</p>}
        {analysis.observations?.map((item, index) => <p key={index}><b>{item.at.toFixed(2)}s</b> · {item.description}</p>)}
        <p>{analysis.limitation}</p>
      </>}
      <ol>{result.report?.map((step, index) => <li key={index} className={`ai-editor-step ${step.status}`}>
        <b>{step.status}</b> · {step.message}
      </li>)}</ol>
      {result.unsupported?.length > 0 && <p>Not applied: {result.unsupported.join('; ')}</p>}
    </details>}
  </div>;
}
