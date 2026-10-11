import { useEffect, useRef, useState } from "react";
import "./BlimpSection.css";
import cloud from "../assets/cloud.png";
import blimp from "../assets/blimp2.png";

function BlimpSection() {
  const sectionRef = useRef(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    function handleScroll() {
      const rect = sectionRef.current.getBoundingClientRect();
      // 0 = section's top is at the bottom of the screen
      // 1 = section's top has reached the top of the screen
      const p = (window.innerHeight - rect.top) / window.innerHeight;
      setProgress(Math.min(Math.max(p, 0), 1));
    }

    handleScroll();
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const shift = progress * 40; // how far the clouds travel, in vw

  return (
    <div className="blimp-section" ref={sectionRef}>
      {/* Blimp comes FIRST so the clouds are drawn on top of it */}
      <img src={blimp} alt="Blimp with banner" className="blimp2" />

      <img
        src={cloud}
        alt=""
        className="cloud cloud-left"
        style={{ transform: `translateX(-${shift}vw)` }}
      />
      <img
        src={cloud}
        alt=""
        className="cloud cloud-right"
        style={{ transform: `translateX(${shift}vw)` }}
      />
    </div>
  );
}

export default BlimpSection;