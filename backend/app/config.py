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

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'data', 'app.db')}")
ODDS_API_KEY = lambda: os.environ.get("ODDS_API_KEY")  # read lazily so tests can set it
FRONTEND_DIST = os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist")
