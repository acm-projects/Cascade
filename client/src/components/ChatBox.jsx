import { useState } from "react";
import "./ChatBox.css";

// A chat panel: title, message list, optional "attached video" tag, and a text box.
//   messages     - [{ role: "user" | "assistant", text }]
//   onSend(text) - called when the user sends a message
//   tag          - text for the attachment tag (e.g. the video's name), or null for none
//   onRemoveTag  - called when the ✕ on the tag is clicked
function ChatBox({ title, messages, onSend, placeholder = "Type a message...", tag, onRemoveTag, disabled }) {
  const [text, setText] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    if (text.trim() === "" || disabled) return;
    onSend(text.trim());
    setText("");
  }

  return (
    <form className="chatbox" onSubmit={handleSubmit}>
      {title && <h2 className="chatbox-title">{title}</h2>}

      <div className="chatbox-messages">
        {messages.length === 0 && <p className="chatbox-empty">No messages yet.</p>}
        {messages.map((message, index) => (
          <p key={index} className={`chatbox-message ${message.role}`}>
            {message.text}
          </p>
        ))}
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
          ↑
        </button>
      </div>
    </form>
  );
}

export default ChatBox;
