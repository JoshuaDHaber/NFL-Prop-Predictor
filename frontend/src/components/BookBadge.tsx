import type { CSSProperties } from "react";
import betmgm from "../assets/books/betmgm.png";
import betonline from "../assets/books/betonline.png";
import betrivers from "../assets/books/betrivers.png";
import bovada from "../assets/books/bovada.png";
import caesars from "../assets/books/caesars.png";
import draftkings from "../assets/books/draftkings.png";
import fanduel from "../assets/books/fanduel.png";

// Each sportsbook's app icon (bundled, from the book's site or Google's copy of its favicon), on its brand color for
// icons with transparent edges. Books without an icon get a monogram in brand colors (background, text).
const BOOKS: Record<string, { icon?: string; mono: string; bg: string; ink: string }> = {
  FanDuel: { icon: fanduel, mono: "FD", bg: "#1493ff", ink: "#fff" },
  DraftKings: { icon: draftkings, mono: "DK", bg: "#61b510", ink: "#fff" },
  BetMGM: { icon: betmgm, mono: "MGM", bg: "#c3a46b", ink: "#111" },
  BetRivers: { icon: betrivers, mono: "BR", bg: "#ffc72c", ink: "#1b3f8f" },
  Bovada: { icon: bovada, mono: "BV", bg: "#fff", ink: "#cc0000" },
  "BetOnline.ag": { icon: betonline, mono: "BOL", bg: "#1a1a1a", ink: "#ff4b4b" },
  Caesars: { icon: caesars, mono: "CZR", bg: "#173a2f", ink: "#d9b65f" },
  Fanatics: { mono: "F", bg: "#111", ink: "#fff" },
};

export const bookMonogram = (book: string) =>
  BOOKS[book]?.mono ?? book.replace(/\.\w+$/, "").split(/\s+|(?=[A-Z])/).filter(Boolean).map((w) => w[0]).join("").slice(0, 3).toUpperCase();

export default function BookBadge({ book, size = 22 }: { book: string; size?: number }) {
  const b = BOOKS[book];
  const text = bookMonogram(book);
  const style = { width: size, height: size, fontSize: size * (text.length > 2 ? 0.34 : 0.42), ...(b && { background: b.bg, color: b.ink }) } as CSSProperties;
  return (
    <span className="book-badge" style={style} aria-hidden="true">
      {b?.icon ? <img src={b.icon} alt="" width={size} height={size} /> : text}
    </span>
  );
}

/** A book's name with its badge in front, for anywhere the site names a sportsbook. */
export function BookName({ book, size = 16 }: { book: string; size?: number }) {
  return <span className="book-name"><BookBadge book={book} size={size} />{book}</span>;
}
