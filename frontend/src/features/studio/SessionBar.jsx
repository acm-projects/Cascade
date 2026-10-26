import { useToast } from "../../components/ui/ToastContext";
import "./SessionBar.css";

// Thin bar under the TopNav: which AI Studio session you're in, with a ▾ to change it.
// UI only for now: the dropdown (switch / create / rename / delete) is ticket 3.6.
//   name     - the session's name, e.g. "Session 1"
//   children - extra things for the right side (e.g. "Go to Editor")
function SessionBar({ name, children }) {
  const toast = useToast();

  return (
    <div className="session-bar">
      <button
        type="button"
        className="session-bar-picker"
        aria-haspopup="menu"
        title="Change session"
        onClick={() => toast.show("Switching sessions is coming soon")}
      >
        <span className="session-bar-label">Session</span>
        <span className="session-bar-name">{name}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {children && <div className="session-bar-actions">{children}</div>}
    </div>
  );
}

export default SessionBar;
