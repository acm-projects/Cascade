import "./LandingMascot.css";

// The landing page's jungle friend: a monkey on a branch, working on a laptop (the laptop lid shows our leaf).
// A placeholder drawing in the app's outlined style; swap this file's SVG for real artwork any time.
const ink = { stroke: "#3b2a14", strokeWidth: 4, strokeLinejoin: "round", strokeLinecap: "round" };
const fur = "#8a5a2b", face = "#e8c193";

function LandingMascot() {
  return (
    <div className="landing-mascot" aria-hidden="true">
      <svg viewBox="0 0 400 420" width="100%" height="100%">
        {/* vine hanging from above */}
        <path d="M330 0 C 320 60 345 110 330 170" fill="none" stroke="#3f8f3a" strokeWidth="7" strokeLinecap="round" />
        {[[326, 50, -30], [338, 100, 30], [331, 150, -25]].map(([x, y, r]) => (
          <ellipse key={y} cx={x} cy={y} rx="16" ry="8" transform={`rotate(${r} ${x} ${y})`} fill="#5cb848" {...ink} strokeWidth="3" />
        ))}

        {/* tail curling down under the branch */}
        <path d="M262 318 C 300 350 310 395 278 404 C 258 409 252 388 268 382" fill="none" stroke={fur} strokeWidth="13" strokeLinecap="round" />
        <path d="M262 318 C 300 350 310 395 278 404 C 258 409 252 388 268 382" fill="none" stroke="#3b2a14" strokeWidth="3" strokeLinecap="round" opacity="0.35" />

        {/* the branch */}
        <path d="M400 296 C 300 288 190 300 30 322 Q 18 332 32 342 C 190 324 300 318 400 326 Z" fill="#7a5230" {...ink} />
        <path d="M90 326 C 150 318 220 314 300 312" fill="none" stroke="#5c3c20" strokeWidth="3" opacity="0.5" />
        {[[60, 318, -20], [110, 306, 15], [360, 290, -15], [385, 300, 25]].map(([x, y, r]) => (
          <ellipse key={x} cx={x} cy={y} rx="22" ry="10" transform={`rotate(${r} ${x} ${y})`} fill="#4fa85a" {...ink} strokeWidth="3" />
        ))}

        {/* legs dangling over the branch */}
        <path d="M188 290 C 180 330 182 350 178 372" fill="none" stroke={fur} strokeWidth="26" strokeLinecap="round" />
        <path d="M246 290 C 254 330 252 350 258 372" fill="none" stroke={fur} strokeWidth="26" strokeLinecap="round" />
        <ellipse cx="176" cy="380" rx="18" ry="11" fill={face} {...ink} strokeWidth="3" />
        <ellipse cx="260" cy="380" rx="18" ry="11" fill={face} {...ink} strokeWidth="3" />

        <g className="landing-mascot-body">
          {/* body + belly */}
          <ellipse cx="218" cy="240" rx="64" ry="70" fill={fur} {...ink} />
          <ellipse cx="218" cy="252" rx="40" ry="48" fill={face} />

          {/* head */}
          <g className="landing-mascot-head">
            <circle cx="160" cy="138" r="22" fill={fur} {...ink} />
            <circle cx="160" cy="138" r="11" fill={face} />
            <circle cx="276" cy="138" r="22" fill={fur} {...ink} />
            <circle cx="276" cy="138" r="11" fill={face} />
            <circle cx="218" cy="140" r="56" fill={fur} {...ink} />
            <path d="M178 142 Q 178 112 200 116 Q 218 124 236 116 Q 258 112 258 142 Q 262 182 218 186 Q 174 182 178 142 Z" fill={face} />
            <ellipse cx="202" cy="146" rx="6" ry="7" fill="#3b2a14" />
            <ellipse cx="234" cy="146" rx="6" ry="7" fill="#3b2a14" />
            <circle cx="204" cy="144" r="2" fill="#fff" />
            <circle cx="236" cy="144" r="2" fill="#fff" />
            <path d="M212 160 h12" {...ink} strokeWidth="3" />
            <path d="M204 168 Q 218 180 232 168" fill="none" {...ink} strokeWidth="3" />
            <ellipse cx="190" cy="164" rx="8" ry="5" fill="#e89a8a" opacity="0.5" />
            <ellipse cx="246" cy="164" rx="8" ry="5" fill="#e89a8a" opacity="0.5" />
          </g>

          {/* laptop: we see the back of the lid, with the leaf on it */}
          <path d="M150 286 L 290 286 L 300 296 L 140 296 Z" fill="#9aa5a3" {...ink} strokeWidth="3" />
          <rect x="160" y="212" width="120" height="76" rx="8" fill="#b9c4c2" {...ink} />
          <path d="M210 262 c 14 0 24 -10 24 -24 c -14 0 -24 10 -24 24 Z m 0 0 l 12 -12" fill="none" stroke="#3fae4a" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
          {/* hands on the keyboard, peeking around the lid */}
          <ellipse cx="160" cy="286" rx="15" ry="11" fill={face} {...ink} strokeWidth="3" />
          <ellipse cx="280" cy="286" rx="15" ry="11" fill={face} {...ink} strokeWidth="3" />
        </g>
      </svg>
    </div>
  );
}

export default LandingMascot;
