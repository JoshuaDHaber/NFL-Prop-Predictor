import { useQueries, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api";
import { BASE, IS_STATIC } from "../env";
import { useBetSlip } from "../BetSlipContext";
import { KIND_SHORT, americanOdds, pct, signedPct } from "../format";
import { alternativesAtBook, bookCoverage, bookOptions, groupByBook, combinedLink, legLink, shareUrl, slipLinksText, linkStatus, openProgress, parlay, rebook, sameGame, slipText, toWin, type BookOption } from "../slip";

export default function BetSlip() {
  const { legs, remove, replace, clear, state, setState, open, setOpen } = useBetSlip();
  const [stakes, setStakes] = useState<Record<string, number>>({});
  const [copied, setCopied] = useState<"link" | "text" | "share" | null>(null);
  const [target, setTarget] = useState<string | null>(null);
  const [combinedMsg, setCombinedMsg] = useState<Record<string, string>>({});
  const [opened, setOpened] = useState<Record<string, string[]>>({});
  const [linking, setLinking] = useState<string | null>(null);
  const qc = useQueryClient();
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

  const copyText = async (text: string, tag: "link" | "text" | "share") => {
    try { await navigator.clipboard.writeText(text); setCopied(tag); setTimeout(() => setCopied(null), 1800); } catch { /* clipboard blocked */ }
  };
  const links = slipLinksText(legs, state);
  // phones can't reach "localhost": share this app's network address instead
  const lanUrl = qc.getQueryData<{ lan_url: string | null }>(["meta"])?.lan_url ?? null;
  const onLocalhost = ["localhost", "127.0.0.1"].includes(window.location.hostname);
  const shareBase = onLocalhost && !IS_STATIC ? lanUrl : (window.location.origin + BASE).replace(/\/$/, "");
  // All of a book's linked legs in a single tab (only for books whose multi-selection link format we know)
  const combineFor = (book: string) => {
    const links = openProgress(legs, book, state, []).direct.map((l) => legLink(l, state)).filter((u): u is string => !!u);
    return combinedLink(book, links);
  };
  const noteCombined = (book: string, count: number) =>
    setCombinedMsg({ ...combinedMsg, [book]: `Opened one tab with ${count} legs. Check that all ${count} are on the ${book} slip before placing; if any are missing, use "one at a time".` });
  // One new tab per click: browsers block extra pop-ups opened from a single click, so we step through the legs.
  const openNext = (book: string) => {
    let p = openProgress(legs, book, state, opened[book] ?? []);
    if (!p.remaining.length) { setOpened({ ...opened, [book]: [] }); p = openProgress(legs, book, state, []); }  // start over
    const leg = p.remaining[0];
    const url = leg && legLink(leg, state);
    if (!url) return;
    window.open(url, "_blank", "noopener");
    setOpened({ ...opened, [book]: [...(opened[book] ?? []).filter((id) => p.direct.some((l) => l.id === id)), leg.id] });
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

            {!IS_STATIC && missing.length > 0 && (
              <section className="suggest">
                <b>{missing.length} {missing.length === 1 ? "leg has" : "legs have"} no betslip link yet.</b>
                <p className="mut">Without one, "Add all" can't add {missing.length === 1 ? "it" : "them"} to the sportsbook slip.</p>
                <button className="primary" disabled={!hasKey || linking === "Fetching links…"} onClick={getLinks}>
                  {linking === "Fetching links…" ? "Fetching…" : `Get links (~${missingGames.length * 2} credits)`}
                </button>
                {!hasKey && <span className="mut"> {metaFlags?.can_write === false ? "Admin only" : "Needs ODDS_API_KEY"}</span>}
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
              const prog = openProgress(legs, book, state, opened[book] ?? []);
              const combine = combineFor(book);
              const p = parlay(ls, stake);
              return (
                <section className="slip-group" key={book}>
                  <div className="slip-book">
                    <b>{book}</b><span className="mut">{ls.length} {ls.length === 1 ? "selection" : "selections"}</span>
                    {combine && (
                      <a className="link strong" href={combine.url} target="_blank" rel="noopener noreferrer"
                        onClick={() => noteCombined(book, combine.count)}
                        title="Opens one tab with every linked leg added to the slip. A real link, so phones can hand it to the sportsbook app.">
                        Open all in one tab ↗
                      </a>
                    )}
                    {prog.direct.length > 0 && (
                      <button className="link" onClick={() => openNext(book)}>
                        {prog.remaining.length === 0 ? "All opened · start over" :
                          prog.direct.length === 1 ? "Add at book ↗" : combine ? `One at a time (${prog.done + 1} of ${prog.direct.length}) ↗` : `Add leg ${prog.done + 1} of ${prog.direct.length} ↗`}
                      </button>
                    )}
                  </div>
                  {combinedMsg[book] && <p className="mut open-msg">{combinedMsg[book]}</p>}
                  {prog.direct.length > 1 && (prog.done > 0 || !combine) && (
                    <p className="mut open-msg">
                      {prog.done === 0 ? "Your browser opens one new tab per click, so click once per leg."
                        : prog.remaining.length ? `Opened ${prog.done} of ${prog.direct.length}. Click again for the next leg.`
                        : `Opened all ${prog.direct.length}. Check your slip at ${book} before placing.`}
                    </p>
                  )}
                  {prog.skipped > 0 && (
                    <p className="warn open-msg">{prog.skipped} {prog.skipped === 1 ? "leg has" : "legs have"} no betslip link yet and will be skipped (see "Get links" above).</p>
                  )}
                  {ls.map((l) => {
                    const url = legLink(l, state);
                    const direct = linkStatus(l, state) === "direct";
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
                  {ls.length > 1 && sameGame(ls) && (
                    <p className="warn">Some legs are in the same game. Books usually price same-game parlays differently (correlation) or reject some combinations, so the payout above is only a guide.</p>
                  )}
                </section>
              );
            })}

            {legs.length > 0 && (
              <div className="slip-footer">
                <button className="primary" disabled={!links} onClick={() => copyText(links, "link")}
                  title={links ? "Copies the same link as \"Open all in one tab\" so you can open it on another device" : "No betslip links to copy yet"}>
                  {copied === "link" ? "Link copied" : "Copy slip link"}
                </button>
                <button className="primary outline" disabled={!shareBase}
                  title={shareBase ? "Copies a link that reopens this whole slip in this app on another device" : "This app's network address isn't available"}
                  onClick={() => shareBase && copyText(shareUrl(shareBase, legs, state), "share")}>
                  {copied === "share" ? "Phone link copied" : "Copy phone link"}
                </button>
                <button className="link" onClick={() => copyText(slipText(legs), "text")}>{copied === "text" ? "Copied" : "Copy as text"}</button>
                <button className="link" onClick={clear}>Clear all</button>
              </div>
            )}
            {legs.length > 0 && (
              <p className="mut slip-disclaimer">
                <b>Phone link:</b> {IS_STATIC ? <>reopens this slip on any device at this page. Tap each leg's button (or "Open all in one tab") to hand it to the sportsbook app. These links come from the snapshot and have likely expired.</> : shareBase ? <>opens this slip in the app at {shareBase}, so your phone must be on the same Wi-Fi and the app started with <code>./run.sh lan</code>. Then tap each leg's button (or "Open all in one tab") to hand it to the sportsbook app. Pasting a sportsbook link into a browser's address bar won't open the app; tapping a link on a page or in Messages does.</> : <>unavailable: the app couldn't find its network address.</>}
              </p>
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
