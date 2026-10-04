from typing import Literal, Optional

from pydantic import BaseModel

Kind = Literal["rush", "rec", "pass", "rr", "td"]


class RunInfo(BaseModel):
    id: int
    season: int
    week: int
    created_at: str
    excluded: list[str]


class CalibrationBin(BaseModel):
    predicted: float
    actual: float
    n: int


class BacktestStat(BaseModel):
    n: int
    mae_model: float   # mean absolute error in yards; for anytime TD, the Brier score
    mae_naive: float   # same measure for the naive baseline
    bias: float
    metric: str = "mae"  # "mae" or "brier"
    calibration: list[CalibrationBin] = []


class OddsInfo(BaseModel):
    fetched_at: str
    lines: int


class Game(BaseModel):
    game_id: str
    label: str
    gameday: str
    gametime: str


class JobStatus(BaseModel):
    state: Literal["idle", "running", "done", "error"]
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    log: list[str] = []
    error: Optional[str] = None


class Meta(BaseModel):
    run: Optional[RunInfo]
    backtest: dict[str, BacktestStat]
    odds: dict[str, OddsInfo]
    games: list[Game]
    has_odds_key: bool
    job: JobStatus
    lan_url: Optional[str] = None
    books: list[str] = []
    snapshot_at: Optional[str] = None  # set only in the static demo export
    can_write: bool = False  # this client may refresh data / fetch alt lines (local, or sent the admin token)
    can_run_projections: bool = True  # False on small hosts that only fetch odds


class ProjectionOut(BaseModel):
    player_id: str
    name: str
    pos: str
    team: str
    opp: str
    home: bool
    kind: Kind
    mu: float
    sd: float
    vol: float
    eff: float
    spread: float
    status: str
    game_id: str
    gameday: str
    gametime: str
    last5: list[float]


class PickOut(BaseModel):
    player_id: str
    name: str
    pos: str
    team: str
    opp: str
    home: bool
    kind: Kind
    mu: float
    sd: float
    status: str
    game_id: str
    gameday: str
    gametime: str
    side: Literal["Over", "Under"]
    line: float
    odds: int
    book: str
    p_model: float
    p_mkt: float
    prob: float
    ev: float
    kelly: float
    books: int
    edge_yds: float
    flagged: bool
    last5: list[float]


class GameLogEntry(BaseModel):
    label: str
    opp: str
    yards: float
    volume: float


class PlayerDetail(BaseModel):
    player_id: str
    name: str
    pos: str
    team: str
    headshot: Optional[str] = None
    projections: list[ProjectionOut]
    picks: list[PickOut]
    logs: dict[str, list[GameLogEntry]]


class RefreshRequest(BaseModel):
    odds: Literal["none", "missing", "all"] = "missing"


class QuoteSide(BaseModel):
    odds: int
    prob: float
    ev: float
    link: Optional[str] = None


class LadderRow(BaseModel):
    line: float
    book: str
    alt: bool
    event_link: Optional[str] = None
    over: Optional[QuoteSide] = None
    under: Optional[QuoteSide] = None


class LadderOut(BaseModel):
    kind: Kind
    mu: float
    sd: float
    game_id: str
    alt_fetched_at: Optional[str] = None
    quotes: list[LadderRow]


class AltFetchResult(BaseModel):
    kinds: list[str]
    alt_quotes: int
    linked: int
    credits_remaining: Optional[str] = None
