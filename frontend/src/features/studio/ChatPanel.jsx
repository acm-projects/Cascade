import { useEffect, useRef, useState } from "react";
import "./ChatPanel.css";
import leafCream from "../../assets/icons/leaf-cream.svg";
import { MAX_CLIPS, requestedClipCount } from './clipCount';

const MIN_CLIPS = 1;

// The AI Studio chat column: messages on top (they scroll), prompt box pinned at the bottom.
//   messages         - [{ id?, role: "user" | "assistant", text }]
//   onSend(text, n)  - called with the prompt and how many clips to find (1-50). If it returns
//                      (or resolves to) false, the prompt stays in the box so it isn't lost.
//   disabled         - true while waiting for an answer
//   text, onTextChange - optional: let the page fill the box (e.g. "Reuse prompt")
//   note             - optional line under the box (e.g. "2 picked clips will guide this prompt")
//   chips            - picked-clip controls above the composer
function ChatPanel({ messages, onSend, disabled = false, text: controlledText, onTextChange, note, chips,
  focusRequest, onStop, onRetry, onReuse }) {
  const [ownText, setOwnText] = useState("");
  const text = controlledText ?? ownText;
  const setText = onTextChange ?? setOwnText;
  const [clipCount, setClipCount] = useState(4);
  const [countError, setCountError] = useState('');
  const listRef = useRef(null);
  const promptRefs = useRef(new Map());
  const lastMessageId = messages.at(-1)?.id;

  // Keep the newest message in view
  useEffect(() => {
    if (!focusRequest) listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [lastMessageId, focusRequest]);

  useEffect(() => {
    const target = promptRefs.current.get(focusRequest?.jobId);
    const list = listRef.current;
    if (!target || !list) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    list.scrollTo({ top: list.scrollTop + target.getBoundingClientRect().top
      - list.getBoundingClientRect().top - 12, behavior: reduced ? 'instant' : 'smooth' });
    target.focus({ preventScroll: true });
  }, [focusRequest]);

  async function send() {
    const prompt = text.trim();
    if (!prompt || disabled) return;
    let count;
    try { count = requestedClipCount(prompt, clipCount); }
    catch (error) { setCountError(error.message); return; }
    setCountError('');
    setClipCount(count);
    const sent = await onSend(prompt, count);
    if (sent !== false) setText("");
  }

  function handleKeyDown(event) {
    // Enter sends; Shift+Enter makes a new line. isComposing: don't send a half-typed
    // Japanese/Chinese/Korean word whose Enter is choosing characters.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  }

  return (
    <section className="chat-panel wood-panel" aria-label="AI assistant chat">
      <header className="chat-panel-header">
        <h2>AI Assistant</h2>
        <p>Tell me what to find and how many clips you want.</p>
      </header>

      <div className="chat-panel-messages" ref={listRef} aria-live="polite">
        {messages.length === 0 && (
          <p className="chat-panel-hint">Try: "Find the funniest moments" or "Clips about the new product".</p>
        )}
        {messages.map((message, i) => (
          <div key={message.id ?? i}
            ref={element => {
              if (message.role !== 'user' || !message.jobId) return;
              if (element) promptRefs.current.set(message.jobId, element);
              else promptRefs.current.delete(message.jobId);
            }}
            tabIndex={message.role === 'user' && message.jobId ? -1 : undefined}
            className={`chat-bubble chat-bubble-${message.role}${message.role === 'user' && message.jobId && focusRequest?.jobId === message.jobId ? ' chat-bubble-focused' : ''}`}>
            {message.text}
            {message.group?.parent_clips?.length > 1 && <div className="chat-reference-context">
              <b>Combined references</b>
              {message.group.parent_clips.map((reference, index) => <span key={index}>
                {index + 1}. {reference.title || 'Selected clip'}
              </span>)}
            </div>}
            {message.group && <div className="chat-generation-actions">
              {['queued', 'processing'].includes(message.group.state) &&
                <button type="button" className="btn btn-small" onClick={() => onStop?.(message.group.job_id)}>Stop</button>}
              {message.group.state === 'error' &&
                <button type="button" className="btn btn-small" onClick={() => onRetry?.(message.group.job_id)}>Retry</button>}
              <button type="button" className="btn btn-small" onClick={() => onReuse?.(message.group.prompt)}>Reuse prompt</button>
            </div>}
          </div>
        ))}
      </div>

      <form className="chat-panel-form" onSubmit={(e) => { e.preventDefault(); send(); }}>
        {chips}
        <textarea
          className="chat-panel-input"
          rows={3}
          placeholder="e.g. Find 10 funny clips…"
          aria-label="Prompt"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="chat-panel-row">
          <label className="chat-panel-count">
            Clips
            <input
              type="number"
              min={MIN_CLIPS}
              max={MAX_CLIPS}
              value={clipCount}
              onChange={(e) => setClipCount(e.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-primary btn-small chat-panel-send" disabled={disabled || !text.trim()}>
            <img src={leafCream} alt="" />
            Send
          </button>
        </div>
        {note && <p className="chat-panel-note">{note}</p>}
        {countError && <p role="alert">{countError}</p>}
      </form>
    </section>
  );
}

export default ChatPanel;
