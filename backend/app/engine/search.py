"""Player search shared by the NFL and NBA routes."""


def rank_hits(hits: list[dict], q: str, limit: int) -> list[dict]:
    """Hits whose name contains q (case- and period-insensitive): a name or a word in it starting with q first,
    projected players before the rest, then alphabetical."""
    q = q.strip().lower().replace(".", "")
    if not q:
        return []
    norm = lambda name: name.lower().replace(".", "")  # noqa: E731
    match = [h for h in hits if q in norm(h["name"])]
    rank = lambda h: (not any(w.startswith(q) for w in [norm(h["name"]), *norm(h["name"]).split()]),  # noqa: E731
                      not h["projected"], h["name"])
    return sorted(match, key=rank)[:limit]
