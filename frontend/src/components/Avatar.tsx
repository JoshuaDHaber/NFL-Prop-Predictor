import { useState } from "react";

const initials = (name: string) => name.split(/\s+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
const hue = (s: string) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);

/** Player headshot with an initials fallback, so a missing or broken image never leaves a hole. */
export default function Avatar({ name, src, size = 40 }: { name: string; src?: string | null; size?: number }) {
  const [failed, setFailed] = useState(false);
  const h = hue(name);
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.36, background: `linear-gradient(135deg, hsl(${h} 70% 50%), hsl(${(h + 40) % 360} 70% 38%))` }}>
      {src && !failed ? <img src={src} alt={name} loading="lazy" onError={() => setFailed(true)} /> : initials(name)}
    </span>
  );
}
