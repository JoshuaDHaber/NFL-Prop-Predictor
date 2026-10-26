import { useEffect, useRef, useState, type ReactNode } from "react";
import { routeClick } from "./NavLink";

export const Caret = () => (
  <svg className="caret" width="10" height="6" viewBox="0 0 10 6" aria-hidden="true">
    <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

interface Props {
  label: ReactNode;
  ariaLabel?: string;
  /** The button's class: "chip-menu" (a small pill) by default. */
  buttonClass?: string;
  /** Which edge of the button the popover lines up with. */
  align?: "start" | "end";
  /** Open below the button, or above it (the phone's bottom bar). */
  placement?: "down" | "up";
  caret?: boolean;
  children: (close: () => void) => ReactNode;
}

/** A button that opens a small popover below it; a click outside or Escape closes it. */
export default function Menu({ label, ariaLabel, buttonClass = "chip-menu", align = "end", placement = "down", caret = true, children }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div className="menu" ref={ref}>
      <button className={buttonClass} aria-haspopup="true" aria-expanded={open} aria-label={ariaLabel} onClick={() => setOpen(!open)}>
        {label}{caret && <Caret />}
      </button>
      {open && <div className={`menu-pop ${align} ${placement}`}>{children(() => setOpen(false))}</div>}
    </div>
  );
}

/** One choice in a Menu, checked when it's the current one. With href it's a link (a section), which a plain click still
 *  routes through onClick. */
export function MenuItem({ on, onClick, href, children }: { on?: boolean; onClick: () => void; href?: string; children: ReactNode }) {
  if (href) return (
    <a className="menu-item" href={href} aria-current={on ? "page" : undefined} onClick={routeClick(onClick)}>
      <span>{children}</span>{on && <span className="menu-check" aria-hidden="true">✓</span>}
    </a>
  );
  return (
    <button className="menu-item" role="menuitemradio" aria-checked={!!on} onClick={onClick}>
      <span>{children}</span>{on && <span className="menu-check" aria-hidden="true">✓</span>}
    </button>
  );
}
