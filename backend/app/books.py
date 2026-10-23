"""Which sportsbooks the site shows. The offshore books (licensed in no US state) can be hidden from the admin page:
their quotes still count toward the market consensus, they just never show up as a price to bet."""
from typing import Iterable, Optional

from .db import Setting
from .engine.picks import book_set

OFFSHORE = frozenset({"BetOnline.ag", "BetUS", "Bovada", "LowVig.ag", "MyBookie.ag"})
HIDE_OFFSHORE = "hide_offshore"


def hide_offshore(db) -> bool:
    row = db.get(Setting, HIDE_OFFSHORE)
    return bool(row and row.value)


def set_hide_offshore(db, on: bool):
    row = db.get(Setting, HIDE_OFFSHORE) or Setting(key=HIDE_OFFSHORE)
    row.value = bool(on)
    db.add(row)
    db.commit()


def shown(books: Iterable[str], hide: bool) -> list[str]:
    return sorted(b for b in books if not (hide and b in OFFSHORE))


def pricing_books(book: Optional[str], books: Iterable[str], hide: bool) -> Optional[str]:
    """The only_book filter for pricing: the asked-for book(s) (every book in `books` when none), minus the offshore ones
    when they're hidden. "none" when that leaves nothing, so nothing is priced."""
    if not hide:
        return book
    return ",".join(sorted((book_set(book) or set(books)) - OFFSHORE)) or "none"
