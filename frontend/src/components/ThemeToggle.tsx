import { useEffect } from "react";
import { usePref, type Prefs } from "../prefs";
import { MoonIcon, SunIcon, SystemIcon } from "./icons";

type Theme = Prefs["theme"];
const ORDER: Theme[] = ["auto", "light", "dark"];
const LOOK: Record<Theme, [typeof SunIcon, string]> = { auto: [SystemIcon, "System theme"], light: [SunIcon, "Light theme"], dark: [MoonIcon, "Dark theme"] };

/** One button that steps through the system default, light and dark; remembered in this browser, and in the account when
 *  signed in (prefs.ts). */
export default function ThemeToggle() {
  const [theme, setTheme] = usePref("theme");
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", theme);
  }, [theme]);
  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
  const [Glyph, label] = LOOK[theme];
  return (
    <button className="icon-btn" onClick={() => setTheme(next)} title={`${label}. Switch to ${LOOK[next][1].toLowerCase()}`} aria-label={`${label}. Switch to ${LOOK[next][1].toLowerCase()}`}>
      <Glyph size={16} stroke={1.75} aria-hidden />
    </button>
  );
}
