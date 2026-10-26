import { useEffect, useRef, useState } from "react";
import "./ChatPanel.css";
import leafCream from "../../assets/icons/leaf-cream.svg";

const MIN_CLIPS = 1;
const MAX_CLIPS = 12;

// The AI Studio chat column: messages on top (they scroll), prompt box pinned at the bottom.
//   messages         - [{ id?, role: "user" | "assistant", text }]
//   onSend(text, n)  - called with the prompt and how many clips to find (1-12). If it returns
//                      (or resolves to) false, the prompt stays in the box so it isn't lost.
//   disabled         - true while waiting for an answer
//   text, onTextChange - optional: let the page fill the box (e.g. "Reuse prompt")
//   note             - optional line under the box (e.g. "2 picked clips will guide this prompt")
function ChatPanel({ messages, onSend, disabled = false, text: controlledText, onTextChange, note }) {
  const [ownText, setOwnText] = useState("");
  const text = controlledText ?? ownText;
  const setText = onTextChange ?? setOwnText;
  const [clipCount, setClipCount] = useState(4);
  const listRef = useRef(null);

  // Keep the newest message in view
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send() {
    const prompt = text.trim();
    if (!prompt || disabled) return;
    const count = Math.min(MAX_CLIPS, Math.max(MIN_CLIPS, Math.round(Number(clipCount) || 4)));
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
        <p>Tell me what clips to find.</p>
      </header>

      <div className="chat-panel-messages" ref={listRef} aria-live="polite">
        {messages.length === 0 && (
          <p className="chat-panel-hint">Try: "Find the funniest moments" or "Clips about the new product".</p>
        )}
        {messages.map((message, i) => (
          <div key={message.id ?? i} className={`chat-bubble chat-bubble-${message.role}`}>
            {message.text}
          </div>
        ))}
      </div>

      <form className="chat-panel-form" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <textarea
          className="chat-panel-input"
          rows={3}
          placeholder="Describe the clips you want…"
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
      </form>
    </section>
  );
}

export default ChatPanel;
