"""Fetch the bill index and full bill details (sponsor, cosponsors, summaries, actions)."""
from datetime import datetime, timezone

from . import config


def bill_id(bill_type, number):
    return f"{bill_type}{number}-{config.CONGRESS}"


def signature(item):
    """Change-detection token: refetch a bill whenever either update timestamp changes."""
    return f"{item.get('updateDate', '')}|{item.get('updateDateIncludingText', '')}"


def fetch_index(api):
    """Return {bill_id: {type, number, signature}} for every bill of every type in the Congress."""
    index = {}
    for bill_type in config.ALL_TYPES:
        count = 0
        for item in api.paginate(f"/bill/{config.CONGRESS}/{bill_type}", "bills"):
            number = str(item["number"])
            index[bill_id(bill_type, number)] = {
                "type": bill_type,
                "number": number,
                "signature": signature(item),
            }
            count += 1
        print(f"  {bill_type}: {count} bills")
    return index


def _cosponsor(c):
    return {
        "bioguideId": c.get("bioguideId"),
        "fullName": c.get("fullName"),
        "party": c.get("party"),
        "state": c.get("state"),
        "isOriginalCosponsor": c.get("isOriginalCosponsor"),
        "sponsorshipDate": c.get("sponsorshipDate"),
        "sponsorshipWithdrawnDate": c.get("sponsorshipWithdrawnDate"),
    }


def fetch_bill(api, bill_type, number):
    base = f"/bill/{config.CONGRESS}/{bill_type}/{number}"
    data = api.get(base)
    if not data or "bill" not in data:
        return None
    b = data["bill"]

    cos_meta = b.get("cosponsors") or {}
    cos_count = cos_meta.get("countIncludingWithdrawnCosponsors", cos_meta.get("count", 0)) or 0
    cosponsors = [_cosponsor(c) for c in api.paginate(f"{base}/cosponsors", "cosponsors")] if cos_count else []

    summaries = []
    if (b.get("summaries") or {}).get("count", 0):
        summaries = [
            {
                "versionCode": s.get("versionCode"),
                "actionDate": s.get("actionDate"),
                "actionDesc": s.get("actionDesc"),
                "updateDate": s.get("updateDate"),
                "text": s.get("text"),
            }
            for s in api.paginate(f"{base}/summaries", "summaries")
        ]

    actions = []
    if (b.get("actions") or {}).get("count", 0):
        actions = [
            {
                "actionDate": a.get("actionDate"),
                "actionCode": a.get("actionCode"),
                "type": a.get("type"),
                "text": a.get("text"),
                "source": (a.get("sourceSystem") or {}).get("name"),
            }
            for a in api.paginate(f"{base}/actions", "actions")
        ]

    return {
        "id": bill_id(bill_type, number),
        "congress": config.CONGRESS,
        "type": bill_type,
        "number": str(number),
        "title": b.get("title"),
        "introducedDate": b.get("introducedDate"),
        "originChamber": b.get("originChamber"),
        "policyArea": (b.get("policyArea") or {}).get("name"),
        "sponsors": [
            {
                "bioguideId": s.get("bioguideId"),
                "fullName": s.get("fullName"),
                "party": s.get("party"),
                "state": s.get("state"),
                "district": s.get("district"),
            }
            for s in b.get("sponsors") or []
        ],
        "cosponsors": cosponsors,
        "latestAction": b.get("latestAction"),
        "laws": b.get("laws") or [],
        "summaries": summaries,
        "actions": actions,
        "updateDate": b.get("updateDate"),
        "updateDateIncludingText": b.get("updateDateIncludingText"),
        "congressGovUrl": (
            f"https://www.congress.gov/bill/{config.CONGRESS}th-congress/"
            f"{config.CONGRESS_GOV_SLUGS[bill_type]}/{number}"
        ),
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
