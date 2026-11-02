import "./Monkey.css";

// Just for fun: a monkey that peeks up from behind whatever it's wrapped around while you hover it,
// grabs the top edge with both paws, and ducks back down when you leave.
// Wrap a card: <Monkey><div className="my-card">…</div></Monkey>. The card must sit above the
// monkey (Monkey.css gives the wrapped element position: relative + z-index: 1).
// Pure CSS animation; it never blocks clicks and is skipped for "reduce motion" users.
const outline = { stroke: "#3b2a14", strokeWidth: 2.5, strokeLinejoin: "round", strokeLinecap: "round" };

function Monkey({ children }) {
  return (
    <div className="monkey-spot">
      {/* the head, behind the card */}
      <span className="monkey-head" aria-hidden="true">
        <svg viewBox="0 0 80 64" width="100%" height="100%">
          <g {...outline}>
            <circle cx="12" cy="30" r="10" fill="#8a5a2b" />
            <circle cx="12" cy="30" r="5" fill="#e8c193" />
            <circle cx="68" cy="30" r="10" fill="#8a5a2b" />
            <circle cx="68" cy="30" r="5" fill="#e8c193" />
            <ellipse cx="40" cy="34" rx="24" ry="26" fill="#8a5a2b" />
            <path d="M24 34 Q24 18 34 20 Q40 24 46 20 Q56 18 56 34 Q58 54 40 56 Q22 54 24 34 Z" fill="#e8c193" />
          </g>
          <circle cx="33" cy="32" r="3" fill="#3b2a14" />
          <circle cx="47" cy="32" r="3" fill="#3b2a14" />
          <circle cx="34" cy="31" r="1" fill="#fff" />
          <circle cx="48" cy="31" r="1" fill="#fff" />
          <path d="M37 41 h6" {...outline} strokeWidth="2" />
          <path d="M32 46 Q40 53 48 46" fill="none" {...outline} strokeWidth="2" />
        </svg>
      </span>
      {children}
      {/* the paws, in front of the card, gripping its top edge */}
      <span className="monkey-paws" aria-hidden="true">
        <svg viewBox="0 0 80 14" width="100%" height="100%">
          <g {...outline}>
            <ellipse cx="18" cy="7" rx="8" ry="5" fill="#e8c193" />
            <ellipse cx="62" cy="7" rx="8" ry="5" fill="#e8c193" />
          </g>
          <path d="M14 4 v4 M18 3 v5 M22 4 v4 M58 4 v4 M62 3 v5 M66 4 v4" stroke="#3b2a14" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </span>
    </div>
  );
}

export default Monkey;
