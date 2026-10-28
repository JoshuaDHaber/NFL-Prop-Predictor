import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";

const PHONE = "(max-width: 700px)";
const isPhone = () => typeof window !== "undefined" && window.matchMedia(PHONE).matches;
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea, summary, [tabindex]:not([tabindex="-1"])';
/** Panels on screen, newest last: Escape and the focus trap belong to the top one (the slip can sit over the player drawer). */
const stack: object[] = [];

interface Props {
  label: string;
  onClose: () => void;
  /** Extra class on the backdrop (the slip sits above the player drawer). */
  overlayClass?: string;
  children: ReactNode;
}

/** A panel over the page: a drawer from the right on wider screens, a bottom sheet on phones that opens halfway, drags up to
 *  full height (or grows when you scroll it), and drags down to close. Escape and a tap on the backdrop close it too.
 *  Focus moves into the panel, Tab stays inside it, and focus goes back to whatever opened it on close. */
export default function Sheet({ label, onClose, overlayClass = "", children }: Props) {
  const [phone, setPhone] = useState(isPhone);
  const [full, setFull] = useState(false);
  const [drag, setDrag] = useState(0);
  const from = useRef<number | null>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const mq = window.matchMedia(PHONE);
    const on = () => setPhone(mq.matches);
    mq.addEventListener("change", on);
    const me = {};
    stack.push(me);
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panel.current?.focus({ preventScroll: true });
    const keys = (e: KeyboardEvent) => {
      const el = panel.current;
      if (stack[stack.length - 1] !== me || !el) return;   // a panel above this one has the keyboard
      if (e.key === "Escape") { closeRef.current(); return; }
      if (e.key !== "Tab") return;
      const items = [...el.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((f) => f.offsetParent !== null);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1], at = document.activeElement;
      if (!el.contains(at)) { e.preventDefault(); first.focus(); }
      else if (e.shiftKey && (at === first || at === el)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && at === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", keys);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";   // the page behind doesn't scroll while the panel is up
    return () => {
      mq.removeEventListener("change", on);
      document.removeEventListener("keydown", keys);
      document.body.style.overflow = overflow;
      stack.splice(stack.indexOf(me), 1);
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);

  const down = (e: PointerEvent) => {
    from.current = e.clientY;
    try { (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); } catch { /* pointer already gone: the drag still tracks */ }
  };
  // the distance lives in a ref too: the release reads it straight away, without waiting for a render
  const dragged = useRef(0);
  const move = (e: PointerEvent) => { if (from.current != null) { dragged.current = e.clientY - from.current; setDrag(dragged.current); } };
  const up = () => {
    if (from.current == null) return;
    from.current = null;
    const d = dragged.current;
    dragged.current = 0;
    setDrag(0);
    if (d > 110) { if (full) setFull(false); else onClose(); }
    else if (d < -50) setFull(true);
  };
  const style = phone ? { height: `calc(${full ? 94 : 62}dvh - ${Math.min(drag, 0)}px)`, transform: drag > 0 ? `translateY(${drag}px)` : undefined,
    transition: from.current != null ? "none" : undefined } : undefined;
  return (
    <div className={`overlay ${overlayClass}`} onClick={onClose}>
      <aside ref={panel} tabIndex={-1} className={`drawer${phone ? " sheet" : ""}${full ? " full" : ""}`} role="dialog" aria-modal="true" aria-label={label} style={style}
        onClick={(e) => e.stopPropagation()} onScroll={(e) => { if (phone && !full && e.currentTarget.scrollTop > 40) setFull(true); }}>
        {/* a zero-height sticky holder keeps the close button in the corner however far the panel scrolls */}
        <div className="sheet-close"><button className="close" onClick={onClose} aria-label="Close">×</button></div>
        {phone && (
          <div className="sheet-grip" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}
            role="button" aria-label={full ? "Drag down to shrink" : "Drag up to expand"} tabIndex={0}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setFull(!full); }}>
            <span />
          </div>
        )}
        {children}
      </aside>
    </div>
  );
}
