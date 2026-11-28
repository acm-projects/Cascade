import ChatBox from '../../components/ChatBox';
import Mascot from '../../components/Mascot';
import { DEMO_EDIT_PROMPT } from '../../demo';
import './AIEditorChat.css';

// Three quick starts; anything else, the person just types
const suggestions = [
  { label: 'Edit this clip', prompt: 'Edit this clip' },
  { label: 'Music edit', prompt: 'Make a music edit: pick the best song from the library, cut on the beat and show the lyrics' },
  { label: 'Undo last edit', prompt: 'Undo your last edit' },
];

// The storyboard OpenAI proposed: nothing renders until "Render". Notes go through the chat box.
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

export default function AIEditorChat({ messages, onSend, onClear, disabled, typing, result, cues, job, aiEdit, onUseTimeline, demo }) {
  const analysis = result?.analysis;
  const placeholder = job
    ? 'Working on the edit. You can ask for changes when it finishes…'
    : typing ? 'Starting…' : aiEdit ? 'Ask for a change to this edit…' : 'Type “edit this clip”, or describe the edit you want…';
  return <div className="ai-editor-chat">
    <ChatBox title="AI Editor" subtitle="OpenAI plans your edit from the footage and speech. The Edited preview shows the rendered result."
      messages={messages} onSend={onSend} disabled={disabled} typing={typing}
      quickActions={suggestions} placeholder={placeholder} prefill={demo && !aiEdit ? DEMO_EDIT_PROMPT : undefined}
      peek={<><Mascot variant="full" size={118} /><span className="chatbox-peek-bubble">{aiEdit ? 'Want any changes?' : 'Tell me the edit you want!'}</span></>} />
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
    {result && <details className="ai-editor-receipt">
      <summary>What changed</summary>
      {analysis && <>
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
