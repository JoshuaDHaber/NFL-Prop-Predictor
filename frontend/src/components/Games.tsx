import type { ReactNode } from "react";
import type { Game, InjuryReport, MoneylineGame, Pick } from "../api";
import { KIND_LABEL, americanOdds, kickoff, pct, signedPct, weatherShort, weatherText, notableWeather } from "../format";
import { gameStatusCounts } from "./Injuries";
import { favored } from "./Moneylines";
import { blowoutAt } from "./Blowout";
import TeamLogo from "./TeamLogo";
import { getLeague } from "../league";
import { matchupColors, shadeVars } from "../teams";
import { BookName } from "./BookBadge";
import { InjuryIcon, WeatherIcon } from "./icons";
import SidePill from "./SidePill";

interface Props {
  games: Game[];
  /** Positive-EV plays across the slate, any order. */
  picks: Pick[];
  moneylines: MoneylineGame[];
  injuries?: InjuryReport;
  onOpen: (gameId: string) => void;
}

/** "Dome", "19 mph" (with a wind icon), "72°F": the one weather fact worth a glance on a tile. */
function weatherBit(g: Game): ReactNode {
  const w = g.weather;
  if (!w) return null;
  if (w.indoor) return weatherText(w);
  if (notableWeather(w)) { const { icon, text } = weatherShort(w); return <span className="with-icon"><WeatherIcon name={icon} />{text}</span>; }
  return w.temp != null ? `${Math.round(w.temp)}°F` : null;
}

function Tile({ g, picks, ml, injuries, onOpen }: { g: Game; picks: Pick[]; ml?: MoneylineGame; injuries?: InjuryReport; onOpen: Props["onOpen"] }) {
  const [, , away, home] = g.game_id.split("_");
  const top = picks[0];
  const inj = injuries ? gameStatusCounts([...(injuries.teams[away] ?? []), ...(injuries.teams[home] ?? [])]) : null;
  const injText = inj && [inj.out && `${inj.out} out`, inj.doubtful && `${inj.doubtful} doubtful`, inj.questionable && `${inj.questionable} questionable`, inj.dayToDay && `${inj.dayToDay} day-to-day`].filter(Boolean).join(" · ");
  const [a, h] = ml?.sides ?? [];
  const wx = weatherBit(g);
  const blow = blowoutAt(ml);
  const [awayColor, homeColor] = matchupColors(away, home);
  return (
    <button className="gt" onClick={() => onOpen(g.game_id)} aria-label={`Open ${g.label}`}>
      <span className="gt-top"><span>{kickoff(g.gameday, g.gametime)}</span>{wx && <span>{wx}</span>}</span>
      <span className="gt-match">
        <span className="gt-team"><TeamLogo team={away} /><span><b>{away}</b>{a && <small>{pct(a.prob, 0)}</small>}</span></span>
        <span className="gt-at">@</span>
        <span className="gt-team home"><span><b>{home}</b>{h && <small>{pct(h.prob, 0)}</small>}</span><TeamLogo team={home} /></span>
      </span>
      {a && h
        ? <span className="ml-bar gt-bar" aria-hidden><i className="tbar" style={{ width: `${a.prob * 100}%`, ...shadeVars(awayColor) }} /><i className="tbar" style={{ width: `${h.prob * 100}%`, ...shadeVars(homeColor) }} /></span>
        : <span className="gt-bar gt-bar-empty" aria-hidden />}
      <span className="gt-line mut">{ml ? (ml.spread != null ? `Spread: ${favored(ml, ml.spread)}` : `Model: ${favored(ml, ml.margin)}`) : "No moneyline yet"}{ml?.total != null && ` · Total ${ml.total}`}</span>
      {blow && <span className={`gt-line gt-blow mut${blow.p >= 0.3 ? " hot" : ""}`} title="Chance the game is decided by 20 or more points, either way">20+ pt blowout: <b>{pct(blow.p, 0)}</b></span>}
      <span className="gt-prop">
        <span className="tile-label">Top prop</span>
        {top ? <>
          <span className="gt-prop-main"><b>{top.name}</b> <SidePill kind={top.kind} side={top.side} line={top.line} /></span>
          <span className="mut">{KIND_LABEL[top.kind]} · {americanOdds(top.odds)} <BookName book={top.book} size={14} /> · <span className="ev-text">{signedPct(top.ev)} EV</span></span>
        </> : <span className="mut">No +EV props yet</span>}
      </span>
      <span className="gt-foot">
        <span>{picks.length ? `${picks.length} +EV prop${picks.length === 1 ? "" : "s"}` : ""}</span>
        <span>{inj == null ? "" : injText ? <span className="with-icon"><InjuryIcon size={14} stroke={1.75} aria-hidden />{injText}</span> : getLeague() === "nba" ? "No injuries listed" : "No game statuses yet"}</span>
      </span>
      <span className="gt-go">Game overview →</span>
    </button>
  );
}

/** The slate: one tile per game with its win chances, top prop and injury count. A tile opens that game's overview. */
export default function Games({ games, picks, moneylines, injuries, onOpen }: Props) {
  if (!games.length) return <div className="card empty">No games on the slate yet. They appear after the next scheduled sync.</div>;
  const nba = getLeague() === "nba";
  const byGame = new Map<string, Pick[]>();
  for (const p of [...picks].filter((p) => !p.flagged).sort((x, y) => y.ev - x.ev)) byGame.set(p.game_id, [...(byGame.get(p.game_id) ?? []), p]);
  const mlByGame = new Map(moneylines.map((m) => [m.game_id, m]));
  return (
    <section className="gt-grid" aria-label={nba ? "Upcoming games" : "This week's games"}>
      {games.map((g) => <Tile key={g.game_id} g={g} picks={byGame.get(g.game_id) ?? []} ml={mlByGame.get(g.game_id)} injuries={injuries} onOpen={onOpen} />)}
    </section>
  );
}
