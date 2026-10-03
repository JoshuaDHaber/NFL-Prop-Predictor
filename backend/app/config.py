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
FRONTEND_DIST = os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist")
