import os
import sys
import tempfile

# Must be set before the app is imported: an isolated in-memory DB and no real API key.
os.environ["NFLPROPS_NO_DOTENV"] = "1"
# TEST_DATABASE_URL runs the suite on a real Postgres instead (CI does both); that database is wiped first.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
os.environ["NFLPROPS_CACHE"] = tempfile.mkdtemp()
os.environ["NBA_CACHE"] = tempfile.mkdtemp()
os.environ.pop("ODDS_API_KEY", None)
os.environ.pop("ODDS_API_KEY_NBA", None)
os.environ["AUTO_SYNC"] = "0"  # the schedule never runs in tests unless a test starts it
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("TEST_DATABASE_URL"):
    from sqlalchemy import create_engine, text

    from app.config import normalize_db_url
    _eng = create_engine(normalize_db_url(os.environ["TEST_DATABASE_URL"]))
    with _eng.begin() as _c:
        _c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    _eng.dispose()


import pytest


@pytest.fixture(autouse=True)
def _no_standings_fetch(monkeypatch):
    """/meta reads teams' records from ESPN; tests never reach it (a test that wants records stubs _download)."""
    from app import standings

    def offline(url):
        raise standings.espn.requests.ConnectionError("offline in tests")
    monkeypatch.setattr(standings, "_download", offline)
    standings._records.cache_clear()
