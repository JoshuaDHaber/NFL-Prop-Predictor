import React, { useEffect, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { setAllowedBooks } from "./api";
import { leagueFromPath, leaguePath } from "./route";
import { BetSlipProvider, useBetSlip } from "./BetSlipContext";
import { allowedBooks } from "./legalBooks";
import { LeagueContext } from "./LeagueContext";
import { getLeague, setLeague as storeLeague, type League } from "./league";
import "./styles.css";

const newClient = () => new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 30_000 } } });
// one cache per league: both sides use the same query keys (["meta"], ["picks", ...]) for different endpoints
const clients: Record<League, QueryClient> = { nfl: newClient(), nba: newClient() };

function Root() {
  const [league, setLeagueState] = useState<League>(getLeague);
  // only the sportsbooks legal where the bettor is: set before any query runs, and every cached query is refetched when it changes
  const { state, allBooks } = useBetSlip();
  const allowed = allowedBooks(state, allBooks);
  setAllowedBooks(allowed);
  const booksKey = allowed?.join() ?? "*";
  const lastBooks = useRef(booksKey);
  useEffect(() => {
    if (lastBooks.current === booksKey) return;
    lastBooks.current = booksKey;
    Object.values(clients).forEach((c) => c.resetQueries());
  }, [booksKey]);
  const setLeague = (l: League) => {
    storeLeague(l);
    // each league has its own sections and games: switching lands on the other league's front page
    window.history.pushState(null, "", leaguePath(l));
    window.scrollTo({ top: 0 });
    setLeagueState(l);
  };
  // back and forward can cross between /nba/... and the NFL's pages
  useEffect(() => {
    const sync = () => {
      const l = leagueFromPath();
      if (l && l !== getLeague()) { storeLeague(l); setLeagueState(l); }
    };
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  return (
    <LeagueContext.Provider value={{ league, setLeague }}>
      <QueryClientProvider client={clients[league]} key={league}>
        <App />
      </QueryClientProvider>
    </LeagueContext.Provider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BetSlipProvider>
      <Root />
    </BetSlipProvider>
  </React.StrictMode>,
);

// installable on Chrome/Android (and lets it open offline); dev skips it so the service worker never serves stale code
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => { navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch(() => {}); });
}
