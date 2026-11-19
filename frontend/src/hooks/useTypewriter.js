import { useCallback, useEffect, useRef, useState } from "react";

// Types `text` into a box one letter at a time (the demo frogs use it so nobody types live).
//   const { type, typing } = useTypewriter(setText, onDone);  then  type("Find me a clip…")
export default function useTypewriter(setText, onDone, msPerLetter = 22) {
  const [typing, setTyping] = useState(false);
  const timer = useRef(null);
  useEffect(() => () => clearInterval(timer.current), []);
  const type = useCallback((text) => {
    clearInterval(timer.current);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setText(text);
      onDone?.();
      return;
    }
    setTyping(true);
    let shown = 0;
    setText("");
    timer.current = setInterval(() => {
      shown += 1;
      setText(text.slice(0, shown));
      if (shown >= text.length) {
        clearInterval(timer.current);
        setTyping(false);
        onDone?.();
      }
    }, msPerLetter);
  }, [setText, onDone, msPerLetter]);
  return { type, typing };
}
