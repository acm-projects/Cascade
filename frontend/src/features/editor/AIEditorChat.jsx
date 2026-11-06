import ChatBox from '../../components/ChatBox';
import './AIEditorChat.css';

export const AI_EDITOR_PROMPT = 'Make this a high-energy Instagram Reel with beat-synced cuts, punch-in zooms, animated captions, shakes, and music. Preserve complete spoken phrases and existing manual edits.';
const suggestions = [
  { label: 'Edit this video', prompt: 'Edit this video' },
  { label: 'Create a high-energy Reel', prompt: AI_EDITOR_PROMPT },
  { label: 'Less shake', prompt: 'Less shake' },
  { label: 'Move the last zoom earlier', prompt: 'Move that zoom earlier by 0.5 seconds' },
  { label: 'Undo last AI edit', prompt: 'Undo your last edit' },
];

function engineLine(status) {
  if (!status) return null;
  if (status.provider === 'claude') return `Claude · ${status.billing} (${status.plan}) · no API charges`;
  if (status.provider !== 'openchatcut') return `Local AI planner (${status.provider})`;
  const quota = status.quota;
  return `${status.planner} · ${status.model} → ${status.engine}` +
    (quota ? ` · ${quota.exhausted ? 'daily free quota used up' : `${quota.used} of ${quota.limit} free requests used by Cascade today`} · resets ${quota.resets}` : '');
}

// The storyboard Claude proposed: nothing renders until "Render". Notes go through the chat box.
function Storyboard({ board, cues, onSend, disabled }) {
  return <section className="ai-storyboard" aria-label="Storyboard">
    <header><b>Storyboard · {board.title || "edit"}</b><small>{board.planner}</small></header>
    <p className="ai-storyboard-plan">{[board.ratio, board.look.replace("_", " "), `${board.captions} captions, size ${board.caption_size}`,
      board.music !== "none" && board.music, board.hook && `hook: “${board.hook}”`].filter(Boolean).join(" · ")}</p>
    <ol className="ai-storyboard-beats">{board.beats.map(beat => <li key={beat.n} className={beat.keep ? "" : "cut"}>
      {board.thumbnails[beat.n] && <img alt="" src={`data:image/jpeg;base64,${board.thumbnails[beat.n]}`} />}
      <span className="ai-storyboard-n">Beat {beat.n}</span>
      {!beat.keep && <em>cut</em>}
      <q className={beat.caption ? "rewritten" : ""}>{beat.caption || cues?.[beat.n]?.text}</q>
      {beat.emphasis && <strong>{beat.emphasis.toUpperCase()}</strong>}
      <small>{[beat.zoom !== "none" && `${beat.zoom} zoom`, beat.broll && `B-roll: ${beat.broll}`, beat.effect !== "none" && beat.effect,
        beat.sfx !== "none" && beat.sfx].filter(Boolean).join(" · ")}</small>
    </li>)}</ol>
    <div className="ai-storyboard-actions">
      <button type="button" className="editor-choice" disabled={disabled} onClick={() => onSend("render")}>Render</button>
      <button type="button" className="editor-choice" disabled={disabled} onClick={() => onSend("discard")}>Discard</button>
      <small>Or type a note: “beat 3 caption should say …”, “tighter cut”, “bigger captions”.</small>
    </div>
  </section>;
}

export default function AIEditorChat({ messages, onSend, onClear, disabled, typing, clip, result, status, cues, job, aiEdit, onUseTimeline }) {
  const analysis = result?.analysis;
  // A used-up Gemini quota does not lock the chat: storyboards are planned with Claude (or the local
  // model), and requests that need Gemini come back as a visible NOT APPLIED note.
  const placeholder = job
    ? 'Working on the edit. You can ask for changes when it finishes…'
    : typing ? 'Starting…' : aiEdit ? 'Ask for a change to this edit…' : 'Type “edit this clip”, or describe the edit you want…';
  return <div className="ai-editor-chat">
    <ChatBox title="AI Editor" subtitle="Plans and applies real timeline edits. Preview shows the rendered result."
      messages={messages} onSend={onSend} disabled={disabled} typing={typing}
      tag={clip.title || 'Selected clip'} quickActions={suggestions} placeholder={placeholder} />
    {job && <section className="ai-edit-progress" role="status" aria-live="polite">
      <div className="ai-edit-progress-bar"><i style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} /></div>
      <p>{job.stage}</p>
      <small>This usually takes a few minutes. It keeps going if you switch clips or reload.</small>
    </section>}
    {aiEdit && !job && <p className="ai-edit-current">
      The Edited preview and Export use AI edit {aiEdit.version}, a finished film. Trim, Captions and the other tabs edit the source timeline.
      <button type="button" className="editor-choice" onClick={onUseTimeline}>Use my timeline instead</button>
    </p>}
    {result?.storyboard && <Storyboard board={result.storyboard} cues={cues} onSend={onSend} disabled={disabled} />}
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
