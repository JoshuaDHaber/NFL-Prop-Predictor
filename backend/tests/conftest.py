import os
import sys
import tempfile

# Must be set before the app is imported: an isolated in-memory DB and no real API key.
os.environ["NFLPROPS_NO_DOTENV"] = "1"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["NFLPROPS_CACHE"] = tempfile.mkdtemp()
os.environ.pop("ODDS_API_KEY", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
