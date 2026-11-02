import { IconArrowDown, IconArrowUp } from "@tabler/icons-react";
import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { deleteAccount, signOut, useAuth } from "../auth";
import { MAX_FAV_TEAMS, setFavTeams, toggled, useFavorites } from "../favorites";
import { getLeague, type League } from "../league";
import { MAIN_TABS, usePref, type MainTab, type Prefs } from "../prefs";
import { teamsOf } from "../teams";
import { AccountAvatar } from "./AccountMenu";
import BookSelect from "./BookSelect";
import { FavStar, LeagueIcon, MoonIcon, SunIcon, SystemIcon } from "./icons";
import TeamLogo from "./TeamLogo";
import { openSignIn } from "./SignIn";

const TAB_LABELS: Record<MainTab, string> = { games: "Games", picks: "Best props", parlays: "Parlays", hot: "Who's Hot", projections: "Projections" };
const THEMES: [Prefs["theme"], string, typeof SunIcon][] = [["auto", "System", SystemIcon], ["light", "Light", SunIcon], ["dark", "Dark", MoonIcon]];

/** The preferences page (/account): who's signed in, and the settings that follow the account to every device. Signed out,
 *  the same settings still work, kept in this browser. */
export default function Preferences({ books }: { books: string[] }) {
  const auth = useAuth();
  const qc = useQueryClient();
  const user = auth?.user;
  const [theme, setTheme] = usePref("theme");
  const [gameBook, setGameBook] = usePref("game_book");
  const [onePer, setOnePer] = usePref("one_per_player");
  const [detailed, setDetailed] = usePref("detailed_cards");
  const [problem, setProblem] = useState("");
  const after = () => { qc.invalidateQueries({ queryKey: ["meta"] }); qc.removeQueries({ queryKey: ["admin"] }); };
  const remove = async () => {
    if (!window.confirm(`Delete the account for ${user!.email}? Your saved preferences and favorites go with it. This can't be undone.`)) return;
    try { await deleteAccount(); after(); } catch (err) { setProblem((err as Error).message); }
  };

  return (
    <div className="prefs">
      <section className="card prefs-card">
        <h3 className="sub-h">Account</h3>
        {user ? <>
          <div className="prefs-who">
            <AccountAvatar user={user} size={40} />
            <div>{user.name && <b>{user.name}</b>}<span className="mut">{user.email}</span></div>
          </div>
          <p className="mut">Your preferences are saved to your account, so they follow you to every device you sign in on.</p>
          <div className="prefs-actions">
            <button className="primary outline" onClick={async () => { await signOut().catch(() => {}); after(); }}>Sign out</button>
            <button className="link danger" onClick={remove}>Delete account</button>
          </div>
          {problem && <p className="err">{problem}</p>}
        </> : <>
          <p className="mut">Your preferences are saved in this browser only. Sign in to keep them on every device.</p>
          <div className="prefs-actions"><button className="primary" onClick={() => openSignIn()} disabled={!auth}>Sign in</button></div>
        </>}
      </section>

      <section className="card prefs-card">
        <h3 className="sub-h">Theme</h3>
        <div className="seg" role="group" aria-label="Theme">
          {THEMES.map(([t, label, Glyph]) => (
            <button key={t} className={theme === t ? "on" : ""} aria-pressed={theme === t} onClick={() => setTheme(t)}>
              <Glyph size={15} stroke={1.75} aria-hidden className="icon" />{label}
            </button>
          ))}
        </div>
        <p className="mut">System follows your device's light or dark setting.</p>
      </section>

      <section className="card prefs-card">
        <h3 className="sub-h">Default sportsbook</h3>
        <div><BookSelect books={books} book={gameBook} allLabel="Every book (best price)" onChange={setGameBook} ariaLabel="Default sportsbook" /></div>
        <p className="mut">The book Best props, Parlays and game pages open at. You can still switch on any page.</p>
      </section>

      <section className="card prefs-card">
        <h3 className="sub-h">Best props</h3>
        <label className="admin-toggle">
          <input type="checkbox" checked={onePer} onChange={(e) => setOnePer(e.target.checked)} />
          <span>One pick per player</span>
        </label>
        <p className="mut">Shows each player's best pick, with a "+N related" tag for the rest. A player's picks win or lose together.</p>
        <label className="admin-toggle">
          <input type="checkbox" checked={detailed} onChange={(e) => setDetailed(e.target.checked)} />
          <span>Every number on the cards</span>
        </label>
        <p className="mut">On phones, each pick's card shows every number instead of just the player, pick, win chance and EV.</p>
      </section>

      <TabOrder />

      <section className="card prefs-card prefs-wide">
        <h3 className="sub-h">Your teams</h3>
        <p className="mut">{user?.age_confirmed ? `Their games come first on the Games tab, starred. Up to ${MAX_FAV_TEAMS} per league.`
          : user ? "Confirm you're 21 or older to save your teams." : "Sign in to save your teams: their games come first on the Games tab, starred."}</p>
        {(getLeague() === "nba" ? ["nba", "nfl"] as const : ["nfl", "nba"] as const).map((l) => <FavTeams key={l} league={l} />)}
      </section>
    </div>
  );
}

