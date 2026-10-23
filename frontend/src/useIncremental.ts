import { useEffect, useRef, useState } from "react";

/**
 * The first `step` rows, growing by `step` as a sentinel element nears the viewport. A board of thousands of rows
 * (the NBA's ~5,000 projections) is too many DOM nodes for a tablet to scroll; new rows start over at `step`.
 */
export function useIncremental<T>(rows: T[], step = 100) {
  const [shown, setShown] = useState(step);
  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => setShown(step), [rows, step]);
  const more = shown < rows.length;
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !more || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && setShown((n) => n + step), { rootMargin: "800px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [more, step, shown]);
  return { visible: rows.slice(0, shown), more, showMore: () => setShown((n) => n + step), sentinel };
}
