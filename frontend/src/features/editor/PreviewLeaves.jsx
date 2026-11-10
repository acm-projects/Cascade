import { useState } from "react";
import { Leaf } from "../../components/LeafTransition";
import "./PreviewLeaves.css";

const colors = [
  { base: "#178244", light: "#2a9c58", edge: "#0b5029" },
  { base: "#1f8f4a", light: "#35ad5e", edge: "#0f5c32" },
  { base: "#74c02f", light: "#98d63c", edge: "#478a22" },
];

export default function PreviewLeaves({ loading = true }) {
  const [revealed, setRevealed] = useState(false);
  if (!loading && !revealed) setRevealed(true);
  return <div className={`preview-leaves${revealed ? " is-ready" : ""}`} aria-hidden="true">
    {Array.from({ length: 42 }, (_, i) => <div className="preview-leaf" key={i} style={{
      left: `${(i % 7) * 25 - 50}%`,
      top: `${Math.floor(i / 7) * 30 - 65}%`,
      "--turn": `${(i * 47) % 40 - 20}deg`,
      "--fall-turn": `${(i % 2 ? 1 : -1) * (25 + (i * 13) % 45)}deg`,
      "--drift": `${(i * 17) % 35 - 17}%`,
      "--fall-delay": `${(i * 71) % 230}ms`,
      "--fall-duration": `${900 + (i * 31) % 200}ms`,
    }}><Leaf color={colors[i % colors.length]} preserveAspectRatio="none" /></div>)}
  </div>;
}