/** One league's teams as toggles, logo and abbreviation; a tap saves to the account (signed out, it opens sign-in, as the
 *  player drawer's star does). */
function FavTeams({ league }: { league: League }) {
  const { teams, ready, loading } = useFavorites(league);
  const signedIn = !!useAuth()?.user;
  const [problem, setProblem] = useState("");
  const full = teams.length >= MAX_FAV_TEAMS;
  const toggle = (t: string) => {
    if (!ready) return openSignIn();
    setProblem("");
    setFavTeams(league, toggled(teams, t, (x) => x === t)).catch((err) => setProblem((err as Error).message));
  };
  return (
    <div className="fav-teams">
      <h4><LeagueIcon league={league} size={14} />{league.toUpperCase()}</h4>
      <div className="fav-team-grid" role="group" aria-label={`Favorite ${league.toUpperCase()} teams`}>
        {teamsOf(league).map((t) => {
          const on = teams.includes(t);
          return (
            <button key={t} type="button" className="chip-btn fav-team" aria-pressed={on} disabled={loading || (signedIn && !ready) || (!on && full)} onClick={() => toggle(t)}>
              <TeamLogo team={t} league={league} size={22} /><span>{t}</span>{on && <FavStar on size={13} />}
            </button>
          );
        })}
      </div>
      {problem && <p className="err">{problem}</p>}
    </div>
  );
}

/** The main sections' order in the top bar (and the phone tab bar's first slots): saved to the account, so signed in and
 *  21+ confirmed only, as Your teams is. */
function TabOrder() {
  const user = useAuth()?.user;
  const [order, setOrder] = usePref("tab_order");
  const [moved, setMoved] = useState("");
  const list = useRef<HTMLOListElement>(null);
  const move = (i: number, by: number) => {
    const next = [...order];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    setOrder(next);
    setMoved(`${TAB_LABELS[next[i + by]]} moved to ${i + by + 1} of ${next.length}`);
    // at either end the pressed arrow is disabled: keep the keyboard on the row by moving to its other arrow
    const to = i + by;
    if (to === 0 || to === next.length - 1) {
      requestAnimationFrame(() => list.current?.children[to]?.querySelector<HTMLButtonElement>(`button:not(:disabled)`)?.focus());
    }
  };
  const usual = order.join() === MAIN_TABS.join();
  return (
    <section className="card prefs-card">
      <h3 className="sub-h">Tab order</h3>
      {user?.age_confirmed ? <>
        <ol className="tab-order" aria-label="Tab order" ref={list}>
          {order.map((t, i) => (
            <li key={t}>
              <span>{TAB_LABELS[t]}</span>
              <button className="icon-btn" onClick={() => move(i, -1)} disabled={i === 0} aria-label={`Move ${TAB_LABELS[t]} up`}><IconArrowUp size={16} stroke={1.75} aria-hidden /></button>
              <button className="icon-btn" onClick={() => move(i, 1)} disabled={i === order.length - 1} aria-label={`Move ${TAB_LABELS[t]} down`}><IconArrowDown size={16} stroke={1.75} aria-hidden /></button>
            </li>
          ))}
        </ol>
        <p className="sr-only" role="status" aria-live="polite">{moved}</p>
        <p className="mut">The order of the sections along the top. On phones, the first three get the bottom bar.
          {!usual && <> <button className="link" onClick={() => { setOrder([...MAIN_TABS]); setMoved("Tab order reset"); }}>Reset</button></>}</p>
      </> : <p className="mut">{user ? "Confirm you're 21 or older to save your tab order." : "Sign in to choose your tab order: the sections along the top, in the order you use them."}</p>}
    </section>
  );
}
