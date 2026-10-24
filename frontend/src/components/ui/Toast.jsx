import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ToastContext } from "./ToastContext";
import "./ui.css";

const SHOW_FOR_MS = 3000;

// Wrap the app in this once (see main.jsx); then any component can call useToast().show(...).
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]); // [{ id, message, type }]
  const nextId = useRef(0);
  const timers = useRef(new Set());

  const show = useCallback((message, type = "success") => {
    const id = nextId.current++;
    setToasts((list) => [...list, { id, message, type }]);
    const timer = setTimeout(() => {
      timers.current.delete(timer);
      setToasts((list) => list.filter((toast) => toast.id !== id));
    }, SHOW_FOR_MS);
    timers.current.add(timer);
  }, []);

  // Stop any waiting timers if the app goes away
  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach(clearTimeout);
  }, []);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {createPortal(
        <div className="ui-toasts" role="status" aria-live="polite">
          {toasts.map((toast) => (
            <div key={toast.id} className={`ui-toast ui-toast-${toast.type}`}>
              {toast.type === "error" ? "⚠️" : "✅"} {toast.message}
            </div>
          ))}
        </div>,
        document.body
      )}
    </ToastContext.Provider>
  );
}
