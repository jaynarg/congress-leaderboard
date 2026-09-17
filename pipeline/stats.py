"""Turn raw bill and member files into leaderboard and member-page JSON.

Reads data/raw/, writes data/site/. Safe to re-run; it rewrites its outputs each time.
"""
import html
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .members import caucus_on
from .stages import STAGE_LABELS, bill_stage

SITE_DIR = config.DATA_DIR / "site"
TAG_RE = re.compile(r"<[^>]+>")
SUMMARY_CHARS = 400
# A member page doesn't need every cosponsorship; the full count is still reported.
COSPONSORED_LIMIT = 250


def _write_json(path, obj):
    """Write only when content actually changed, to keep nightly commits (and git history) small."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except FileNotFoundError:
        pass
    path.write_text(text, encoding="utf-8")
    return True


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else None


def crs_summary(bill):
    """Latest CRS summary as plain text, truncated. Returns None if the bill has none."""
    summaries = bill.get("summaries") or []
    if not summaries:
        return None
    latest = max(summaries, key=lambda s: (s.get("actionDate") or "", s.get("updateDate") or ""))
    text = html.unescape(TAG_RE.sub(" ", latest.get("text") or ""))
    text = " ".join(text.split())
    if not text:
        return None
    if len(text) > SUMMARY_CHARS:
        cut = text[:SUMMARY_CHARS].rsplit(" ", 1)[0]
        text = cut + "..."
    return text


def _blank():
    return {
        "sponsored": 0, "cosponsored": 0, "resolutionsSponsored": 0,
        "stages": {k: 0 for k in STAGE_LABELS},
        "bipartisanSponsored": 0,
        "cosponsorsReceived": 0, "crossPartyCosponsorsReceived": 0,
        "cosponsorshipsGiven": 0, "crossPartyCosponsorshipsGiven": 0,
        "collaborators": defaultdict(int),
        "sponsoredBills": [], "cosponsoredBills": [],
    }


def build(data_dir=None):
    data_dir = Path(data_dir) if data_dir else config.DATA_DIR
    members = json.loads((data_dir / "raw" / "members.json").read_text(encoding="utf-8"))
    by_id = {m["bioguideId"]: m for m in members}
    acc = {m["bioguideId"]: _blank() for m in members}

    bill_files = sorted((data_dir / "raw" / "bills").glob("*/*.json"))
    skipped = 0
    for path in bill_files:
        bill = json.loads(path.read_text(encoding="utf-8"))
        ranked = bill["type"] in config.RANKED_TYPES
        sponsors = bill.get("sponsors") or []
        if not sponsors or sponsors[0].get("bioguideId") not in acc:
            skipped += 1
            continue
        sponsor_id = sponsors[0]["bioguideId"]
        intro = bill.get("introducedDate") or ""
        sponsor_caucus = caucus_on(by_id[sponsor_id], intro) if intro else None

        stage, _, _ = bill_stage(bill)
        # Withdrawn cosponsors don't count toward anything.
        cosponsors = [c for c in bill.get("cosponsors") or [] if not c.get("sponsorshipWithdrawnDate")]

        cross = cross_original = 0
        for c in cosponsors:
            cid = c.get("bioguideId")
            member = by_id.get(cid)
            c_caucus = caucus_on(member, c.get("sponsorshipDate") or intro) if member else None
            is_cross = bool(sponsor_caucus and c_caucus and c_caucus != sponsor_caucus)
            if is_cross:
                cross += 1
                if c.get("isOriginalCosponsor"):
                    cross_original += 1
            if cid in acc and ranked:
                a = acc[cid]
                a["cosponsored"] += 1
                a["cosponsorshipsGiven"] += 1
                if is_cross:
                    a["crossPartyCosponsorshipsGiven"] += 1
                    a["collaborators"][sponsor_id] += 1
                a["cosponsoredBills"].append({
                    "id": bill["id"], "number": f"{bill['type'].upper()} {bill['number']}",
                    "title": bill.get("title"), "stage": stage,
                    "date": c.get("sponsorshipDate"), "original": bool(c.get("isOriginalCosponsor")),
                    "sponsorId": sponsor_id, "crossParty": is_cross, "url": bill["congressGovUrl"],
                })

        bipartisan = cross_original > 0
        a = acc[sponsor_id]
        if ranked:
            a["sponsored"] += 1
            a["stages"][stage] += 1
            a["cosponsorsReceived"] += len(cosponsors)
            a["crossPartyCosponsorsReceived"] += cross
            if bipartisan:
                a["bipartisanSponsored"] += 1
            for c in cosponsors:
                cid = c.get("bioguideId")
                if cid in acc and by_id.get(cid) and caucus_on(by_id[cid], c.get("sponsorshipDate") or intro) not in (None, sponsor_caucus):
                    a["collaborators"][cid] += 1
        else:
            a["resolutionsSponsored"] += 1

        a["sponsoredBills"].append({
            "id": bill["id"], "number": f"{bill['type'].upper()} {bill['number']}",
            "type": bill["type"], "ranked": ranked, "title": bill.get("title"),
            "introducedDate": intro, "stage": stage, "policyArea": bill.get("policyArea"),
            "cosponsors": len(cosponsors), "crossPartyCosponsors": cross,
            "bipartisan": bipartisan, "latestAction": bill.get("latestAction"),
            "summary": crs_summary(bill), "summarySource": "crs" if crs_summary(bill) else None,
            "url": bill["congressGovUrl"],
        })

    rows = []
    for m in members:
        a = acc[m["bioguideId"]]
        last_day = min(max(t["end"] for t in m["terms"]), datetime.now(timezone.utc).date().isoformat())
        row = {
            "bioguideId": m["bioguideId"], "name": m["name"], "state": m["state"],
            "district": m["district"], "chamber": m["chamber"],
            "caucus": caucus_on(m, last_day), "party": m["party"],
            "former": max(t["end"] for t in m["terms"]) < datetime.now(timezone.utc).date().isoformat(),
            "photoUrl": m["photoUrl"],
            "sponsored": a["sponsored"], "cosponsored": a["cosponsored"],
            "resolutionsSponsored": a["resolutionsSponsored"],
            "reported": a["stages"]["reported"] + a["stages"]["passed_one_chamber"]
                        + a["stages"]["passed_both_chambers"] + a["stages"]["became_law"],
            "passedOneChamber": a["stages"]["passed_one_chamber"] + a["stages"]["passed_both_chambers"]
                                + a["stages"]["became_law"],
            "passedBothChambers": a["stages"]["passed_both_chambers"] + a["stages"]["became_law"],
            "becameLaw": a["stages"]["became_law"],
            "bipartisanSponsored": a["bipartisanSponsored"],
            "bipartisanPct": _pct(a["bipartisanSponsored"], a["sponsored"]),
            "crossPartyCosponsorPct": _pct(a["crossPartyCosponsorsReceived"], a["cosponsorsReceived"]),
            "reachingAcrossPct": _pct(a["crossPartyCosponsorshipsGiven"], a["cosponsorshipsGiven"]),
        }
        rows.append(row)

        top = sorted(a["collaborators"].items(), key=lambda kv: -kv[1])[:5]
        detail = dict(row)
        detail["topCrossPartyCollaborators"] = [
            {"bioguideId": cid, "name": by_id[cid]["name"], "caucus": caucus_on(by_id[cid], last_day), "count": n}
            for cid, n in top if cid in by_id
        ]
        detail["sponsoredBills"] = sorted(a["sponsoredBills"], key=lambda b: b["introducedDate"] or "", reverse=True)
        cosponsored = sorted(a["cosponsoredBills"], key=lambda b: b["date"] or "", reverse=True)
        detail["cosponsoredBills"] = cosponsored[:COSPONSORED_LIMIT]
        detail["cosponsoredBillsShown"] = len(detail["cosponsoredBills"])
        _write_json(SITE_DIR / "members" / f"{m['bioguideId']}.json", detail)

    for chamber in ("house", "senate"):
        chamber_rows = sorted(
            (r for r in rows if r["chamber"] == chamber),
            key=lambda r: (-r["sponsored"], r["name"]),
        )
        _write_json(SITE_DIR / f"leaderboard-{chamber}.json", chamber_rows)

    last_run = json.loads((data_dir / "state" / "last_run.json").read_text(encoding="utf-8"))
    meta = {
        "congress": config.CONGRESS,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataThrough": last_run.get("finishedAt"),
        "billsCounted": len(bill_files) - skipped,
        "billsSkipped": skipped,
        "members": len(members),
        "rankedTypes": [t.upper() for t in config.RANKED_TYPES],
        "stageLabels": STAGE_LABELS,
        "definitions": {
            "bipartisan": "Sponsored bill with at least one original cosponsor from the other caucus; withdrawn cosponsorships excluded.",
            "caucus": "Independents counted with the party they caucus with; party evaluated as of the sponsorship date.",
            "rankedTypes": "Bills and joint resolutions only (HR, S, HJRES, SJRES). Simple and concurrent resolutions appear on member pages but are not ranked.",
            "stageCounts": "Cumulative: a bill that became law also counts in passed and reported.",
        },
    }
    meta["cosponsoredBillsPerMemberLimit"] = COSPONSORED_LIMIT
    _write_json(SITE_DIR / "meta.json", meta)
    print(json.dumps({k: v for k, v in meta.items() if k not in ("stageLabels", "definitions")}, indent=1))
    return rows


if __name__ == "__main__":
    build()
