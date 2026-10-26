import BottomNav from "./BottomNav";
import LeagueSwitch from "./LeagueSwitch";
import Logo from "./Logo";
import Menu, { MenuItem } from "./Menu";
import StateBooks from "./StateBooks";
import ThemeToggle from "./ThemeToggle";
import { routeClick } from "./NavLink";

interface Props<T extends string> {
  /** Every section, in order; the ones in `more` sit under the More menu. Omit for a bar with no sections. */
  tabs?: [T, string][];
  more?: T[];
  tab?: T;
  onTab?: (t: T) => void;
  /** Each section's URL, so the sections are real links (open in a new tab, copy the link). */
  href?: (t: T) => string;
}

/** The sticky top line: the brand, the main sections (the rest under More), and the state, league and theme menus. */
export default function TopBar<T extends string>({ tabs = [], more = [], tab, onTab, href }: Props<T>) {
  const main = tabs.filter(([k]) => !more.includes(k));
  const extra = tabs.filter(([k]) => more.includes(k));
  const inMore = extra.find(([k]) => k === tab);
  return (
    <>
    <header className="topbar">
      <h1 className="brand">
        <a href={tabs[0] && href ? href(tabs[0][0]) : "/"} onClick={tabs[0] ? routeClick(() => onTab?.(tabs[0][0])) : undefined} aria-label="The Haber Process: home">
          <Logo size={26} /><span>The Haber <span className="grad">Process</span></span>
        </a>
      </h1>
      {tabs.length > 0 && (
        <nav className="topnav" aria-label="Sections">
          <div className="topnav-main">
            {main.map(([k, label]) => (
              <a key={k} href={href?.(k)} className={`topnav-item${tab === k ? " on" : ""}`} aria-current={tab === k ? "page" : undefined} onClick={routeClick(() => onTab?.(k))}>{label}</a>
            ))}
          </div>
          {extra.length > 0 && (
            <Menu label={inMore ? inMore[1] : "More"} buttonClass={`topnav-item${inMore ? " on" : ""}`} align="start">
              {(close) => extra.map(([k, label]) => <MenuItem key={k} on={tab === k} href={href?.(k)} onClick={() => { close(); onTab?.(k); }}>{label}</MenuItem>)}
            </Menu>
          )}
        </nav>
      )}
      <div className="topbar-actions">
        <StateBooks />
        <LeagueSwitch />
        <ThemeToggle />
      </div>
    </header>
    {/* outside the header: its backdrop blur would make a fixed child sit inside it rather than on the screen */}
    {tabs.length > 0 && <BottomNav tabs={[...main, ...extra]} tab={tab} onTab={onTab} href={href} />}
    </>
  );
}
