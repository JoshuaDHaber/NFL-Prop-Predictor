import type { ReactNode } from "react";
import Avatar from "./Avatar";

export interface Tile { key: string; label: string; name: string; meta: string; value: ReactNode; caption: string; onClick?: () => void }

/** A row of highlight tiles: the best item on the page, front and centre. */
export default function TopTiles({ tiles }: { tiles: Tile[] }) {
  if (!tiles.length) return null;
  return (
    <section className="tiles" aria-label="Top rated">
      {tiles.map((t, i) => {
        const Tag = t.onClick ? "button" : "div";
        return (
          <Tag key={t.key} className={`tile${i === 0 ? " lead" : ""}`} onClick={t.onClick}>
            <span className="tile-label">{i === 0 ? "★ " : ""}{t.label}</span>
            <span className="tile-who"><Avatar name={t.name} size={38} /><span><b>{t.name}</b><small>{t.meta}</small></span></span>
            <span className="tile-value">{t.value}</span>
            <span className="tile-cap">{t.caption}</span>
          </Tag>
        );
      })}
    </section>
  );
}
