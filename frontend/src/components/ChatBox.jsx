import { useState } from "react";
import "./ChatBox.css";
import leafIcon from "../assets/icons/leaf.svg";

// A chat panel: header, message list, optional "attached video" tag, text box, and quick buttons.
//   title / subtitle - header text (leave out for no header)
//   onNewChat        - shows a "+ New Chat" button that calls this
//   messages         - [{ role: "user" | "assistant" | "system", text, changes? }]
//                      (system = a note from the app; changes = small chips under the message)
//   onSend(text)     - called when the user sends a message
//   tag              - text for the attachment tag (e.g. the video's name), or null for none
//   onRemoveTag      - called when the ✕ on the tag is clicked
//   quickActions     - [{ label, prompt }]: buttons under the text box that send a ready-made prompt
//   typing           - show the "…" bubble while the AI is answering
function ChatBox({
  title, subtitle, onNewChat, messages, onSend, placeholder = "Type a message...",
  tag, onRemoveTag, quickActions = [], disabled, typing,
}) {
  const [text, setText] = useState("");

  function send(message) {
    if (message.trim() === "" || disabled) return;
    onSend(message.trim());
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (disabled) return; // keep the typed text until the AI is free
    send(text);
    setText("");
  }

  return (
    <form className="chatbox" onSubmit={handleSubmit}>
      {title && (
        <header className="chatbox-header">
          <img src={leafIcon} alt="" className="chatbox-leaf" />
          <div className="chatbox-heading">
            <h2 className="chatbox-title">{title}</h2>
            {subtitle && <p className="chatbox-subtitle">{subtitle}</p>}
          </div>
          {onNewChat && (
            <button type="button" className="btn btn-small" onClick={onNewChat}>+ New Chat</button>
          )}
        </header>
      )}

      <div className="chatbox-messages">
        {messages.length === 0 && <p className="chatbox-empty">No messages yet.</p>}
        {messages.map((message, index) => (
          <div key={index} className={`chatbox-message ${message.role}`}>
            {message.text}
            {message.changes?.length > 0 && (
              <span className="chatbox-changes">
                {message.changes.map((change) => <span key={change} className="chatbox-change">{change}</span>)}
              </span>
            )}
          </div>
        ))}
        {typing && <p className="chatbox-message assistant chatbox-typing" aria-label="Thinking">…</p>}
      </div>

      {tag && (
        <div className="chatbox-tag">
          <span>🎬 {tag}</span>
          {onRemoveTag && (
            <button type="button" onClick={onRemoveTag} title="Remove">✕</button>
          )}
        </div>
      )}

      <div className="chatbox-input-row">
        <input
          className="chatbox-input"
          placeholder={placeholder}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button type="submit" className="chatbox-send" title="Send" disabled={disabled}>
          ➤
        </button>
      </div>

      {quickActions.length > 0 && (
        <div className="chatbox-quick">
          {quickActions.map((action) => (
            <button
              key={action.label}
              type="button"
              className="btn btn-small chatbox-quick-btn"
              onClick={() => send(action.prompt)}
              disabled={disabled}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </form>
  );
}

export default ChatBox;
