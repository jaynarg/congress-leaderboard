"""Settings for the data pipeline. Change CONGRESS to target a different Congress."""
import os
from pathlib import Path

CONGRESS = 119
CONGRESS_START = "2025-01-03"
CONGRESS_END = "2027-01-03"

# Types counted in leaderboard rankings (can become law), then resolutions
# (shown on member pages only). Ranked types are fetched first during backfill.
RANKED_TYPES = ["hr", "s", "hjres", "sjres"]
OTHER_TYPES = ["hres", "sres", "hconres", "sconres"]
ALL_TYPES = RANKED_TYPES + OTHER_TYPES

API_BASE = "https://api.congress.gov/v3"
API_KEY = os.environ.get("CONGRESS_API_KEY", "")

# Congress.gov allows 5,000 requests/hour; stay under it with some margin.
MAX_CALLS_PER_HOUR = int(os.environ.get("MAX_CALLS_PER_HOUR", "4500"))

# GitHub Actions jobs are killed at 6 hours. Stop fetching early so there is
# time to save progress and commit. Override with RUN_BUDGET_MINUTES.
RUN_BUDGET_MINUTES = int(os.environ.get("RUN_BUDGET_MINUTES", "320"))

LEGISLATORS_URLS = [
    "https://raw.githubusercontent.com/unitedstates/congress-legislators/gh-pages/legislators-current.json",
    "https://raw.githubusercontent.com/unitedstates/congress-legislators/gh-pages/legislators-historical.json",
]
PHOTO_URL = "https://unitedstates.github.io/images/congress/225x275/{bioguide}.jpg"

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
MEMBERS_FILE = DATA_DIR / "raw" / "members.json"
BILLS_DIR = DATA_DIR / "raw" / "bills"
STATE_FILE = DATA_DIR / "state" / "fetch_state.json"
LAST_RUN_FILE = DATA_DIR / "state" / "last_run.json"

CONGRESS_GOV_SLUGS = {
    "hr": "house-bill",
    "s": "senate-bill",
    "hjres": "house-joint-resolution",
    "sjres": "senate-joint-resolution",
    "hconres": "house-concurrent-resolution",
    "sconres": "senate-concurrent-resolution",
    "hres": "house-resolution",
    "sres": "senate-resolution",
}
