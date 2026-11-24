import DolphinLoader from "./DolphinLoader";
import "./DolphinCurtain.css";

// The page change between AI Studio, the Editor and Export (LeafTransition.jsx runs it): the pixel sea fades in
// over the screen with the 3D dolphins leaping (DolphinLoader), the next page loads behind it, and once that page
// says it's ready the sea fades away, showing the page fully loaded. It replaced the pixel waterfall
// (WaterfallCurtain.jsx, no longer used).
//   phase - "cover" (fading in), "hold" (covering, while the next page loads), "reveal" (fading away)
//   label - what's loading, shown under the dolphins ("Opening the Editor")
function DolphinCurtain({ phase, label }) {
  return (
    <div className={`dolphin-curtain is-${phase}`}>
      <DolphinLoader label={label} />
    </div>
  );
}

export default DolphinCurtain;
