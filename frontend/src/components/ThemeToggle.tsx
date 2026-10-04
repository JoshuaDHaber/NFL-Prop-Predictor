import { useEffect, useState } from "react";

type Theme = "auto" | "light" | "dark";
const KEY = "theme";
const OPTIONS: [Theme, string, string][] = [["light", "☀️", "Light"], ["auto", "💻", "Default"], ["dark", "🌙", "Dark"]];

function stored(): Theme {
  try { const v = localStorage.getItem(KEY); if (v === "light" || v === "dark") return v; } catch { /* storage blocked */ }
  return "auto";
}

/** Corner switch between light, dark and the system default; the choice is remembered in this browser. */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(stored);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", theme);
    try { if (theme === "auto") localStorage.removeItem(KEY); else localStorage.setItem(KEY, theme); } catch { /* storage blocked */ }
  }, [theme]);
  return (
    <div className="seg small theme-toggle" role="group" aria-label="Color theme">
      {OPTIONS.map(([t, icon, label]) => (
        <button key={t} className={theme === t ? "on" : ""} aria-pressed={theme === t} title={label} aria-label={label} onClick={() => setTheme(t)}>
          <span className="ico" aria-hidden>{icon}</span>
        </button>
      ))}
    </div>
  );
}
