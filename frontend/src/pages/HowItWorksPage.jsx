import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { createPondScene } from "../features/howItWorks/pondScene";
import Icon from "../components/ui/Icon";
import "./HowItWorksPage.css";

// "How it works": a 3D pond where a frog leaps across four lily pads, one per stage of Cascade.
// Click a pad, a stage tag, the arrows, or press the arrow keys to send the frog hopping.
// The 3D lives in features/howItWorks/pondScene.js; this page draws the words on top.
const STAGES = [
  {
    name: "Upload",
    title: "Drop in one long video",
    text: "A stream, a podcast, a lecture or a vlog. Upload it once and Cascade takes it from there.",
    icon: "cloud",
  },
  {
    name: "Find",
    title: "AI finds the best moments",
    text: "In AI Studio, ask for what you want, like \"10 funny clips\". Cascade picks them out, and you keep the ones you like.",
    icon: "sparkles",
  },
  {
    name: "Edit",
    title: "Make each clip yours",
    text: "In the Editor, trim, reframe for phones, and add captions, B-roll and music.",
    icon: "scissors",
  },
  {
    name: "Post",
    title: "A week of content",
    text: "Export every clip ready for TikTok, Reels and Shorts. One video in, a week of posts out.",
    icon: "send",
  },
];

function HowItWorksPage() {
  const holderRef = useRef(null);
  const labelRefs = useRef([]);
  const sceneRef = useRef(null);
  const [stage, setStage] = useState(1);   // the pad the frog is sitting on

  useEffect(() => {
    const holder = holderRef.current;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // A new canvas each time: once a canvas's 3D is shut down, it can't be started again
    const canvas = document.createElement("canvas");
    canvas.className = "hiw-canvas";
    holder.append(canvas);
    try {
      sceneRef.current = createPondScene(canvas, { still, labels: labelRefs.current, onStage: setStage });
    } catch {
      canvas.remove();   // no 3D on this device: the words still work
    }
    return () => {
      sceneRef.current?.stop();
      sceneRef.current = null;
      canvas.remove();
    };
  }, []);

  const goTo = useCallback((next) => {
    const target = Math.max(1, Math.min(STAGES.length, next));
    if (sceneRef.current) sceneRef.current.goTo(target);
    else setStage(target);
  }, []);

  // Left and right arrow keys hop backwards and forwards
  useEffect(() => {
    function handleKey(event) {
      if (event.key === "ArrowRight") goTo(stage + 1);
      if (event.key === "ArrowLeft") goTo(stage - 1);
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [stage, goTo]);

  const current = STAGES[stage - 1];

  return (
    <div className="hiw">
      <div ref={holderRef} className="hiw-world" />

      <header className="hiw-top">
        <h1 className="hiw-title">How it works?</h1>
        <Link to="/projects" className="hiw-back"><Icon name="undo" /> Back to projects</Link>
      </header>

      {/* The stage tags; the 3D scene moves each one next to its lily pad */}
      <div className="hiw-labels">
        {STAGES.map((item, i) => (
          <button key={item.name} type="button" ref={(el) => { labelRefs.current[i] = el; }}
            className={`hiw-tag${stage === i + 1 ? " active" : ""}`} onClick={() => goTo(i + 1)}>
            Stage {i + 1}
          </button>
        ))}
      </div>

      <section className="hiw-panel" aria-live="polite">
        <div className="hiw-panel-icon"><Icon name={current.icon} /></div>
        <div className="hiw-panel-words">
          <p className="hiw-panel-step">Stage {stage} of {STAGES.length} · {current.name}</p>
          <h2 className="hiw-panel-title">{current.title}</h2>
          <p className="hiw-panel-text">{current.text}</p>
        </div>
        <div className="hiw-panel-nav">
          <div className="hiw-dots" role="tablist" aria-label="Stages">
            {STAGES.map((item, i) => (
              <button key={item.name} type="button" role="tab" aria-selected={stage === i + 1} aria-label={`Stage ${i + 1}: ${item.name}`}
                className={`hiw-dot${stage === i + 1 ? " active" : ""}`} onClick={() => goTo(i + 1)} />
            ))}
          </div>
          <div className="hiw-arrows">
            <button type="button" className="hiw-arrow" onClick={() => goTo(stage - 1)} disabled={stage === 1} aria-label="Previous stage">
              <Icon name="chevronRight" className="hiw-flip" />
            </button>
            {stage < STAGES.length ? (
              <button type="button" className="hiw-arrow hiw-next" onClick={() => goTo(stage + 1)}>
                Hop <Icon name="chevronRight" />
              </button>
            ) : (
              <Link to="/projects" className="hiw-arrow hiw-next">Start <Icon name="arrowRight" /></Link>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

export default HowItWorksPage;
