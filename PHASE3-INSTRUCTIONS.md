# Phase 3: stats computation

## Files in this bundle

- `pipeline/stages.py` (new): works out how far a bill advanced
- `pipeline/stats.py` (new): builds the leaderboard and member-page JSON
- `.github/workflows/update-data.yml` (replaces the existing one): adds a "Build stats" step

## Install

Upload all three, keeping the folder structure, then run the workflow once from the
Actions tab. The fetch step will be quick now that the backfill is done; the stats step
takes under a minute.

## New outputs, written to `data/site/`

- `leaderboard-house.json`, `leaderboard-senate.json`: one row per member
- `members/<bioguideId>.json`: full stats plus their bills
- `meta.json`: generation time, counts, and the written-out definitions behind every stat

## Definitions applied

- Rankings count bills and joint resolutions only (HR, S, HJRES, SJRES). Simple and
  concurrent resolutions are counted separately for member pages.
- Bipartisan = at least one ORIGINAL cosponsor from the other caucus.
- Withdrawn cosponsorships are excluded from every stat.
- Independents count with the caucus they sit with; party is evaluated as of the
  sponsorship date, so mid-term switches are handled correctly.
- Stage counts are cumulative: a bill that became law also counts as passed and reported.
- Members who left mid-Congress are included and flagged `"former": true`.

## Notes

- Member files skip rewriting when nothing changed, so nightly commits stay small.
- Each member page carries their 250 most recent cosponsorships; the full count is still
  in `cosponsored`.
