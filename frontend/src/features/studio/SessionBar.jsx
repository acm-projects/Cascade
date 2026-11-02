import { useState } from "react";
import Modal from "../../components/ui/Modal";
import Button from "../../components/ui/Button";
import "./SessionBar.css";

// Thin bar under the TopNav: which AI Studio session you're in, switch / create / rename / delete sessions.
// Each session has its own source video and clip exploration.
//   sessions        - [{ id, name, job_ids }]
//   activeId        - the session on screen
//   onSwitch(id), onCreate(name), onRename(name), onDelete() - may return promises; the pop-up waits for them
//   children        - extra things for the right side (e.g. "Go to Editor")
function SessionBar({ sessions, activeId, onSwitch, onCreate, onRename, onDelete, children }) {
  const [dialog, setDialog] = useState(null); // null | "create" | "rename" | "delete"
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const active = sessions.find((session) => session.id === activeId);

  function open(kind) {
    setName(kind === "rename" ? active?.name ?? "" : "");
    setDialog(kind);
  }

  async function submit(event) {
    event.preventDefault();
    if (dialog !== "delete" && !name.trim()) return;
    setSaving(true);
    try {
      if (dialog === "delete") await onDelete();
      else await (dialog === "create" ? onCreate(name.trim()) : onRename(name.trim()));
      setDialog(null);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="session-bar">
      <label className="session-bar-picker">
        <span className="session-bar-label">Session</span>
        <select className="session-bar-select" value={activeId} onChange={(e) => onSwitch(e.target.value)}>
          {sessions.map((session) => (
            <option key={session.id} value={session.id}>
              {session.name}{session.job_ids?.length ? ` · ${session.job_ids.length} ${session.job_ids.length === 1 ? "prompt" : "prompts"}` : ""}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="btn btn-ghost btn-small" onClick={() => open("rename")} aria-label="Rename session">✎</button>
      <button type="button" className="btn btn-ghost btn-small" onClick={() => open("delete")} aria-label="Delete session"
        disabled={sessions.length < 2} title={sessions.length < 2 ? "You can't delete the only session" : "Delete this session"}>🗑</button>
      <button type="button" className="btn btn-small" onClick={() => open("create")}>+ New session</button>
      {children && <div className="session-bar-actions">{children}</div>}

      {dialog && (
        <Modal title={{ create: "New session", rename: "Rename session", delete: "Delete session?" }[dialog]}
          onClose={() => !saving && setDialog(null)}>
          <form className="session-bar-form" onSubmit={submit}>
            {dialog === "create" && <p>Start with a new audio or video source. Your other sessions and clips stay saved.</p>}
            {dialog === "delete" ? (
              <p>Delete <strong>{active?.name}</strong>? Its clips leave the Studio and are unpicked from the Editor. Your other sessions stay.</p>
            ) : (
              <input className="session-bar-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={80}
                placeholder="Funny moments, Emotional, Highlights…" aria-label="Session name" autoFocus />
            )}
            <div className="session-bar-form-actions">
              <Button variant="ghost" size="sm" onClick={() => setDialog(null)} disabled={saving}>Cancel</Button>
              <Button variant="primary" size="sm" type="submit" disabled={saving || (dialog !== "delete" && !name.trim())}>
                {{ create: "Create", rename: "Save", delete: "Delete" }[dialog]}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

export default SessionBar;
