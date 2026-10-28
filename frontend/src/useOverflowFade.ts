import { useEffect, useRef, useState } from "react";

/** For a row that scrolls sideways (pills, tabs): which edges have more to scroll to, so the row can fade there, and the
 *  `selector` element (the active pill or tab) kept in view when `deps` change. Put `ref` and `onScroll` on the row. */
export function useOverflowFade<T extends HTMLElement>(selector: string, deps: unknown[]) {
  const ref = useRef<T>(null);
  const [fade, setFade] = useState({ l: false, r: false });
  const measure = () => {
    const el = ref.current;
    if (!el) return;
    const l = el.scrollLeft > 4, r = el.scrollLeft + el.clientWidth < el.scrollWidth - 4;
    setFade((f) => (f.l === l && f.r === r ? f : { l, r }));
  };
  useEffect(() => {
    const el = ref.current, on = el?.querySelector<HTMLElement>(selector);
    if (el && on && (on.offsetLeft < el.scrollLeft || on.offsetLeft + on.offsetWidth > el.scrollLeft + el.clientWidth)) el.scrollLeft = on.offsetLeft - 16;
    measure();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);
  const className = `${fade.l ? " fade-l" : ""}${fade.r ? " fade-r" : ""}`;
  return { ref, onScroll: measure, className };
}
