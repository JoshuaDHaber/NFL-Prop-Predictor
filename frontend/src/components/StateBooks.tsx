import { useState } from "react";
import { useBetSlip } from "../BetSlipContext";
import { detectState } from "../geoState";
import { allowedBooks } from "../legalBooks";

/** The bettor's state and which sportsbooks the app shows for it: only the legal ones, unless they ask for all. */
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

  if (!state) {
    return (
      <div className="state-books">
        {locating ? "Finding your state…" : <button className="link" onClick={locate}>📍 Show books legal in my state</button>}
        {error && !locating && <div className="mut">{error}</div>}
      </div>
    );
  }
  const legal = allowedBooks(state, false) ?? [];
  return (
    <div className="state-books">
      <span>📍 <b>{state}</b> · {allBooks ? "all books" : legal.length ? "legal books only" : "no legal sportsbooks"}</span>
      {" · "}
      <button className="link" onClick={() => setAllBooks(!allBooks)}>{allBooks ? "Legal only" : "Show all"}</button>
      {!allBooks && legal.length > 0 && <div className="mut">{legal.join(", ")}</div>}
    </div>
  );
}
