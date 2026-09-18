"""Generate plain-English summaries for bills that have no CRS summary yet.

Uses the Anthropic Message Batches API (50% cheaper than standard calls). A run either
submits a new batch or collects a batch submitted by an earlier run, so the work spreads
across nightly runs without ever blocking one.

Env:
  ANTHROPIC_API_KEY    required
  SUMMARY_MODEL        default claude-haiku-4-5-20251001
  SUMMARY_BATCH_SIZE   bills per batch (default 2500)
  SUMMARY_MAX_SPEND    cumulative USD ceiling across all runs (default 60)
  SUMMARY_POLL_MINUTES how long to wait for a submitted batch before leaving it (default 40)
  SUMMARY_LIMIT        cap this run's batch (for a small test run)
  SUMMARY_REGENERATE   set to 1 to rewrite summaries that already exist
  TEXT_FETCH_INTERVAL  seconds between bill-text downloads (default 0.5; govinfo is a
                       bulk-data host and tolerates a faster pace than congress.gov did)
"""
import argparse
import html
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from . import config
from .api import BudgetExhausted, CongressAPI

API_URL = "https://api.anthropic.com/v1/messages/batches"
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("SUMMARY_MODEL", "claude-haiku-4-5-20251001")
BATCH_SIZE = int(os.environ.get("SUMMARY_BATCH_SIZE", "2500"))
MAX_SPEND = float(os.environ.get("SUMMARY_MAX_SPEND", "60"))
POLL_MINUTES = float(os.environ.get("SUMMARY_POLL_MINUTES", "40"))
TEXT_CHAR_LIMIT = 12000
# Bill text comes from GPO's govinfo, the upstream publisher. The Library of Congress
# directs developers there for bulk use and blocks crawling of congress.gov file paths.
GOVINFO_HTML = "https://www.govinfo.gov/content/pkg/{pkg}/html/{pkg}.htm"
PACKAGE_RE = re.compile(r"(BILLS-[0-9A-Za-z]+)\.(?:htm|html|xml|txt)$", re.I)
TEXT_MIN_INTERVAL = float(os.environ.get("TEXT_FETCH_INTERVAL", "0.5"))
TEXT_MAX_ATTEMPTS = 4
TEXT_GIVE_UP_AFTER = 8   # consecutive blocked fetches before we stop collecting this run
MAX_TOKENS = 200
RETRY_NO_TEXT_DAYS = 14

# Haiku 4.5 is $1/$5 per million tokens; the Batch API halves both.
PRICE_IN = 0.50 / 1_000_000
PRICE_OUT = 2.50 / 1_000_000

SUMMARY_DIR = config.DATA_DIR / "ai-summaries"
STATE_FILE = config.DATA_DIR / "state" / "summary_state.json"

SYSTEM = (
    "You summarize United States federal legislation for a public, nonpartisan reference site. "
    "Given a bill's title and text, write one or two sentences, 40 words maximum, in plain English, "
    "describing what the measure would do if enacted. "
    "Open with the verb for its main action, in the third person: for example 'Authorizes grants to...', "
    "'Amends the Internal Revenue Code to...', 'Requires the Secretary to...', 'Establishes a program that...'. "
    "Requirements: state only what is in the text; do not speculate about motives, effects, politics, or "
    "likelihood of passage; use no praise or criticism; do not mention the sponsor; do not restate the bill "
    "number or title. If the text is too fragmentary to summarize, reply with exactly: INSUFFICIENT TEXT"
)

TAG_RE = re.compile(r"<[^>]+>")
_last_text_fetch = 0.0


def _read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path, obj, compact=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":") if compact else None,
                      indent=None if compact else 1) + "\n"
    path.write_text(text, encoding="utf-8")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_state():
    return _read_json(STATE_FILE, None) or {
        "batchId": None, "submittedAt": None, "pending": {},
        "spendUsd": 0.0, "summarized": 0, "insufficientText": 0, "errors": 0,
    }


def _headers():
    if not ANTHROPIC_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    return {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }


