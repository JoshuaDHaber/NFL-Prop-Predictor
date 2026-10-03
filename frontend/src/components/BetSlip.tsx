import { useQueries } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { useBetSlip } from "../BetSlipContext";
import { KIND_SHORT, americanOdds, pct, signedPct } from "../format";
import { alternativesAtBook, bookCoverage, bookOptions, groupByBook, isDirectLink, legLink, parlay, rebook, sameGame, slipText, toWin, type BookOption } from "../slip";

export default function BetSlip() {
  const { legs, remove, replace, clear, state, setState, open, setOpen } = useBetSlip();
  const [stakes, setStakes] = useState<Record<string, number>>({});
  const [copied, setCopied] = useState(false);
  const [target, setTarget] = useState<string | null>(null);
  // line shopping data: every book's quote for each leg's exact line (shares the drawer's query cache)
  const keys = [...new Map(legs.map((l) => [`${l.playerId}|${l.kind}`, l])).values()];
  const ladders = useQueries({
    queries: keys.map((l) => ({ queryKey: ["ladder", l.playerId, l.kind], queryFn: () => api.lines(l.playerId, l.kind), enabled: open })),
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

  const copy = async () => {
    try { await navigator.clipboard.writeText(slipText(legs)); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  };
  const openAll = (book: string) => {
    legs.filter((l) => l.book === book).forEach((l) => { const u = legLink(l, state); if (u) window.open(u, "_blank", "noopener"); });
  };

  return (
    <>
      <button className="slip-fab" onClick={() => setOpen(true)} aria-label={`Open betslip, ${legs.length} selections`}>
        Betslip <span className="count">{legs.length}</span>
      </button>
      {open && (
        <div className="overlay slip-overlay" onClick={() => setOpen(false)}>
          <aside className="drawer" role="dialog" aria-label="Betslip" onClick={(e) => e.stopPropagation()}>
            <button className="close" onClick={() => setOpen(false)} aria-label="Close">×</button>
            <h2>Betslip</h2>
            {!legs.length && <p className="mut">Nothing here yet. Open a player and tap + on a line to add it.</p>}

            {legs.length > 0 && (
              <label className="statebox">Your state <small className="mut">(some books need it for links)</small>
                <input value={state} maxLength={2} placeholder="e.g. NJ" onChange={(e) => setState(e.target.value.toUpperCase())} />
              </label>
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
                      <div><b>{l.name}</b> <span className={l.side === "Over" ? "over" : "under"}>{l.side} {l.line}</span> <span className="mut">{KIND_SHORT[l.kind]}</span></div>
                      {alts.length ? (
                        <div className="chips">
                          {alts.map((o) => (
                            <button key={o.line} className="chip-btn" onClick={() => replace(l.id, rebook(l, o))}
                              title={`Swap to ${l.side} ${o.line} at ${target}`}>
                              {l.side} {o.line} <b>{americanOdds(o.odds)}</b>
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

            {groupByBook(legs).map(([book, ls]) => {
              const stake = stakeFor(book);
              const p = parlay(ls, stake);
              return (
                <section className="slip-group" key={book}>
                  <div className="slip-book">
                    <b>{book}</b><span className="mut">{ls.length} {ls.length === 1 ? "selection" : "selections"}</span>
                    <button className="link" onClick={() => openAll(book)}>Open all ↗</button>
                  </div>
                  {ls.map((l) => {
                    const url = legLink(l, state);
                    return (
                      <div className="slip-leg" key={l.id}>
                        <div>
                          <b>{l.name}</b> <span className="mut">{l.team}</span><br />
                          <span className={l.side === "Over" ? "over" : "under"}>{l.side} {l.line}</span> {KIND_SHORT[l.kind]}
                          {l.alt && <span className="alt">alt</span>}
                          <span className="mut"> {l.home ? "vs" : "@"} {l.opp}</span><br />
                          <label className="bookpick">
                            <span className="mut">Book</span>
                            <select value={l.book} aria-label={`Book for ${l.name} ${l.side} ${l.line}`}
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
                          {url && <a href={url} target="_blank" rel="noopener noreferrer" className="btn"
                            title={isDirectLink(l, state) ? "Adds this selection to your betslip at the sportsbook" : "Opens the sportsbook (no direct link available)"}>
                            {isDirectLink(l, state) ? "Add at book ↗" : "Open book ↗"}
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
                  {ls.length > 1 && sameGame(ls) && (
                    <p className="warn">Some legs are in the same game. Books usually price same-game parlays differently (correlation) or reject some combinations, so the payout above is only a guide.</p>
                  )}
                </section>
              );
            })}

            {legs.length > 0 && (
              <div className="slip-footer">
                <button className="primary" onClick={copy}>{copied ? "Copied" : "Copy slip"}</button>
                <button className="link" onClick={clear}>Clear all</button>
              </div>
            )}
            <p className="mut slip-disclaimer">
              This app doesn't place bets. "Add at book" opens the sportsbook with the selection added to its betslip
              when the book supports that; you sign in and confirm the bet there. Check the line and price before you
              place it. Odds move, and not every book accepts every combination.
            </p>
          </aside>
        </div>
      )}
    </>
  );
}
