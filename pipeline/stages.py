"""Determine how far a bill advanced, from Congress.gov's standardized action codes.

Senate-sourced actions carry no action code, so we rely on the Library of Congress
"bill status" codes, which are present for both chambers, and fall back to action text.
"""

INTRODUCED, REPORTED, PASSED_ONE, PASSED_BOTH, BECAME_LAW = (
    "introduced", "reported", "passed_one_chamber", "passed_both_chambers", "became_law"
)
STAGE_ORDER = [INTRODUCED, REPORTED, PASSED_ONE, PASSED_BOTH, BECAME_LAW]
STAGE_LABELS = {
    INTRODUCED: "Introduced",
    REPORTED: "Out of committee",
    PASSED_ONE: "Passed one chamber",
    PASSED_BOTH: "Passed both chambers",
    BECAME_LAW: "Became law",
}

# Library of Congress standardized codes, verified against 119th Congress data.
REPORTED_CODES = {"5000", "14000", "1010", "5500", "14500"}  # reported or discharged
PASSED_HOUSE_CODES = {"8000"}
PASSED_SENATE_CODES = {"17000"}
BECAME_LAW_CODES = {"36000", "E40000"}


def bill_stage(bill):
    """Return (stage, passed_house, passed_senate) for a bill record."""
    passed_house = passed_senate = reported = became_law = False

    if bill.get("laws"):
        became_law = True

    for action in bill.get("actions") or []:
        code = action.get("actionCode")
        text = (action.get("text") or "").lower()
        if code in BECAME_LAW_CODES or text.startswith("became public law"):
            became_law = True
        elif code in PASSED_HOUSE_CODES or text.startswith("passed/agreed to in house"):
            passed_house = True
        elif code in PASSED_SENATE_CODES or text.startswith("passed/agreed to in senate"):
            passed_senate = True
        elif code in REPORTED_CODES:
            reported = True

    if became_law:
        stage = BECAME_LAW
    elif passed_house and passed_senate:
        stage = PASSED_BOTH
    elif passed_house or passed_senate:
        stage = PASSED_ONE
    elif reported:
        stage = REPORTED
    else:
        stage = INTRODUCED
    return stage, passed_house, passed_senate
