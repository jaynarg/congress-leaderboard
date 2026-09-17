# Phase 2: plain-English summaries

Generates a summary for the 11,410 ranked bills (70%) that have no Congressional Research
Service summary, using the Anthropic Batch API at half the standard rate.

## Before you upload

1. Get an API key at console.anthropic.com and **add credits** (batches fail without a
   positive balance). Around $25 covers the whole backfill with room to spare.
2. Add it to the repo as a second secret: Settings -> Secrets and variables -> Actions ->
   New repository secret, named exactly `ANTHROPIC_API_KEY`.

## Files in this bundle

Keep the folder structure when uploading:

- `pipeline/summarize.py` (new) — fetches bill text, submits and collects batches
- `pipeline/stats.py` (replaces yours) — uses the AI summary when no CRS summary exists
- `.github/workflows/update-data.yml` (replaces yours) — adds the summarize step
- `member.html`, `methodology.html` (replace yours) — label AI summaries, explain them

## Do a 100-bill test run first

Actions -> Update Congress data -> Run workflow. The dropdown now has a
**"Max bills to summarize this run"** field: type `100` and run it.

Read a few summaries on the site afterwards, and check the reported cost in the log. If the
wording needs adjusting, the instructions live in the `SYSTEM` string at the top of
`pipeline/summarize.py`.

## Then let it run

Leave the field blank on later runs and it works through 2,500 bills per run, so the
backfill takes about five nights. Trigger extra runs manually to go faster.

## How the two-step batch works

Batches are asynchronous. A run submits one, waits up to 40 minutes, and if it hasn't
finished, saves the batch ID and exits. The next run collects it before submitting more.
Most batches finish in under an hour, so a single run usually does both.

## Guardrails

- `SUMMARY_MAX_SPEND` (default $60) is a cumulative ceiling across all runs. Once total
  spend passes it, no new batches are submitted until you raise it.
- Actual cost is read from the token usage in each batch result, not estimated, and is
  logged in `data/state/summary_state.json`.
- Bills whose text isn't published yet are marked and retried after two weeks.
- If a summary can't be written from the available text, the bill shows no summary rather
  than a bad one.
- A summary is replaced automatically once the Research Service publishes a real one.
- If the summarize step fails, the site still rebuilds and commits, and GitHub emails you.
