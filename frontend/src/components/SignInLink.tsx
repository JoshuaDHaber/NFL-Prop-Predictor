import { useEffect, useRef, useState } from "react";
import { verifyLink } from "../auth";
import { BASE } from "../env";
import Logo from "./Logo";
import { openSignIn } from "./SignIn";
import ThemeToggle from "./ThemeToggle";

/** /signin#t=<token>: where the emailed link lands. The token is in the #fragment and is spent only by this page's POST, so a
 *  mail scanner opening the link can't use it up. Signed in, it goes back to the page the visitor started from. */
export default function SignInLink() {
  const [problem, setProblem] = useState("");
  const started = useRef(false);   // StrictMode runs effects twice in development; the token is good once
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const token = new URLSearchParams(window.location.hash.slice(1)).get("t");
    window.history.replaceState(null, "", window.location.pathname);   // the token leaves the address bar and history
    if (!token) { setProblem("This sign-in link is incomplete. Copy the whole link from the email, or send yourself a new one."); return; }
    verifyLink(token).then((s) => window.location.replace(s.next || BASE), (err) => setProblem((err as Error).message));
  }, []);
  return (
    <div className="wrap">
      <header>
        <div>
          <h1><Logo /> The Haber <span className="grad">Process</span></h1>
          <div className="sub"><a href={BASE}>← Back to the site</a></div>
        </div>
        <div className="head-actions"><ThemeToggle /></div>
      </header>
      <div className="card admin-signin">
        {problem ? <>
          <b>Couldn't sign you in</b>
          <p className="mut">{problem}</p>
          <button className="primary" onClick={() => openSignIn()}>Send a new link</button>
        </> : <>
          <b>Signing you in…</b>
          <p className="mut">One moment.</p>
        </>}
      </div>
    </div>
  );
}