def summary_path(bill_type, number):
    return SUMMARY_DIR / bill_type / f"{number}.json"


def needs_summary(bill, regenerate=False):
    """True if this bill has no CRS summary and no usable stored AI summary."""
    if bill.get("summaries"):
        return False
    if regenerate:
        return True
    existing = _read_json(summary_path(bill["type"], bill["number"]))
    if not existing:
        return True
    if existing.get("text"):
        return False
    # Markers written before the rate-limit fix can't be trusted: some said "no text"
    # when the fetch had merely been blocked. Retry those once, whatever their age.
    if not existing.get("noTextConfirmed"):
        return True
    # Text wasn't published last time we looked; retry occasionally.
    checked = existing.get("checkedAt", "")
    try:
        when = datetime.fromisoformat(checked)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - when > timedelta(days=RETRY_NO_TEXT_DAYS)


def candidates(data_dir, regenerate=False):
    """Bills needing a summary: ranked types first, then oldest first.

    Oldest-first matters. Congress.gov publishes a bill's text days or weeks after
    introduction, so working newest-first spends API calls on bills that have no text yet.
    """
    order = {t: i for i, t in enumerate(config.ALL_TYPES)}
    found = []
    for path in (data_dir / "raw" / "bills").glob("*/*.json"):
        bill = _read_json(path)
        if bill and needs_summary(bill, regenerate):
            found.append(bill)
    found.sort(key=lambda b: (order.get(b["type"], 99), b.get("introducedDate") or "", int(b["number"])))
    return found


def govinfo_url(congress_gov_url):
    """Translate a congress.gov text URL into its govinfo equivalent.

    Congress.gov serves ...dow/119/bills/hr1491/BILLS-119hr1491rh.htm; the filename stem is
    the GPO package id, so the same document is at govinfo under /content/pkg/<id>/html/.
    """
    match = PACKAGE_RE.search(congress_gov_url or "")
    if not match:
        return None
    return GOVINFO_HTML.format(pkg=match.group(1))


def _get_text_file(url):
    """Fetch a bill text file, throttled, honouring 429s. Returns (text, status)."""
    global _last_text_fetch
    for attempt in range(TEXT_MAX_ATTEMPTS):
        wait = TEXT_MIN_INTERVAL - (time.time() - _last_text_fetch)
        if wait > 0:
            time.sleep(wait)
        _last_text_fetch = time.time()
        try:
            resp = requests.get(url, timeout=90, headers={
                "User-Agent": "congress-leaderboard/1.0 (nightly summary job; contact via GitHub)"
            })
        except requests.RequestException as exc:
            print(f"  network error fetching text ({exc}); retrying")
            time.sleep(15 * (attempt + 1))
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After")
            delay = int(retry_after) if (retry_after or "").isdigit() else 30 * (2 ** attempt)
            print(f"  congress.gov returned {resp.status_code}; waiting {delay}s")
            time.sleep(min(delay, 300))
            continue
        if resp.status_code == 404:
            return None, "no_text"
        if resp.status_code >= 400:
            return None, "error"
        return resp.text, "ok"
    return None, "error"


def fetch_text(api, bill):
    """Return (text, version_date, status) where status is ok, no_text, or error.

    'no_text' means Congress.gov has not published the text yet, which is a durable
    answer worth recording. 'error' means we could not reach it right now, which is not:
    recording that would skip a bill that does have text.
    """
    data = api.get(f"/bill/{config.CONGRESS}/{bill['type']}/{bill['number']}/text")
    versions = (data or {}).get("textVersions") or []
    if not versions:
        return None, None, "no_text"
    latest = max(versions, key=lambda v: v.get("date") or "")
    formats = {f.get("type"): f.get("url") for f in latest.get("formats") or []}
    url = formats.get("Formatted Text") or formats.get("Text") or next(
        (u for t, u in formats.items() if t and "PDF" not in t and u), None)
    if not url:
        return None, None, "no_text"
    source = govinfo_url(url)
    body, status = _get_text_file(source) if source else (None, "no_source")
    if status in ("no_text", "no_source", "error") and source:
        # Fall back to the congress.gov copy only if govinfo doesn't have this package.
        if status == "no_text":
            print(f"  {bill['id']}: not on govinfo, trying congress.gov")
            body, status = _get_text_file(url)
    elif not source:
        body, status = _get_text_file(url)
    if status != "ok" or not body:
        return None, latest.get("date"), "no_text" if status in ("no_text", "no_source") else status
    if "<" in body[:2000]:
        body = TAG_RE.sub(" ", body)
    body = html.unescape(body)
    body = "\n".join(line.strip() for line in body.splitlines())
    body = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]{2,}", " ", body)).strip()
    if not body:
        return None, latest.get("date"), "no_text"
    return body[:TEXT_CHAR_LIMIT], latest.get("date"), "ok"


