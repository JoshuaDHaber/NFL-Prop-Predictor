import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { BetSlipProvider } from "./BetSlipContext";
import { LeagueContext } from "./LeagueContext";
import { getLeague, setLeague as storeLeague, type League } from "./league";
import "./styles.css";

const newClient = () => new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 30_000 } } });
// one cache per league: both sides use the same query keys (["meta"], ["picks", ...]) for different endpoints
const clients: Record<League, QueryClient> = { nfl: newClient(), nba: newClient() };

function Root() {
  const [league, setLeagueState] = useState<League>(getLeague);
  const setLeague = (l: League) => {
    storeLeague(l);
    // a game page belongs to one league: switching lands on the other league's slate
    if (window.location.hash) window.history.replaceState(null, "", window.location.pathname + window.location.search);
    window.scrollTo({ top: 0 });
    setLeagueState(l);
  };
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
