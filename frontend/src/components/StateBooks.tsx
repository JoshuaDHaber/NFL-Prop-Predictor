import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useBetSlip } from "../BetSlipContext";
import { detectState } from "../geoState";
import { allowedBooks } from "../legalBooks";
import { BookName } from "./BookBadge";
import { PinIcon } from "./icons";
import Menu from "./Menu";

/** The bettor's state as a small top-bar menu: which sportsbooks are legal there, and a switch to show every book. */
export default function StateBooks() {
  const { state, setState, allBooks, setAllBooks } = useBetSlip();
  const [locating, setLocating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const locate = async () => {
    setLocating(true);
    const r = await detectState();
    setLocating(false);
    if ("state" in r) { setState(r.state); setError(null); } else setError(r.error);
  };
  const qc = useQueryClient();
  // the books this league has odds from (already narrowed to the legal ones unless every book is showing), read from the
  // cache when the menu opens
  const legalHere = () => {
    const siteBooks = qc.getQueryData<{ books: string[] }>(["meta"])?.books;
    return (state ? allowedBooks(state, false) ?? [] : []).filter((b) => !siteBooks || siteBooks.includes(b));
  };
  return (
    <Menu label={<><PinIcon size={15} stroke={1.75} aria-hidden className="icon" />{state || "State"}</>} ariaLabel={state ? `Your state: ${state}` : "Set your state"}>
      {() => {
        const legal = legalHere();
        return (
          <div className="state-pop">
            {!state ? <p>Show only the sportsbooks that are legal where you are.</p>
              : legal.length ? <>
                <p>{allBooks ? `Showing every book. These are legal in ${state}:` : `Showing books legal in ${state}:`}</p>
                <div className="state-pop-books">{legal.map((b) => <BookName key={b} book={b} />)}</div>
              </> : <p>None of the sportsbooks on this site are legal in {state}.</p>}
            {state && (
              <label className="state-pop-toggle">
                <input type="checkbox" checked={allBooks} onChange={(e) => setAllBooks(e.target.checked)} /> Show every book
              </label>
            )}
            <button className="menu-item" onClick={locate} disabled={locating}>{locating ? "Finding your state…" : state ? "Update my location" : "Use my location"}</button>
            {error && <p className="err">{error}</p>}
          </div>
        );
      }}
    </Menu>
  );
}
