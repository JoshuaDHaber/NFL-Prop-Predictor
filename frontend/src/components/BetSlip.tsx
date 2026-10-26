import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useBetSlip } from "../BetSlipContext";
import { detectState } from "../geoState";
import BookBadge from "./BookBadge";
import Sheet from "./Sheet";
import SidePill from "./SidePill";
import { isYesNo, KIND_SHORT, americanOdds, pct, playLabel, signedPct, timeAgo } from "../format";
import { alternativesAtBook, bookCoverage, bookOptions, groupByBook, combinedLink, legLink, slipLinksText, linkStatus, openProgress, parlay, rebook, sameGame, slipHitChance, toAmerican, toWin, type BookOption } from "../slip";

// once per page load: the stored state covers later opens, and "Try again" re-runs it
let locatedOnce = false;

export default function BetSlip() {
  const { legs, remove, replace, clear, state, setState, open, setOpen, staleSince } = useBetSlip();
  // old odds: the bettor ticks that they'll check prices before a Place button hands the slip to a book (once per odds fetch)
  const [checkedStale, setCheckedStale] = useState<string | null>(null);
  const gated = !!staleSince && checkedStale !== staleSince;
  const close = () => setOpen(false);
  const [stakes, setStakes] = useState<Record<string, number>>({});
  const [copied, setCopied] = useState<"link" | null>(null);
  const [target, setTarget] = useState<string | null>(null);
  const [placeMsg, setPlaceMsg] = useState<string | null>(null);
  const [opened, setOpened] = useState<Record<string, string[]>>({});
  const [linking, setLinking] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState<string | null>(null);
  const qc = useQueryClient();
  // some books' links need the bettor's state: find it from the device's location the first time the slip opens
  const locate = async () => {
    setLocating(true);
    const r = await detectState();
    setLocating(false);
    if ("state" in r) { setState(r.state); setLocError(null); } else setLocError(r.error);
  };
  const needsState = legs.some((l) => /\{state\}/.test(`${l.link ?? ""} ${l.eventLink ?? ""}`));
  useEffect(() => {
    if (open && needsState && !locatedOnce) { locatedOnce = true; locate(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, needsState]);
  const metaFlags = qc.getQueryData<{ has_odds_key: boolean; can_write: boolean }>(["meta"]);
  const hasKey = !!metaFlags?.has_odds_key && !!metaFlags?.can_write;
  // line shopping data: every book's quote for each leg's exact line (shares the drawer's query cache)
  const keys = [...new Map(legs.map((l) => [`${l.playerId}|${l.kind}`, l])).values()];
  const ladders = useQueries({
    queries: keys.map((l) => ({ queryKey: ["ladder", l.playerId, l.kind, 0], queryFn: () => api.lines(l.playerId, l.kind, 0), enabled: open })),
  });
  const ladderFor = (l: { playerId: string; kind: string }) => ladders[keys.findIndex((k) => k.playerId === l.playerId && k.kind === l.kind)]?.data;
  const options: Record<string, BookOption[]> = Object.fromEntries(legs.map((l) => [l.id, bookOptions(ladderFor(l), l)]));
  const coverage = bookCoverage(options);
  const moveAll = (book: string) => {
    setTarget(book);
    legs.forEach((l) => {
      const o = options[l.id]?.find((x) => x.book === book);
      if (o && l.book !== book) replace(l.id, rebook(l, o));
    });
  };
  // legs the chosen book can't take as-is, each with the nearest lines that book does offer
  const stranded = target ? legs.filter((l) => l.book !== target) : [];
  const stakeFor = (book: string) => stakes[book] ?? 10;
  // same-game legs: positions (slip legs don't carry them) and the correlations, only once a book's legs share a game
  const needCorr = open && legs.some((l, i) => legs.some((m, j) => j > i && m.gameId === l.gameId && m.book === l.book));
  // both leagues' (a slip can hold either); their market names differ, so one table holds both without clashing
  const nflProj = useQuery({ queryKey: ["nfl-projections"], queryFn: api.nflProjections, enabled: needCorr, staleTime: 10 * 60_000 });
  const nbaProj = useQuery({ queryKey: ["nba-projections"], queryFn: api.nbaProjections, enabled: needCorr, staleTime: 10 * 60_000 });
  const corrQuery = useQuery({ queryKey: ["correlations"], queryFn: api.correlations, enabled: needCorr, staleTime: 10 * 60_000 });
  const nbaCorrQuery = useQuery({ queryKey: ["nba-correlations"], queryFn: api.nbaCorrelations, enabled: needCorr, staleTime: 10 * 60_000 });
  const positions = useMemo(() => Object.fromEntries([...(nflProj.data ?? []), ...(nbaProj.data ?? [])].map((p) => [p.player_id, p.pos])),
    [nflProj.data, nbaProj.data]);
  const corr = useMemo(() => ({ ...corrQuery.data?.pairs, ...nbaCorrQuery.data?.pairs }), [corrQuery.data, nbaCorrQuery.data]);

  const copyText = async (text: string, tag: "link") => {
    try { await navigator.clipboard.writeText(text); setCopied(tag); setTimeout(() => setCopied(null), 1800); } catch { /* clipboard blocked */ }
  };
  const links = slipLinksText(legs, state);
  // All of a book's linked legs in a single tab (only for books whose multi-selection link format we know)
  const combineFor = (book: string) => {
    const direct = openProgress(legs, book, state, []).direct.flatMap((l) => {
      const url = legLink(l, state);
      return url ? [{ ...l, url }] : [];
    });
    return combinedLink(book, direct);
  };
  // One new tab per click: browsers block extra pop-ups opened from a single click, so we step through the legs.
  const openNext = (book: string) => {
    let p = openProgress(legs, book, state, opened[book] ?? []);
    if (!p.remaining.length) p = openProgress(legs, book, state, []);  // start over
    const leg = p.remaining[0];
    const url = leg && legLink(leg, state);
    if (!url) return;
    window.open(url, "_blank", "noopener");
    const done = [...(p.done ? opened[book] ?? [] : []).filter((id) => p.direct.some((l) => l.id === id)), leg.id];
    setOpened({ ...opened, [book]: done });
    setPlaceMsg(done.length < p.direct.length ? `Added ${done.length} of ${p.direct.length} at ${book}. Click again for the next leg.`
      : `All ${p.direct.length} legs opened at ${book}. Check the slip there before placing.`);
  };
  const groups = groupByBook(legs);
  // "Place bet": every linked leg in one tab where the book's multi-selection link is known, otherwise one leg per click
  const placeButton = (book: string) => {
    const prog = openProgress(legs, book, state, opened[book] ?? []);
    if (!prog.direct.length) return null;
    const label = <><BookBadge book={book} size={20} />{groups.length > 1 ? `Place at ${book}` : "Place bet"}</>;
    if (gated) return <button key={book} className="primary" disabled title="Tick the box above first: these prices are old">{label} ↗</button>;
    const combine = combineFor(book);
    // a real link (not window.open), so phones hand it to the sportsbook app
    if (combine) return (
      <a key={book} className="primary" href={combine.url} target="_blank" rel="noopener noreferrer"
        onClick={() => setPlaceMsg(`Opened ${book} with ${combine.count} ${combine.count === 1 ? "leg" : "legs"}. If any are missing from the slip there, add them with each leg's button.`)}>
        {label} ↗
      </a>
    );
    const step = prog.direct.length > 1 && prog.remaining.length ? ` · leg ${prog.done + 1} of ${prog.direct.length}` : "";
    return <button key={book} className="primary" onClick={() => openNext(book)}>{label}{step} ↗</button>;
  };

  // legs with no betslip link at all (links only come with a game's alternate-lines fetch); one fetch per game covers them
  const missing = legs.filter((l) => linkStatus(l, state) === "missing");
  const missingGames = [...new Map(missing.map((l) => [l.gameId, l])).values()];
  const getLinks = async () => {
    const credits = missingGames.length * 2;
    if (!window.confirm(`Fetch betslip links for ${missingGames.length} ${missingGames.length === 1 ? "game" : "games"}?\n\nUses about ${credits}+ Odds API credits.`)) return;
    setLinking("Fetching links…");
    try {
      for (const l of missingGames) await api.fetchAlt(l.playerId);
      await qc.invalidateQueries({ queryKey: ["ladder"] });
      setLinking(null);
    } catch (e) { setLinking(`Couldn't fetch links: ${(e as Error).message}`); }
  };
  // once fresh quotes arrive, attach their links to legs that had none (same book, line and side)
  useEffect(() => {
    legs.forEach((l) => {
      if (l.link) return;
      const o = bookOptions(ladderFor(l), l).find((x) => x.book === l.book);
      if (o?.link) replace(l.id, rebook(l, o));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ladders.map((q) => q.dataUpdatedAt).join(",")]);
  return (
    <>
      <button className="slip-fab" onClick={() => setOpen(true)} aria-label={`Open betslip, ${legs.length} selections`}>
        Betslip <span className="count">{legs.length}</span>
      </button>
      {open && (
        <Sheet label="Betslip" overlayClass="slip-overlay" onClose={close}>
            <h2>Betslip</h2>
            {!legs.length && <p className="mut">Nothing here yet. Open a player and tap + on a line to add it.</p>}

            {needsState && (
              <p className="mut slip-where">
                {locating ? "Finding your state…" : state ? <>Links set for <b>{state}</b>{locError && " (last known)"}</> : null}
                {locError && !locating && <>{state ? " · " : ""}{locError} <button className="link" onClick={locate}>Try again</button></>}
              </p>
            )}

            {legs.length > 1 && coverage.length > 0 && (
              <label className="statebox">Put every leg at one book
                <select value="" onChange={(e) => e.target.value && moveAll(e.target.value)} aria-label="Move all legs to a book">
                  <option value="">Choose a book…</option>
                  {coverage.map((c) => (
                    <option key={c.book} value={c.book}>{c.book} · {c.count} of {legs.length} legs available</option>
                  ))}
                </select>
              </label>
            )}

            {missing.length > 0 && (
              <section className="suggest">
                <p><b>{missing.length} {missing.length === 1 ? "leg has" : "legs have"} no betslip link yet.</b></p>
                {hasKey ? (
                  <button className="primary" disabled={linking === "Fetching links…"} onClick={getLinks}>
                    {linking === "Fetching links…" ? "Fetching…" : `Get links (~${missingGames.length * 2} credits)`}
                  </button>
                ) : <p className="mut">The next scheduled odds sync usually adds them.</p>}
                {linking && linking !== "Fetching links…" && <p className="err">{linking}</p>}
              </section>
            )}

            {target && stranded.length > 0 && (
              <section className="suggest" aria-live="polite">
                <div className="suggest-head">
                  <b>{target} can't take {stranded.length === legs.length ? "these legs" : `${stranded.length} of ${legs.length} legs`} as they are.</b>
                  <button className="link" onClick={() => setTarget(null)}>Dismiss</button>
                </div>
                <p className="mut">Nearest lines {target} offers for each, so everything can go on one slip:</p>
                {stranded.map((l) => {
                  const alts = alternativesAtBook(ladderFor(l), l, target);
                  return (
                    <div className="suggest-leg" key={l.id}>
                      <div><b>{l.name}</b> <SidePill kind={l.kind} side={l.side} line={l.line} /> {!isYesNo(l.kind) && <span className="mut">{KIND_SHORT[l.kind]}</span>}</div>
                      {alts.length ? (
                        <div className="chips">
                          {alts.map((o) => (
                            <button key={o.line} className="chip-btn" onClick={() => replace(l.id, rebook(l, o))}
                              title={`Swap to ${playLabel(l.kind, l.side, o.line)} at ${target}`}>
                              {playLabel(l.kind, l.side, o.line)} <b>{americanOdds(o.odds)}</b>
                              <span className={o.ev > 0 ? "pos" : "mut"}> {signedPct(o.ev)}</span>
                            </button>
                          ))}
                        </div>
                      ) : (
                        <p className="mut">{target} has no {l.side.toLowerCase()} quotes for this player yet. Open the player and load alternate lines to see more.</p>
                      )}
                    </div>
                  );
                })}
              </section>
            )}

            {groups.map(([book, ls]) => {
              const stake = stakeFor(book);
              const prog = openProgress(legs, book, state, []);
              const p = parlay(ls, stake);
              return (
                <section className="slip-group" key={book}>
                  <div className="slip-book">
                    <BookBadge book={book} size={28} /><b>{book}</b><span className="mut">{ls.length} {ls.length === 1 ? "selection" : "selections"}</span>
                  </div>
                  {prog.skipped > 0 && (
                    <p className="warn open-msg">{prog.skipped} {prog.skipped === 1 ? "leg" : "legs"} can't be added: {ls.some((l) => linkStatus(l, state) === "needs-state")
                      ? "needs your state (allow location above)." : "no betslip link yet."}</p>
                  )}
                  {ls.map((l) => {
                    const url = legLink(l, state);
                    const direct = linkStatus(l, state) === "direct";
                    return (
                      <div className="slip-leg" key={l.id}>
                        <div>
                          <b>{l.name}</b> <span className="mut">{l.team} {l.home ? "vs" : "@"} {l.opp}</span><br />
                          <SidePill kind={l.kind} side={l.side} line={l.line} /> {!isYesNo(l.kind) && KIND_SHORT[l.kind]}
                          {l.alt && <span className="alt">alt</span>}<br />
                          <label className="bookpick">
                            <BookBadge book={l.book} size={20} />
                            <select value={l.book} aria-label={`Book for ${l.name} ${playLabel(l.kind, l.side, l.line)}`}
                              onChange={(e) => { const o = options[l.id]?.find((x) => x.book === e.target.value); if (o) replace(l.id, rebook(l, o)); }}>
                              {!options[l.id]?.some((o) => o.book === l.book) && <option value={l.book}>{l.book} {americanOdds(l.odds)}</option>}
                              {(options[l.id] ?? []).map((o) => (
                                <option key={o.book} value={o.book}>{o.book} {americanOdds(o.odds)}</option>
                              ))}
                            </select>
                          </label><br />
                          <span className="mut">{pct(l.prob, 0)} model · <span className={l.ev > 0 ? "pos" : ""}>{signedPct(l.ev)} EV</span> · to win ${toWin(l.odds, stake).toFixed(2)}</span>
                        </div>
                        <div className="slip-actions">
                          {/* a book's only leg goes through "Place bet" below */}
                          {url && !(ls.length === 1 && direct) && gated && <button className="btn" disabled title="Tick the box below first: these prices are old">{direct ? "Add at book ↗" : "Open book ↗"}</button>}
                          {url && !(ls.length === 1 && direct) && !gated && <a href={url} target="_blank" rel="noopener noreferrer" className="btn"
                            title={direct ? "Adds this selection to your betslip at the sportsbook" : "Opens the sportsbook's page (no betslip link for this selection yet)"}>
                            {direct ? "Add at book ↗" : "Open book ↗"}
                          </a>}
                          <button className="link" onClick={() => remove(l.id)}>Remove</button>
                        </div>
                      </div>
                    );
                  })}
                  <div className="slip-total">
                    <label>Stake $
                      <input type="number" min={0} step={1} value={stake}
                        onChange={(e) => setStakes({ ...stakes, [book]: Math.max(0, Number(e.target.value)) })} />
                    </label>
                    {ls.length > 1 ? (
                      <span>{ls.length}-leg parlay <b>{americanOdds(p.american)}</b> → pays <b>${p.payout.toFixed(2)}</b> (profit ${p.profit.toFixed(2)})</span>
                    ) : <span className="mut">Single bet</span>}
                  </div>
                  {ls.length > 1 && (() => {
                    const sg = sameGame(ls);
                    const hit = slipHitChance(ls, positions, sg ? corr : undefined);
                    const ev = hit * p.decimal - 1;
                    return (
                      <p className="mut slip-chance">
                        Model hit chance <b>{pct(hit, hit < 0.1 ? 1 : 0)}</b>
                        {sg ? <> · fair odds <b>{americanOdds(toAmerican(1 / Math.max(hit, 1e-6)))}</b></>
                          : <> · <span className={ev > 0 ? "pos" : ""}>{signedPct(ev)} EV</span></>}
                      </p>
                    );
                  })()}
                  {ls.length > 1 && sameGame(ls) && (
                    <p className="warn">Same-game legs: books price these their own way, so the payout is a guide. Take it if the book's price beats the fair odds.</p>
                  )}
                </section>
              );
            })}

            {legs.length > 0 && staleSince && (
              <label className="stale-ack">
                <input type="checkbox" checked={!gated} onChange={(e) => setCheckedStale(e.target.checked ? staleSince : null)} />
                <span><b>These prices are {timeAgo(staleSince).replace(" ago", "")} old</b> and have probably moved. I'll check each one at the book before betting.</span>
              </label>
            )}
            {legs.length > 0 && (
              <div className="slip-footer">
                {groups.map(([book]) => placeButton(book))}
                <button className="primary outline" disabled={!links} onClick={() => copyText(links, "link")}
                  title={links ? "Copies the sportsbook link so you can open the slip on another device" : "No betslip links to copy yet"}>
                  {copied === "link" ? "Link copied" : "Copy slip link"}
                </button>
                <button className="primary outline" onClick={clear}>Clear all</button>
              </div>
            )}
            {placeMsg && <p className="mut slip-place-msg" aria-live="polite">{placeMsg}</p>}
            <p className="mut slip-disclaimer">
              This app doesn't place bets: you sign in and confirm at the sportsbook. Check the line and price first.
            </p>
        </Sheet>
      )}
    </>
  );
}
