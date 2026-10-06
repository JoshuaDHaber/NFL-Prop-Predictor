"""SQLAlchemy models. SQLite locally; swap DATABASE_URL for Postgres in deployment."""
import json
import os
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


class Run(Base):
    """One execution of the projection pipeline."""
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    season: Mapped[int] = mapped_column(Integer)
    week: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    backtest: Mapped[dict] = mapped_column(JSON)
    variance: Mapped[dict] = mapped_column(JSON)
    excluded: Mapped[list] = mapped_column(JSON, default=list)
    projections: Mapped[list["Projection"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class Projection(Base):
    __tablename__ = "projections"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(80))
    pos: Mapped[str] = mapped_column(String(4))
    team: Mapped[str] = mapped_column(String(4))
    opp: Mapped[str] = mapped_column(String(4))
    home: Mapped[bool] = mapped_column(Boolean)
    kind: Mapped[str] = mapped_column(String(6))
    mu: Mapped[float] = mapped_column(Float)
    sd: Mapped[float] = mapped_column(Float)
    vol: Mapped[float] = mapped_column(Float)
    eff: Mapped[float] = mapped_column(Float)
    spread: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="")
    game_id: Mapped[str] = mapped_column(String(24), index=True)
    gameday: Mapped[str] = mapped_column(String(12))
    gametime: Mapped[str] = mapped_column(String(8), default="")
    last5: Mapped[list] = mapped_column(JSON)
    run: Mapped[Run] = relationship(back_populates="projections")

    __table_args__ = (Index("ix_proj_run_kind", "run_id", "kind"),)


class OddsLine(Base):
    """One sportsbook's over/under quote. Rows from one fetch share fetched_at."""
    __tablename__ = "odds_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    player: Mapped[str] = mapped_column(String(80))
    market: Mapped[str] = mapped_column(String(6), index=True)
    line: Mapped[float] = mapped_column(Float)
    over_odds: Mapped[float] = mapped_column(Float, nullable=True)
    under_odds: Mapped[float] = mapped_column(Float, nullable=True)
    book: Mapped[str] = mapped_column(String(40))
    over_link: Mapped[str] = mapped_column(String(500), nullable=True)
    under_link: Mapped[str] = mapped_column(String(500), nullable=True)
    event_link: Mapped[str] = mapped_column(String(500), nullable=True)
    game_id: Mapped[str] = mapped_column(String(24), nullable=True, index=True)  # which game the quote is for (null: older rows)


class AltLine(Base):
    """Alternate-line quotes, fetched on demand for one game at a time."""
    __tablename__ = "alt_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    game_id: Mapped[str] = mapped_column(String(24), index=True)
    player: Mapped[str] = mapped_column(String(80))
    market: Mapped[str] = mapped_column(String(6))
    line: Mapped[float] = mapped_column(Float)
    over_odds: Mapped[float] = mapped_column(Float, nullable=True)
    under_odds: Mapped[float] = mapped_column(Float, nullable=True)
    book: Mapped[str] = mapped_column(String(40))
    over_link: Mapped[str] = mapped_column(String(500), nullable=True)
    under_link: Mapped[str] = mapped_column(String(500), nullable=True)
    event_link: Mapped[str] = mapped_column(String(500), nullable=True)


def backfill_game_ids(eng) -> int:
    """Tag quotes stored before game_id existed with the game that was upcoming when they were fetched.

    Uses every projection run (player -> game, with the game's date): a quote fetched on a given day belongs to the
    player's first game on or after that day. So it is correct whichever run happens to be newest."""
    from sqlalchemy.orm import Session
    from .engine import odds
    with Session(eng) as s:
        legacy = s.query(OddsLine).filter(OddsLine.game_id.is_(None)).all()
        if not legacy:
            return 0
        games = {}  # normalized player name -> {gameday: game_id}
        for name, gameday, gid in s.query(Projection.name, Projection.gameday, Projection.game_id).distinct():
            games.setdefault(odds.norm(name), {})[gameday] = gid
        done = 0
        for r in legacy:
            fetched_day = r.fetched_at.date().isoformat()
            upcoming = sorted((day, gid) for day, gid in games.get(odds.norm(r.player), {}).items() if day >= fetched_day)
            if upcoming:
                r.game_id = upcoming[0][1]
                done += 1
        s.commit()
        return done


def ensure_columns(eng) -> bool:
    """create_all never alters existing tables; add the link columns to databases created before they existed.
    Returns True when game_id was just added (so the caller can tag the existing quotes)."""
    from sqlalchemy import inspect, text
    have = {c["name"] for c in inspect(eng).get_columns("odds_lines")}
    with eng.begin() as conn:
        for col in ("over_link", "under_link", "event_link"):
            if col not in have:
                conn.execute(text(f"ALTER TABLE odds_lines ADD COLUMN {col} VARCHAR(500)"))
        added = "game_id" not in have
        if added:
            conn.execute(text("ALTER TABLE odds_lines ADD COLUMN game_id VARCHAR(24)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_odds_lines_game_id ON odds_lines (game_id)"))
    return added


def make_engine(url=None):
    url = url or config.DATABASE_URL
    if url.startswith("sqlite:///") and not url.endswith(":memory:"):
        os.makedirs(os.path.dirname(url.replace("sqlite:///", "")), exist_ok=True)
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True, "pool_recycle": 300}
    if url.endswith(":memory:"):
        from sqlalchemy.pool import StaticPool
        kwargs["poolclass"] = StaticPool
    eng = create_engine(url, **kwargs)
    Base.metadata.create_all(eng)
    if ensure_columns(eng):
        backfill_game_ids(eng)
    return eng


engine = make_engine()
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def current_lines(session):
    """The newest quotes, as a DataFrame in the shape engine.picks expects.

    Newest per market AND game, so lines fetched for different games at different times (Thursday's game first,
    the Sunday slate later) all stay visible. Rows from before game_id existed are grouped per market."""
    import pandas as pd
    from sqlalchemy import select
    rows = session.scalars(select(OddsLine)).all()
    newest = {}
    for r in rows:
        k = (r.market, r.game_id)
        if k not in newest or r.fetched_at > newest[k]:
            newest[k] = r.fetched_at
    keep = [r for r in rows if r.fetched_at == newest[(r.market, r.game_id)]]
    return pd.DataFrame([dict(player=r.player, market=r.market, line=r.line, over_odds=r.over_odds,
                              under_odds=r.under_odds, book=r.book, over_link=r.over_link, under_link=r.under_link,
                              event_link=r.event_link, game_id=r.game_id) for r in keep],
                        columns=["player", "market", "line", "over_odds", "under_odds", "book", "over_link",
                                 "under_link", "event_link", "game_id"])
