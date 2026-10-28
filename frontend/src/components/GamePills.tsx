import type { Game } from "../api";
import { kickoff } from "../format";
import { useOverflowFade } from "../useOverflowFade";

interface Props {
  games: Game[];
  /** The chosen games; none means every game. */
  selected: string[];
  onChange: (ids: string[]) => void;
  /** Several games at once (tapping toggles one), or just one (tapping picks it). */
  multi?: boolean;
  label?: string;
}

/** The site's game filter: an "All games" pill, then one pill per game (kickoff on hover), scrolling sideways with a fade where more are hidden. */
export default function GamePills({ games, selected, onChange, multi = false, label = "Games" }: Props) {
  const pick = (id: string) => {
    const on = selected.includes(id);
    onChange(!multi ? [id] : on ? selected.filter((x) => x !== id) : [...selected, id]);
  };
  // a fade at either edge says more games are off to that side; the first chosen game is scrolled into view
  const { ref, onScroll, className: fade } = useOverflowFade<HTMLDivElement>(".pill.on", [games.length, selected.join()]);
  return (
    <div ref={ref} className={`pills${fade}`} role="group" aria-label={label} onScroll={onScroll}>
      <button aria-pressed={!selected.length} className={`pill${!selected.length ? " on" : ""}`} onClick={() => onChange([])}>
        All games <span className="pill-count">{games.length}</span>
      </button>
      {games.map((g) => {
        const on = selected.includes(g.game_id);
        return (
          <button key={g.game_id} aria-pressed={on} className={`pill${on ? " on" : ""}`} title={kickoff(g.gameday, g.gametime)} onClick={() => pick(g.game_id)}>
            {g.label}
          </button>
        );
      })}
    </div>
  );
}
