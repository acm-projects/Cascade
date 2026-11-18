import ChatBox from '../../components/ChatBox';
import './AIEditorChat.css';

export const AI_EDITOR_PROMPT = 'Make this a high-energy Instagram Reel with beat-synced cuts, punch-in zooms, animated captions, shakes, and music. Preserve complete spoken phrases and existing manual edits.';
const suggestions = [
  { label: 'Cascade signature edit', prompt: 'Edit this video in a bold Cascade style inspired by the reference guide. Choose the best visual language for the actual story, with meaningful standout moments, strong type, dynamic framing and a clean payoff. Preserve complete speech and my aspect ratio.' },
  { label: 'Editorial collage', prompt: 'Edit this video with the editorial collage direction: evidence-led photo cards, an ink reveal, a circled hero word and readable typography. Keep it relevant to the speech, with quiet space between bold moments.' },
  { label: 'Create a high-energy Reel', prompt: AI_EDITOR_PROMPT },
  { label: 'Less shake', prompt: 'Less shake' },
  { label: 'Move the last zoom earlier', prompt: 'Move that zoom earlier by 0.5 seconds' },
  { label: 'Undo last AI edit', prompt: 'Undo your last edit' },
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

// The beat plan the AI Editor made (one row per visual beat). Plans only for now: nothing renders from them yet.
// Each saved version records which beats changed from its parent; a first plan has no highlights.
export default function AIEditorChat({ messages, onSend, onClear, disabled, typing, clip, result, cues, job, aiEdit, beatPlan }) {
  const placeholder = job
    ? 'Working on the edit. You can ask for changes when it finishes…'
    : typing ? 'Starting…' : aiEdit || beatPlan ? 'Ask for a change to this edit…' : 'Type “edit this clip”, or describe the edit you want…';
  return <div className="ai-editor-chat">
    <ChatBox title="AI Editor" subtitle="Tell me the edit you want and I'll make it."
      messages={messages} onSend={onSend} disabled={disabled} typing={typing}
      tag={clip.title || 'Selected clip'} quickActions={suggestions} placeholder={placeholder} />
    {job && <section className="ai-edit-progress" role="status" aria-live="polite">
      <div className="ai-edit-progress-bar"><i style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} /></div>
      <p>{job.stage}</p>
    </section>}
    {result?.storyboard && <Storyboard board={result.storyboard} cues={cues} onSend={onSend} disabled={disabled} />}
    {onClear && <button type="button" className="editor-choice ai-editor-clear" onClick={onClear} disabled={typing || !messages.length}>
      Clear chat history
    </button>}
  </div>;
}
