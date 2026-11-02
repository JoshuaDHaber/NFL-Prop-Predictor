import { useQueryClient } from "@tanstack/react-query";
import { IconUser } from "@tabler/icons-react";
import { signOut, useAuth, type Account } from "../auth";
import Menu, { MenuItem } from "./Menu";
import { openSignIn } from "./SignIn";

export type AccountPage = "account" | "bets" | "admin";

export function AccountAvatar({ user, size = 20 }: { user: Account; size?: number }) {
  const initial = (user.name || user.email)[0].toUpperCase();
  return user.avatar_url
    ? <img className="acct-avatar" src={user.avatar_url} alt="" width={size} height={size} referrerPolicy="no-referrer" />
    : <span className="acct-avatar acct-initial" style={{ width: size, height: size, fontSize: size * .55 }} aria-hidden="true">{initial}</span>;
}

/** The top bar's account control: "Sign in" when signed out; signed in, a menu with the preferences page, the admin page
 *  (for admins) and sign out. Nothing until the server has said who's signed in, so it never flickers. */
export default function AccountMenu({ href, onPage, page }: { href: (p: AccountPage) => string; onPage: (p: AccountPage) => void; page?: string }) {
  const auth = useAuth();
  const qc = useQueryClient();
  if (!auth) return null;
  const user = auth.user;
  if (!user) return (
    <button className="chip-menu" onClick={() => openSignIn()} aria-label="Sign in">
      <IconUser size={16} stroke={1.75} aria-hidden /><span className="acct-label">Sign in</span>
    </button>
  );
  return (
    <Menu label={<AccountAvatar user={user} />} ariaLabel={`Account: ${user.email}`} buttonClass="chip-menu acct-chip">
      {(close) => <>
        <div className="acct-who">
          {user.name && <b>{user.name}</b>}
          <span className="mut">{user.email}</span>
        </div>
        <MenuItem on={page === "bets"} href={href("bets")} onClick={() => { close(); onPage("bets"); }}>My bets</MenuItem>
        <MenuItem on={page === "account"} href={href("account")} onClick={() => { close(); onPage("account"); }}>Preferences</MenuItem>
        {user.is_admin && <MenuItem on={page === "admin"} href={href("admin")} onClick={() => { close(); onPage("admin"); }}>Admin</MenuItem>}
        <MenuItem onClick={async () => { close(); await signOut().catch(() => {}); qc.invalidateQueries({ queryKey: ["meta"] }); qc.removeQueries({ queryKey: ["admin"] }); }}>Sign out</MenuItem>
      </>}
    </Menu>
  );
}
