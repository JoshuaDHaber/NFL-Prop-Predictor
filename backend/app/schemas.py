from typing import Literal, Optional

from pydantic import BaseModel

Kind = Literal["rush", "rec", "pass", "rr", "td", "recs", "ptd", "lng", "pts", "reb", "ast", "threes"]  # the last four: NBA


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
    mae_market: Optional[float] = None              # moneyline: Brier score of the closing moneyline...
    mae_model_market_games: Optional[float] = None  # ...and the model's, on the games that have one
    n_market: Optional[int] = None


class OddsInfo(BaseModel):
    fetched_at: str
    lines: int


class GameWeather(BaseModel):
    stadium: str = ""
    roof: str = "unknown"
    indoor: bool = False
    source: str = "none"              # forecast | indoor | none (no forecast available)
    temp: Optional[float] = None      # degrees F, average over the three hours from kickoff
    wind: Optional[float] = None      # mph, same window
    gust: Optional[float] = None
    wind_dir: Optional[float] = None  # degrees the wind blows FROM (0 = north), averaged over the window
    sky: Optional[str] = None         # e.g. "Partly cloudy", "Rain showers"
    precip_prob: Optional[float] = None  # %, highest in the window
    precip: Optional[float] = None    # inches; shown, not applied (no history to fit it on)
    snow: Optional[float] = None
    fetched_at: Optional[str] = None
    provider: Optional[str] = None    # Open-Meteo | National Weather Service
    factors: dict[str, float] = {}    # per market: multiplier applied to yardage projections


class Game(BaseModel):
    game_id: str
    label: str
    gameday: str
    gametime: str
    weather: Optional[GameWeather] = None


class JobStatus(BaseModel):
    state: Literal["idle", "running", "done", "error"]
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    log: list[str] = []
    error: Optional[str] = None
    stage: Optional[str] = None      # what it is doing now, e.g. "Running the model"
    step: int = 0                    # which step (1-based) of `steps`
    steps: int = 0
    detail: Optional[str] = None     # the latest sub-step message, e.g. "game 3 of 15"
    progress: Optional[float] = None # 0..1 within the odds step (None while the model runs)


class AutoSync(BaseModel):
    enabled: bool
    next_at: Optional[str] = None     # UTC, when the next scheduled sync runs
    next_label: Optional[str] = None


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
    calibration: Optional[dict] = None  # when/for which week the error tables were last fitted
    redistribution: Optional[dict] = None  # what teammate redistribution did in the backtest (see engine/redistribute.py)
    weather: Optional[dict] = None  # the fitted weather effect and what it did in the backtest (see engine/weather.py)
    can_write: bool = False  # this client may refresh data / fetch alt lines (local, or sent the admin token)
    can_run_projections: bool = True  # False on small hosts that only fetch odds
    auto_sync: Optional[AutoSync] = None


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
    wx: Optional[float] = None  # weather multiplier already in mu (1 or None: no effect)
    teammate_out: Optional[str] = ""  # same-position rotation receivers in their first game out
    thin: Optional[bool] = False      # thin history (a rookie, or back from IR): shown, never priced


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
    wx: Optional[float] = None
    flag: str = ""             # why it's flagged: "large gap" | "teammate out"
    teammate_out: str = ""     # same-position rotation receivers in their first game out (shown on Overs too)


class GradeLine(BaseModel):
    """Record and units (1 unit a pick at the logged price) for one slice of the graded board."""
    label: str
    n: int
    wins: int
    losses: int
    pushes: int
    voids: int                     # the player didn't play: books void these
    units: float
    roi: Optional[float] = None    # units per decided pick
    expected_wins: float           # what the model's win chances added up to


class MarketCheck(BaseModel):
    """Model projection vs the posted line: which landed closer to the result, per market."""
    kind: Kind
    n: int
    mae_model: float
    mae_line: float
    model_closer: float            # share of player-games where the projection was closer than the line


class GradeReport(BaseModel):
    season: Optional[int] = None
    graded: int
    pending: int                   # logged, waiting on the game or its stats
    weeks: list[int]
    board: list[GradeLine]
    by_market: list[GradeLine]
    by_ev: list[GradeLine]
    by_week: list[GradeLine]
    model_vs_line: list[MarketCheck]


class GameLogEntry(BaseModel):
    label: str
    opp: str
    yards: float
    volume: float


class PlayerHit(BaseModel):
    """A player search result: an active player (NFL: offensive skill positions), flagged with whether he is projected this week or slate."""
    player_id: str
    name: str
    pos: str
    team: str
    headshot: Optional[str] = None
    projected: bool


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
    odds: Literal["none", "missing", "thin", "today", "all"] = "missing"
    full: bool = False  # refit the model's calibration instead of reusing the saved one


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


