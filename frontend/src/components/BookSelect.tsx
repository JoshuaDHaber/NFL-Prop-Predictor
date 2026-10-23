import BookBadge from "./BookBadge";
import { Caret } from "./Menu";

interface Props {
  books: string[];
  book: string;
  onChange: (book: string) => void;
  /** Offer "all" (best price at any book) under this label. */
  allLabel?: string;
  /** Inline in a page heading ("Parlays at FanDuel") rather than a pill among other controls. */
  inline?: boolean;
  ariaLabel?: string;
}

/** The site's sportsbook picker: the book's badge and name, with the native picker laid invisibly over it, so it's sized
 *  to the name and still the phone's own picker. */
export default function BookSelect({ books, book, onChange, allLabel, inline = false, ariaLabel = "Sportsbook" }: Props) {
  const all = book === "all";
  return (
    <span className={`book-pick${inline ? " inline" : ""}`}>
      {!all && <BookBadge book={book} size={inline ? 24 : 18} />}
      <span className="book-pick-name">{all ? allLabel : book}<Caret /></span>
      <select value={book} onChange={(e) => onChange(e.target.value)} aria-label={ariaLabel}>
        {allLabel && <option value="all">{allLabel}</option>}
        {books.map((b) => <option key={b} value={b}>{b}</option>)}
      </select>
    </span>
  );
}
