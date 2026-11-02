import "./Parrot.css";

// Just for fun: a little parrot that flies in and lands on whatever it's wrapped around while you
// hover it, then flies away when you leave. Wrap a button: <Parrot><button>…</button></Parrot>
// Pure CSS animation (Parrot.css); it never blocks clicks and is skipped for "reduce motion" users.
function Parrot({ children }) {
  return (
    <span className="parrot-perch">
      {children}
      <span className="parrot" aria-hidden="true">
        <svg viewBox="0 0 64 64" width="100%" height="100%">
          <g stroke="#3b2a14" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round">
            {/* tail */}
            <path d="M40 40 L58 60 L50 61 Z" fill="#2f7fd1" />
            <path d="M38 40 L52 62 L45 62 Z" fill="#f6c431" />
            {/* body */}
            <ellipse cx="34" cy="36" rx="12" ry="14" fill="#e23b2e" />
            {/* feet */}
            <path d="M30 49 v5 M36 49 v5 M27 54 h6 M33 54 h6" fill="none" />
            {/* head */}
            <circle cx="24" cy="20" r="10" fill="#e23b2e" />
            <path d="M17 17 Q19 12 24 13 Q21 18 22 24 Q18 23 17 17 Z" fill="#fff6e6" />
            <circle cx="21" cy="18" r="1.8" fill="#3b2a14" stroke="none" />
            {/* beak */}
            <path d="M15 18 Q8 19 9 26 Q12 22 16 23 Z" fill="#f6c431" />
          </g>
          {/* wing: flaps while flying, folds when landed */}
          <g className="parrot-wing" stroke="#3b2a14" strokeWidth="2" strokeLinejoin="round">
            <path d="M30 28 Q48 26 50 44 Q40 46 32 40 Z" fill="#3fae4a" />
            <path d="M40 36 Q47 38 49 44 Q43 45 39 42 Z" fill="#2f7fd1" />
          </g>
        </svg>
      </span>
    </span>
  );
}

export default Parrot;
