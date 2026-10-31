import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=os.path.join(BASE_DIR, ".env")):
    """Load KEY=VALUE lines from backend/.env without overriding real environment variables."""
    if os.path.exists(path):
        for line in open(path):
            k, _, v = line.strip().partition("=")
            if k and not k.startswith("#") and v:
                os.environ.setdefault(k, v.strip("\"'"))


if not os.environ.get("NFLPROPS_NO_DOTENV"):  # tests must never pick up the real API key
    load_env()

def normalize_db_url(url: str) -> str:
    """Hosted Postgres gives postgres:// or postgresql:// URLs; SQLAlchemy needs the driver we install (psycopg 3)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = normalize_db_url(os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'data', 'app.db')}"))
ADMIN_TOKEN = lambda: os.environ.get("ADMIN_TOKEN")  # lets a remote client run refreshes and spend API credits
CORS_ORIGINS = lambda: [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
# the weekly model run needs ~400 MB; small hosts set this to 0 and run it elsewhere against the same database
PROJECTIONS_ON_SERVER = lambda: os.environ.get("PROJECTIONS_ON_SERVER", "1") != "0"
ODDS_API_KEY = lambda: os.environ.get("ODDS_API_KEY")  # read lazily so tests can set it
# the NBA side has its own Odds API key, so its daily syncs never eat into the NFL key's credits
ODDS_API_KEY_NBA = lambda: os.environ.get("ODDS_API_KEY_NBA")
# spares: a sync switches to these once the key above reaches the credit floor (app/odds_keys.py)
ODDS_API_KEY_NFL_SECONDARY = lambda: os.environ.get("ODDS_API_KEY_NFL_SECONDARY")
ODDS_API_KEY_NBA_SECONDARY = lambda: os.environ.get("ODDS_API_KEY_NBA_SECONDARY")


def odds_keys(league: str = "nfl") -> list[tuple[str, str]]:
    """[(env var, key)] for a league's Odds API keys that are set, the one to spend first first."""
    names = ("ODDS_API_KEY_NBA", "ODDS_API_KEY_NBA_SECONDARY") if league == "nba" else ("ODDS_API_KEY", "ODDS_API_KEY_NFL_SECONDARY")
    return [(n, k) for n in names if (k := globals()[n]())]


# ESPN responses for the NBA model (game logs, rosters, schedule); next to the database so they survive redeploys
NBA_CACHE = os.environ.get("NBA_CACHE") or os.path.join(BASE_DIR, "data", "nba_cache")
# Scheduled syncs (app/scheduler.py): on by default on Railway, off elsewhere so a laptop never spends credits by itself
AUTO_SYNC = lambda: os.environ.get("AUTO_SYNC", "1" if os.environ.get("RAILWAY_ENVIRONMENT_NAME") else "0") == "1"
# sync jobs run in a child process that frees their memory on exit (app/scheduler.py); tests run them in-process
SYNC_SUBPROCESS = lambda: os.environ.get("SYNC_SUBPROCESS", "1") != "0"
# odds fetches stop before a key drops under this many credits; a sync then switches to the spare key, and the admin page says which key to rotate
ODDS_CREDIT_FLOOR = lambda: int(os.environ.get("ODDS_CREDIT_FLOOR", "10"))
FRONTEND_DIST = os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist")
