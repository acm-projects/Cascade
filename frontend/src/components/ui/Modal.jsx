import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import "./ui.css";

// A pop-up window over the page. Show it with {isOpen && <Modal ...>}.
//   <Modal title="Delete project?" onClose={() => setIsOpen(false)}> ...buttons... </Modal>
// Closes on Esc, on a click outside the box, and with the × button.
function Modal({ title, children, onClose, className = '', wide = false }) {
  const dialogRef = useRef(null);
  const onCloseRef = useRef(onClose);
  const titleId = useId();

  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    const previous = document.activeElement; // where focus was before, so we can put it back
    const oldOverflow = document.body.style.overflow;
    const oldHtmlOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';
    const backdrop = dialogRef.current?.parentElement;
    const background = Array.from(document.body.children).filter(node => node !== backdrop && node instanceof HTMLElement);
    const inertBefore = background.map(node => node.inert);
    const overflowBefore = background.map(node => node.style.overflow);
    background.forEach(node => { node.inert = true; node.style.overflow = 'hidden'; });
    dialogRef.current?.focus();

    function handleKey(event) {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onCloseRef.current?.(); }
      if (event.key === 'Tab') {
        const items = Array.from(dialogRef.current?.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), video[controls], audio[controls], [tabindex="0"]') || []).filter(node => node.getClientRects().length && !node.closest('[inert]'));
        const first = items[0], last = items.at(-1);
        if (!first) { event.preventDefault(); dialogRef.current?.focus(); }
        else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogRef.current)) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialogRef.current)) { event.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      background.forEach((node, i) => { node.inert = inertBefore[i]; node.style.overflow = overflowBefore[i]; });
      document.body.style.overflow = oldOverflow;
      document.documentElement.style.overflow = oldHtmlOverflow;
      previous?.focus?.();
    };
  }, []);

  // createPortal: draw it at the end of <body>, so it sits above everything on the page
  return createPortal(
    <div className="ui-modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div ref={dialogRef} className={`ui-modal wood-panel${wide ? " ui-modal-wide" : ""} ${className}`} role="dialog" aria-modal="true"
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
