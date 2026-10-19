import { useQueries, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, type Filters } from "./api";
import { getLeague } from "./league";
import { buildBalancedLadders, buildLadderParlays, buildTdParlays, defaultBook, filterGames, ladderProps, ladderTargets, parlaysByBook } from "./parlays";

// Parlays rank by win probability, not EV, so they price every play (any EV) at the default market weight
export const PARLAY_FILTERS: Filters = { kind: "all", side: "all", game: "all", book: "all", q: "", minEv: -1, marketWeight: 0.35, flagged: false };

/**
 * Every parlay tile for the chosen games (none = every game) at one sportsbook: likely plays, touchdowns, ladders and single alternate props.
 * The per-book picks and line ladders are fetched for the whole slate and shared through the query cache, so the Parlays tab and a game page reuse them.
 */
export function useParlayBoard(books: string[], chosenGames: string[], enabled: boolean, preferredBook?: string) {
  // one pricing per sportsbook, so every parlay's legs sit at a single book
  const parlayQueries = useQueries({
    queries: books.map((book) => ({ queryKey: ["parlay-picks", book], queryFn: () => api.picks({ ...PARLAY_FILTERS, book }, 1000), enabled })),
  });
  // anytime-TD picks per book (the plain picks above leave TDs out); the NBA has no touchdown market
  const hasTd = getLeague() !== "nba";
  const tdQueries = useQueries({
    queries: books.map((book) => ({ queryKey: ["parlay-td", book], queryFn: () => api.picks({ ...PARLAY_FILTERS, kind: "td", book }, 1000), enabled: enabled && hasTd })),
  });
  // same-game correlations from the latest run (NFL only; without them, legs are priced as independent)
  const corrQuery = useQuery({ queryKey: ["correlations"], queryFn: api.correlations, enabled: enabled && hasTd, staleTime: 10 * 60_000 });
  const corr = hasTd ? corrQuery.data?.pairs : undefined;
  const loading = parlayQueries.some((q) => q.isLoading);
  const [book, setBook] = useState<string | null>(null);
  const parlayStamp = parlayQueries.map((q) => q.dataUpdatedAt).join();
  const allPicksByBook = useMemo(() => Object.fromEntries(books.map((b, i) => [b, parlayQueries[i]?.data ?? []])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [books.join(), parlayStamp]);
  const gamePicks = useMemo(() => filterGames(allPicksByBook, chosenGames), [allPicksByBook, chosenGames]);
  const byBook = useMemo(() => parlaysByBook(gamePicks, corr), [gamePicks, corr]);
  // a page-wide sportsbook choice wins over the tab's own picker
  const chosenBook = preferredBook && books.includes(preferredBook) ? preferredBook : book;
  const activeBook = chosenBook && books.includes(chosenBook) ? chosenBook : defaultBook(byBook, gamePicks);
  // ladder parlays need each likely player's line ladder (alternate lines); shares the drawer's and slip's query cache
  const targets = useMemo(() => ladderTargets(activeBook ? gamePicks[activeBook] ?? [] : [], Math.min(24, Math.max(12, chosenGames.length * 8))), [activeBook, gamePicks, chosenGames]);
  const ladderQueries = useQueries({
    queries: targets.map((t) => ({ queryKey: ["ladder", t.player_id, t.kind, 0], queryFn: () => api.lines(t.player_id, t.kind, 0), enabled })),
  });
  const ladderStamp = ladderQueries.map((q) => q.dataUpdatedAt).join();
  const ladderEntries = useMemo(() => targets.map((base, i) => ({ base, ladder: ladderQueries[i]?.data })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [targets, ladderStamp]);
  const ladderParlays = useMemo(() => activeBook ? buildLadderParlays(ladderEntries, activeBook, corr) : [], [activeBook, ladderEntries, corr]);
  // with games chosen, one more ladder per game that uses both teams
  const balancedLadders = useMemo(() => activeBook ? buildBalancedLadders(ladderEntries, activeBook, chosenGames.slice(0, 4), ladderParlays, corr) : [],
    [activeBook, ladderEntries, chosenGames, ladderParlays, corr]);
  const tdStamp = tdQueries.map((q) => q.dataUpdatedAt).join();
  const tdParlays = useMemo(() => {
    const i = books.indexOf(activeBook ?? "");
    return activeBook && i >= 0 ? buildTdParlays(tdQueries[i]?.data ?? [], activeBook, chosenGames, corr) : [];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeBook, books, chosenGames, tdStamp, corr]);
  const altProps = useMemo(() => activeBook ? ladderProps(ladderEntries, activeBook) : [], [activeBook, ladderEntries]);
  const ladders = useMemo(() => [...ladderParlays, ...balancedLadders], [ladderParlays, balancedLadders]);

  return {
    loading, book: activeBook, setBook, parlays: (activeBook && byBook[activeBook]) || [], tdParlays, ladders, altProps,
    laddersLoading: ladderQueries.some((q) => q.isLoading),
  };
}
