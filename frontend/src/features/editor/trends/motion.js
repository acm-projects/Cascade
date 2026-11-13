// Small motion helpers for the Trend Analysis page. Everything plays once and respects
// "reduce motion"; nothing animates continuously in the background.
import { useEffect, useRef, useState } from 'react';

const query = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

/** true when the person asked their system for less motion */
export function useReducedMotion() {
  const [reduced, setReduced] = useState(() => Boolean(query?.matches));
  useEffect(() => {
    if (!query) return undefined;
    const update = () => setReduced(query.matches);
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return reduced;
}

/** Phones and touch screens get the simple version of the effects. */
export function useSimpleMotion() {
  const reduced = useReducedMotion();
  const [small, setSmall] = useState(() => typeof window !== 'undefined' && window.matchMedia?.('(max-width: 760px), (pointer: coarse)').matches);
  useEffect(() => {
    const mq = window.matchMedia?.('(max-width: 760px), (pointer: coarse)');
    if (!mq) return undefined;
    const update = () => setSmall(mq.matches);
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);
  return reduced || small;
}

/** Reveal once: returns [ref, shown]. The element fades up the first time it scrolls into view. */
export function useReveal(rootRef, { threshold = 0.15 } = {}) {
  const ref = useRef(null);
  const [shown, setShown] = useState(() => typeof IntersectionObserver === 'undefined');
  useEffect(() => {
    const node = ref.current;
    if (!node || shown) return undefined;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) { setShown(true); observer.disconnect(); }
    }, { root: rootRef?.current || null, threshold, rootMargin: '0px 0px -8% 0px' });
    observer.observe(node);
    return () => observer.disconnect();
  }, [rootRef, threshold, shown]);
  return [ref, shown];
}

/** Count a number up from 0 once, the first time `start` is true. */
export function useCountUp(value, start, duration = 900) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(null);
  const done = useRef(false);
  useEffect(() => {
    if (!start || !Number.isFinite(value)) return undefined;
    if (done.current || reduced) { done.current = true; setShown(value); return undefined; } // later changes: no replay
    done.current = true;
    let frame; const t0 = performance.now();
    const step = now => {
      const p = Math.min(1, (now - t0) / duration), eased = 1 - (1 - p) ** 3;
      setShown(value * eased);
      if (p < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value, start, duration, reduced]);
  return shown ?? 0;
}