class PlanGame(BaseModel):
    game_id: str
    label: str
    gameday: str
    need_main: list[str]
    need_alt: bool
    alt_kinds: list[str] = []     # which alternate markets (a game may lack only newly added ones)
    credits: int
    reason: str = "missing"       # missing | thin | today | all
    stored_quotes: int = 0


class SyncPlan(BaseModel):
    season: Optional[int] = None
    week: Optional[int] = None
    total_games: int
    games: list[PlanGame]
    credits: int
    will_run_projections: bool
    has_odds_key: bool
    will_recalibrate: bool = False  # True: the model run refits its calibration (slow); False: it reuses the saved one
    calibration: Optional[dict] = None

class MoneylineSide(BaseModel):
    team: str
    name: str
    home: bool
    p_model: float                 # the team-rating model's win chance
    p_mkt: Optional[float] = None  # no-vig consensus across books (None: no two-way prices yet)
    prob: float                    # the blend that prices EV (leans at least 80% on the market)
    books: int = 0
    odds: Optional[int] = None     # best price (at the chosen book, if one is chosen)
    book: Optional[str] = None
    ev: Optional[float] = None
    kelly: Optional[float] = None
    link: Optional[str] = None
    event_link: Optional[str] = None


class InjuredPlayer(BaseModel):
    player_id: str
    name: str
    pos: str
    team: str
    side: Literal["off", "def", "st"]
    status: str             # Out | Doubtful | Questionable | "" (no game status) | IR | PUP | NFI | Reserve
    injury: str
    practice: str           # DNP | Limited | Full | "" (not on the practice report)
    rest: bool              # a veteran's rest day, not an injury
    kind: Optional[str] = None  # a market the app projects for him (opens his player drawer)
    comment: str = ""           # ESPN: the latest news line, e.g. "won't play Monday against the Thunder"
    return_date: Optional[str] = None  # ESPN: estimated return, YYYY-MM-DD
    updated: Optional[str] = None      # ESPN: when the status was last updated (UTC ISO)


class InjuryReport(BaseModel):
    season: Optional[int] = None
    week: Optional[int] = None
    report_week: Optional[int] = None   # the week the report is from (earlier than week until this week's is out)
    fetched_at: Optional[str] = None
    news_fetched_at: Optional[str] = None   # NFL: when ESPN's feed (news lines, return dates) was last read
    teams: dict[str, list[InjuredPlayer]] = {}


class MoneylineGame(BaseModel):
    game_id: str
    label: str
    gameday: str
    gametime: str
    margin: float                  # the model's predicted home margin, points
    spread: Optional[float] = None # the market's (nflverse) home spread, points
    total: Optional[float] = None  # the market's points total (NBA, from ESPN)
    sides: list[MoneylineSide]     # away, home


class CreditStatus(BaseModel):
    remaining: Optional[int] = None   # credits left on the current ODDS_API_KEY
    floor: int                        # odds fetches stop before the balance drops under this
    low: bool = False                 # at or under the floor: time to rotate the key
    key_hint: Optional[str] = None    # last 4 characters, to tell keys apart
    checked_at: Optional[str] = None
    error: Optional[str] = None


class SyncRunOut(BaseModel):
    id: int
    slot: str
    label: str
    trigger: str                      # schedule | catch-up | manual
    scheduled_for: Optional[str] = None
    started_at: str
    finished_at: Optional[str] = None
    status: str                       # running | ok | partial | error | skipped
    odds_mode: str
    full: bool
    season: Optional[int] = None
    week: Optional[int] = None
    games_fetched: int = 0
    credits_before: Optional[int] = None
    credits_after: Optional[int] = None
    summary: str = ""
    error: Optional[str] = None


class SyncRunDetail(SyncRunOut):
    log: list[str] = []


class SlotOut(BaseModel):
    id: str
    label: str
    league: str = "nfl"
    when: str                         # "Wed 10:00 AM ET"
    odds_mode: str
    full: bool
    why: str
    next_at: str
    last_run: Optional[SyncRunOut] = None


class AdminState(BaseModel):
    auto_sync: AutoSync
    timezone: str
    credits: CreditStatus
    credits_nba: Optional[CreditStatus] = None   # the NBA's own key (ODDS_API_KEY_NBA)
    slots: list[SlotOut]
    runs: list[SyncRunOut]
    job: JobStatus
    can_run_projections: bool


class NbaRunInfo(BaseModel):
    id: int
    season: int                       # ESPN's season year: 2027 is the 2026-27 season
    slate: list[str]                  # the Eastern dates the run projects
    created_at: str
    excluded: list[str]


class NbaMeta(BaseModel):
    league: Literal["nba"] = "nba"
    run: Optional[NbaRunInfo]
    backtest: dict[str, BacktestStat]
    odds: dict[str, OddsInfo]
    games: list[Game]
    has_odds_key: bool
    books: list[str] = []
    auto_sync: Optional[AutoSync] = None
    can_write: bool = False
    supports_alt: bool = False        # no alternate-line fetches for the NBA yet