def build_request(bill, text):
    prompt = (
        f"Bill: {bill['type'].upper()} {bill['number']} ({config.CONGRESS}th Congress)\n"
        f"Official title: {bill.get('title')}\n"
        f"Policy area: {bill.get('policyArea') or 'not assigned'}\n\n"
        f"Bill text (may be truncated):\n{text}"
    )
    return {
        "custom_id": f"{bill['type']}-{bill['number']}",
        "params": {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "system": SYSTEM,
            "messages": [{"role": "user", "content": prompt}],
        },
    }


def submit(state, data_dir, limit, regenerate=False):
    pool = candidates(data_dir, regenerate)
    print(f"{len(pool)} bills to summarize"
          + (" (regenerating existing summaries)" if regenerate else " (no CRS summary, none generated yet)"))
    if not pool:
        return state
    budget_left = MAX_SPEND - state["spendUsd"]
    if budget_left <= 0:
        print(f"Spend ceiling of ${MAX_SPEND:.2f} reached; not submitting. Raise SUMMARY_MAX_SPEND to continue.")
        return state
    # ~4 chars per token, plus prompt overhead and max output.
    per_bill = (TEXT_CHAR_LIMIT / 4 + 200) * PRICE_IN + MAX_TOKENS * PRICE_OUT
    affordable = max(1, int(budget_left / per_bill))
    target = min(limit or BATCH_SIZE, BATCH_SIZE, affordable, len(pool))
    print(f"Preparing up to {target} bills (worst-case ${target * per_bill:.2f}, ${budget_left:.2f} of budget left)")

    api = CongressAPI(config.API_KEY, time.time() + POLL_MINUTES * 60 + 3600)
    requests_payload, pending, no_text, blocked = [], {}, 0, 0
    for bill in pool:
        if len(requests_payload) >= target:
            break
        try:
            text, version_date, status = fetch_text(api, bill)
        except BudgetExhausted:
            print("  out of time while collecting bill text; submitting what we have")
            break
        if status == "error":
            # Don't record anything: the text may well exist, we just couldn't reach it.
            blocked += 1
            if blocked >= TEXT_GIVE_UP_AFTER:
                print(f"  congress.gov is refusing repeated requests ({blocked} in a row); "
                      "submitting what we have and leaving the rest for the next run")
                break
            continue
        blocked = 0
        if not text:
            _write_json(summary_path(bill["type"], bill["number"]),
                        {"text": None, "reason": "no bill text published yet",
                         "noTextConfirmed": True, "checkedAt": _now()})
            no_text += 1
            continue
        requests_payload.append(build_request(bill, text))
        pending[f"{bill['type']}-{bill['number']}"] = {
            "type": bill["type"], "number": bill["number"], "textVersionDate": version_date,
        }
    print(f"  {len(requests_payload)} ready, {no_text} had no published text, "
          f"{blocked} unreachable this run, {api.calls} Congress.gov API calls")
    if not requests_payload:
        return state

    resp = requests.post(API_URL, headers=_headers(),
                         json={"requests": requests_payload}, timeout=300)
    if resp.status_code >= 400:
        print(f"Batch submission failed ({resp.status_code}): {resp.text[:400]}")
        state["errors"] += 1
        return state
    batch = resp.json()
    state["batchId"] = batch["id"]
    state["submittedAt"] = _now()
    state["pending"] = pending
    print(f"Submitted batch {batch['id']} with {len(requests_payload)} bills")
    return state


