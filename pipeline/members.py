"""Load every member who served in the target Congress from unitedstates/congress-legislators,
and resolve which caucus a member belonged to on a given date."""
import requests

from . import config

CAUCUS_CODES = {"Democrat": "D", "Republican": "R"}


def _overlaps_congress(term):
    # Terms ending exactly on CONGRESS_START belong to the previous Congress.
    return term["start"] < config.CONGRESS_END and term["end"] > config.CONGRESS_START


def fetch_members():
    members = []
    for url in config.LEGISLATORS_URLS:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        for person in resp.json():
            terms = [t for t in person.get("terms", []) if _overlaps_congress(t)]
            if not terms:
                continue
            name = person["name"]
            latest = terms[-1]
            members.append({
                "bioguideId": person["id"]["bioguide"],
                "name": name.get("official_full") or f"{name['first']} {name['last']}",
                "firstName": name.get("first"),
                "lastName": name.get("last"),
                "chamber": "senate" if latest["type"] == "sen" else "house",
                "state": latest["state"],
                "district": latest.get("district"),
                "party": latest["party"],
                "photoUrl": config.PHOTO_URL.format(bioguide=person["id"]["bioguide"]),
                "terms": [
                    {
                        "type": t["type"],
                        "start": t["start"],
                        "end": t["end"],
                        "state": t["state"],
                        "district": t.get("district"),
                        "party": t["party"],
                        "caucus": t.get("caucus"),
                        "partyAffiliations": t.get("party_affiliations"),
                    }
                    for t in terms
                ],
            })
    members.sort(key=lambda m: (m["chamber"], m["state"], m["lastName"] or ""))
    return members


def caucus_on(member, date):
    """Return 'D', 'R', or None (caucuses with neither) for a member on an ISO date.
    Independents count with the party they caucus with. Handles mid-term party switches."""
    date = date[:10]
    for term in member["terms"]:
        if not (term["start"] <= date <= term["end"]):
            continue
        party, caucus = term["party"], term.get("caucus")
        for aff in term.get("partyAffiliations") or []:
            if aff["start"] <= date <= aff["end"]:
                party, caucus = aff["party"], aff.get("caucus") or caucus
                break
        return CAUCUS_CODES.get(caucus or party)
    return None
