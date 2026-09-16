"""Nightly entry point: refresh members, refresh the bill index, then fetch details for every
new or changed bill until done or out of time. Safe to stop and resume at any point."""
import json
import time
from datetime import datetime, timezone

from . import config
from .api import BudgetExhausted, CongressAPI
from .bills import fetch_bill, fetch_index
from .members import fetch_members


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path, obj, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def main():
    started = _now()
    deadline = time.time() + config.RUN_BUDGET_MINUTES * 60
    api = CongressAPI(config.API_KEY, deadline)

    print("Refreshing members...")
    members = fetch_members()
    _write_json(config.MEMBERS_FILE, members)
    print(f"  {len(members)} members served in the {config.CONGRESS}th Congress")

    print("Refreshing bill index...")
    index = fetch_index(api)

    state = _load_json(config.STATE_FILE, {})
    rank_order = {t: i for i, t in enumerate(config.ALL_TYPES)}
    queue = sorted(
        (bid for bid, item in index.items() if state.get(bid) != item["signature"]),
        key=lambda bid: (rank_order[index[bid]["type"]], int(index[bid]["number"])),
    )
    print(f"{len(queue)} bills new or changed (of {len(index)})")

    fetched = failed = 0
    try:
        for i, bid in enumerate(queue, 1):
            item = index[bid]
            try:
                bill = fetch_bill(api, item["type"], item["number"])
            except BudgetExhausted:
                raise
            except Exception as exc:  # one bad bill shouldn't sink the run; it retries next night
                print(f"  failed {bid}: {exc}")
                failed += 1
                continue
            if bill:
                _write_json(config.BILLS_DIR / item["type"] / f"{item['number']}.json", bill, compact=True)
            state[bid] = item["signature"]
            fetched += 1
            if i % 100 == 0:
                _write_json(config.STATE_FILE, state, compact=True)
                print(f"  {i}/{len(queue)} processed, {api.calls} API calls so far")
        complete = failed == 0
    except BudgetExhausted:
        print("Time budget reached; saving progress. The next run will resume.")
    finally:
        _write_json(config.STATE_FILE, state, compact=True)
        remaining = sum(1 for bid, item in index.items() if state.get(bid) != item["signature"])
        report = {
            "congress": config.CONGRESS,
            "startedAt": started,
            "finishedAt": _now(),
            "apiCalls": api.calls,
            "billsInIndex": len(index),
            "billsFetched": fetched,
            "billsFailed": failed,
            "billsRemaining": remaining,
            "upToDate": remaining == 0,
        }
        _write_json(config.LAST_RUN_FILE, report)
        print(json.dumps(report, indent=1))

    if failed > 25:
        # Many per-bill failures suggests an API change; fail the workflow so GitHub emails you.
        # Progress is still committed by the workflow's final step.
        raise SystemExit(1)


if __name__ == "__main__":
    main()
