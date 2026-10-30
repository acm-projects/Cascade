import { useCallback, useEffect, useRef, useState } from "react";
import useApi from "../../api/useApi";

const SAVE_DELAY_MS = 700;   // save this long after the last change
const HISTORY_LIMIT = 50;

// One clip's edits ("draft"), loaded from and auto-saved to the backend (backend/editor_backend.py).
// Use it inside a component that has key={clipKey(clip)}, so switching clips starts fresh.
//   info    - { duration, width, height, cues: [{ start, end, text }], burned_in, warning } (null while loading)
//   state   - the edit: { start, end, captions, composition, effects, reframe, texts, broll }
//   change(next) - set a new state (undoable); next can be a function of the current state
//   patch(next)  - same, but not an undo step
//   recordUndo(before) - after live patch() updates (a drag), add ONE undo step back to `before`
//   undo / redo / canUndo / canRedo
//   chat, setChat - the editor chat for this clip (saved with the draft)
//   saveStatus - "saved" | "saving" | "error"
export default function useClipDraft(projectId, clip) {
  const api = useApi();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState({ past: [], present: null, future: [] });
  const [chat, setChat] = useState([]);
  const [saveStatus, setSaveStatus] = useState("saved");
  const loaded = useRef(false);    // don't save the draft we just loaded straight back
  const saveCount = useRef(0);
  const pending = useRef(null);    // { state, chat } waiting for the autosave timer, or null
  const sending = useRef(0);       // saves sent but not answered yet

  useEffect(() => {
    let active = true;
    api.getDraft(projectId, clip.job_id, clip.clip_index)
      .then((result) => {
        if (!active) return;
        const { draft, ...details } = result;
        setInfo(details);
        setHistory({ past: [], present: draft.state, future: [] });
        setChat(draft.chat ?? []);
      })
      .catch((err) => active && setError(err));
    return () => {
      active = false;
    };
  }, [api, projectId, clip.job_id, clip.clip_index]);

  // Send one save to the backend
  const send = useCallback((edits) => {
    sending.current += 1;
    return api.saveDraft(projectId, clip.job_id, clip.clip_index, { ...edits, updated_at: Math.floor(Date.now() / 1000) })
      .finally(() => {
        sending.current -= 1;
      });
  }, [api, projectId, clip.job_id, clip.clip_index]);

  // Auto-save a moment after the last change
  const state = history.present;
  useEffect(() => {
    if (!state) return;
    if (!loaded.current) {
      loaded.current = true;
      return;
    }
    const thisSave = ++saveCount.current;
    pending.current = { state, chat };
    const timer = setTimeout(() => {
      pending.current = null;
      setSaveStatus("saving");
      send({ state, chat })
        .then(() => thisSave === saveCount.current && setSaveStatus("saved"))
        .catch(() => thisSave === saveCount.current && setSaveStatus("error"));
    }, SAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [state, chat, send]);

  // Switching clips closes this editor before the timer goes off: send the waiting save right away
  // so the last change isn't lost.
  useEffect(() => () => {
    if (pending.current) send(pending.current).catch(() => {});
  }, [send]);

  // Closing the tab while something isn't saved yet: let the browser ask "Leave site?"
  useEffect(() => {
    function warn(event) {
      if (!pending.current && !sending.current) return;
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  const change = useCallback((next) => {
    setHistory(({ past, present }) => {
      const value = typeof next === "function" ? next(present) : next;
      if (JSON.stringify(value) === JSON.stringify(present)) return { past, present, future: [] };
      return { past: [...past, present].slice(-HISTORY_LIMIT), present: value, future: [] };
    });
  }, []);

  // A change that isn't an undo step (e.g. the app storing a finished framing analysis)
  const patch = useCallback((next) => {
    setHistory(({ past, present, future }) => ({
      past, future, present: typeof next === "function" ? next(present) : next,
    }));
  }, []);

  // After a drag that used patch() for live updates, make the whole drag ONE undo step:
  // `before` is the state from when the drag started.
  const recordUndo = useCallback((before) => {
    setHistory(({ past, present, future }) =>
      JSON.stringify(before) === JSON.stringify(present)
        ? { past, present, future }
        : { past: [...past, before].slice(-HISTORY_LIMIT), present, future: [] });
  }, []);

  const undo = useCallback(() => {
    setHistory(({ past, present, future }) =>
      past.length ? { past: past.slice(0, -1), present: past[past.length - 1], future: [present, ...future] } : { past, present, future });
  }, []);

  const redo = useCallback(() => {
    setHistory(({ past, present, future }) =>
      future.length ? { past: [...past, present], present: future[0], future: future.slice(1) } : { past, present, future });
  }, []);

  return {
    info, error, state, change, patch, recordUndo, undo, redo,
    canUndo: history.past.length > 0, canRedo: history.future.length > 0,
    chat, setChat, saveStatus,
  };
}