def collect(state):
    """Poll the in-flight batch and write any finished summaries. Returns True when done."""
    batch_id = state["batchId"]
    deadline = time.time() + POLL_MINUTES * 60
    while True:
        resp = requests.get(f"{API_URL}/{batch_id}", headers=_headers(), timeout=60)
        if resp.status_code == 404:
            print(f"Batch {batch_id} no longer exists; clearing it and starting fresh next run.")
            state.update(batchId=None, pending={})
            return True
        resp.raise_for_status()
        batch = resp.json()
        status, counts = batch.get("processing_status"), batch.get("request_counts") or {}
        print(f"  batch {batch_id}: {status} {counts}")
        if status == "ended":
            break
        if time.time() > deadline:
            print("  still processing; the next run will collect it (batches can take up to 24 hours)")
            return False
        time.sleep(60)

    results = requests.get(batch.get("results_url") or f"{API_URL}/{batch_id}/results",
                           headers=_headers(), timeout=600)
    results.raise_for_status()
    written = insufficient = errored = 0
    spend = 0.0
    for line in results.text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cid = row.get("custom_id")
        info = state["pending"].get(cid)
        result = row.get("result") or {}
        if result.get("type") != "succeeded" or not info:
            errored += 1
            continue
        message = result.get("message") or {}
        usage = message.get("usage") or {}
        spend += usage.get("input_tokens", 0) * PRICE_IN + usage.get("output_tokens", 0) * PRICE_OUT
        text = " ".join(
            block.get("text", "") for block in message.get("content") or [] if block.get("type") == "text"
        ).strip()
        if not text or "INSUFFICIENT TEXT" in text.upper():
            _write_json(summary_path(info["type"], info["number"]),
                        {"text": None, "reason": "text too fragmentary to summarize", "checkedAt": _now()})
            insufficient += 1
            continue
        _write_json(summary_path(info["type"], info["number"]), {
            "text": text, "model": message.get("model", MODEL), "generatedAt": _now(),
            "textVersionDate": info.get("textVersionDate"),
            "inputTokens": usage.get("input_tokens"), "outputTokens": usage.get("output_tokens"),
        })
        written += 1
    state["spendUsd"] = round(state["spendUsd"] + spend, 4)
    state["summarized"] += written
    state["insufficientText"] += insufficient
    state["errors"] += errored
    state.update(batchId=None, submittedAt=None, pending={})
    print(f"Collected batch: {written} summaries written, {insufficient} unsummarizable, "
          f"{errored} errored. This batch cost ${spend:.2f}; ${state['spendUsd']:.2f} spent in total.")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=int(os.environ.get("SUMMARY_LIMIT", "0") or 0),
                        help="cap the number of bills submitted this run (for a test run)")
    parser.add_argument("--collect-only", action="store_true", help="collect an in-flight batch and stop")
    parser.add_argument("--regenerate", action="store_true",
                        default=os.environ.get("SUMMARY_REGENERATE", "").lower() in ("1", "true", "yes"),
                        help="rewrite summaries that already exist (use after changing the prompt)")
    args = parser.parse_args(argv)

    state = _load_state()
    try:
        if state.get("batchId"):
            finished = collect(state)
            if not finished or args.collect_only:
                return
        if not args.collect_only:
            state = submit(state, config.DATA_DIR, args.limit, args.regenerate)
            if state.get("batchId"):
                collect(state)
    finally:
        state["updatedAt"] = _now()
        _write_json(STATE_FILE, state, compact=False)
        print(json.dumps({k: state[k] for k in
                          ("batchId", "spendUsd", "summarized", "insufficientText", "errors")}, indent=1))


if __name__ == "__main__":
    main()
