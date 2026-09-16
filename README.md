# Congress Legislative Leaderboard

Tracks legislative activity for every member of the current Congress: bills sponsored and
cosponsored, how far they advanced, and cross-party cosponsorship.

## Phase 1: data pipeline (this commit)

A GitHub Action runs nightly at 3 a.m. Pacific. It:

1. Loads every member who served in the 119th Congress from
   [unitedstates/congress-legislators](https://github.com/unitedstates/congress-legislators).
2. Pulls the full bill index for all 8 bill types from the Congress.gov API.
3. Fetches details (sponsor, cosponsors, CRS summaries, actions) for every bill that is new or
   has changed since the last run. Ranked types (HR, S, HJRES, SJRES) go first.
4. Commits updated JSON to `data/`.

The first run cannot finish the full backfill within GitHub's 6-hour limit. It saves progress
and the next run picks up where it left off; expect a few nights (or trigger extra runs
manually). After that, nightly runs take minutes.

## Data layout

- `data/raw/members.json`: members, terms, party/caucus history, photo URLs
- `data/raw/bills/<type>/<number>.json`: one file per bill
- `data/state/fetch_state.json`: change-detection checkpoint (don't edit)
- `data/state/last_run.json`: summary of the most recent run (`upToDate` shows backfill status)

## Setup

1. Get a free API key at https://api.congress.gov/sign-up/
2. In the repo: Settings → Secrets and variables → Actions → New repository secret.
   Name: `CONGRESS_API_KEY`
3. Actions tab → "Update Congress data" → Run workflow.

## Tuning

Environment variables (set in the workflow's `env:` block):

- `RUN_BUDGET_MINUTES` (default 320): stop fetching after this long so progress can be committed
- `MAX_CALLS_PER_HOUR` (default 4500): stays under Congress.gov's 5,000/hour limit
