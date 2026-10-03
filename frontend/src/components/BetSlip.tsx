import { useState } from "react";
import { useBetSlip } from "../BetSlipContext";
import { KIND_SHORT, americanOdds, pct, signedPct } from "../format";
import { groupByBook, isDirectLink, legLink, parlay, sameGame, slipText, toWin } from "../slip";

export default function BetSlip() {
  const { legs, remove, clear, state, setState, open, setOpen } = useBetSlip();
  const [stakes, setStakes] = useState<Record<string, number>>({});
  const [copied, setCopied] = useState(false);
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
                          <span className="mut"> {l.home ? "vs" : "@"} {l.opp} · {americanOdds(l.odds)}</span><br />
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
