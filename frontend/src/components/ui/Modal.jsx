import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import "./ui.css";

// A pop-up window over the page. Show it with {isOpen && <Modal ...>}.
//   <Modal title="Delete project?" onClose={() => setIsOpen(false)}> ...buttons... </Modal>
// Closes on Esc, on a click outside the box, and with the × button.
function Modal({ title, children, onClose }) {
  const dialogRef = useRef(null);
  const onCloseRef = useRef(onClose);
  const titleId = useId();

  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    const previous = document.activeElement; // where focus was before, so we can put it back
    dialogRef.current?.focus();

    function handleKey(event) {
      if (event.key === "Escape") onCloseRef.current?.();
    }
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      previous?.focus?.();
    };
  }, []);

  // createPortal: draw it at the end of <body>, so it sits above everything on the page
  return createPortal(
    <div className="ui-modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div ref={dialogRef} className="ui-modal wood-panel" role="dialog" aria-modal="true"
        aria-labelledby={titleId} tabIndex={-1}>
        <div className="ui-modal-header">
          <h2 id={titleId} className="ui-modal-title">{title}</h2>
          <button type="button" className="btn btn-ghost btn-small" aria-label="Close" onClick={onClose}>✕</button>
        </div>
        <div className="ui-modal-body">{children}</div>
      </div>
    </div>,
    document.body
  );
}

export default Modal;
