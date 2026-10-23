import { useEffect, useState } from "react";
import { MoonIcon, SunIcon, SystemIcon } from "./icons";

type Theme = "auto" | "light" | "dark";
const KEY = "theme";
const ORDER: Theme[] = ["auto", "light", "dark"];
const LOOK: Record<Theme, [typeof SunIcon, string]> = { auto: [SystemIcon, "System theme"], light: [SunIcon, "Light theme"], dark: [MoonIcon, "Dark theme"] };

function stored(): Theme {
  try { const v = localStorage.getItem(KEY); if (v === "light" || v === "dark") return v; } catch { /* storage blocked */ }
  return "auto";
}

/** One button that steps through the system default, light and dark; the choice is remembered in this browser. */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(stored);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", theme);
    try { if (theme === "auto") localStorage.removeItem(KEY); else localStorage.setItem(KEY, theme); } catch { /* storage blocked */ }
  }, [theme]);
  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
  const [Glyph, label] = LOOK[theme];
  return (
    <button className="icon-btn" onClick={() => setTheme(next)} title={`${label}. Switch to ${LOOK[next][1].toLowerCase()}`} aria-label={`${label}. Switch to ${LOOK[next][1].toLowerCase()}`}>
      <Glyph size={16} stroke={1.75} aria-hidden />
    </button>
  );
}
