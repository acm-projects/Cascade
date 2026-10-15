import { useState } from "react";
import { Link } from "react-router-dom";
import "./EditorPage.css";
import editorBg from "../assets/VideoEditorPg.png";

function EditorPage() {
  const [messages, setMessages] = useState([]); // chat history
  const [text, setText] = useState("");          // what's typed in the chat box

  function handleSend(e) {
    e.preventDefault();
    if (text.trim() === "") return;
    setMessages([...messages, text]);
    setText("");
  }

  function handleAttach(e) {
    const file = e.target.files[0];
    if (file) setMessages([...messages, `📎 ${file.name}`]);
  }

  return (
    <div className="editor">
      <form
        className="editor-stage"
        style={{ backgroundImage: `url(${editorBg})` }}
        onSubmit={handleSend}
      >
        {/* Top bar: tools (placeholder) */}
        <div className="editor-toolbar">Effects · SFX · Captions</div>

        {/* Big panel: video preview (placeholder) */}
        <div className="editor-preview">Video preview</div>

        {/* Right plank: Export */}
        <Link to="/export" className="editor-export">Export</Link>

        {/* Right panel: AI chat */}
        <div className="editor-chat-messages">
          {messages.map((message, index) => (
            <p key={index} className="editor-chat-message">{message}</p>
          ))}
        </div>

        <input
          className="editor-chat-input"
          placeholder="Ask for an edit..."
          value={text}
          onChange={(e) => setText(e.target.value)}
        />

        <label className="editor-chat-attach" title="Attach a file">
          <input type="file" hidden onChange={handleAttach} />
        </label>

        <button type="submit" className="editor-chat-send" title="Send" />
      </form>
    </div>
  );
}

export default EditorPage;