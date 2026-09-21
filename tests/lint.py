"""Reply lint: deterministic checks run on every live reply (see cal.say in test_messages.py).

Errors fail the test. Warnings are only counted and printed with the scorecard: they flag
something worth a look, but a legitimate reply can trip them.
"""
import re
from datetime import date, timedelta

# An offer to do something the agent cannot do. Narrow on purpose: "I'll keep the calendar current" is fine.
FAKE_OFFER = re.compile(
    r"\b(happy to|glad to|i can|i could|i'll|i will|want me to|shall i|should i|let me)\s+"
    r"(ping|notify|nudge|remind|message|email|dm|reach out|follow up|check with|loop in|let \w+(?: \w+)? know"
    r"|flag (?:it|this|that|these|those|any[^.?!]*?) (?:to|with|for))\b", re.I)
# "Next week" answered with the rest of THIS week (the clock is Mon Aug 24; next week starts Aug 31).
WRONG_NEXT_WEEK = re.compile(r"aug(ust)?\.? 2[4-9]\s*(–|—|-|to|through)\s*(aug(ust)?\.? )?(2[5-9]|3[01])", re.I)
WROTE = {"created", "updated", "held_for_dri"}
_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? (\d{1,2})\b", re.I)


def dates_in(text: str, year: int) -> set[str]:
    found = set()
    for iso, month, day in _DATE.findall(text):
        try:
            found.add(iso or date(year, _MONTHS.index(month.lower()) + 1, int(day)).isoformat())
        except ValueError:
            pass
    return found


def lint(message: str, reply, launches, now) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    offer = FAKE_OFFER.search(reply.prose)
    if offer:
        errors.append(f"offers an action the agent cannot perform: {offer[0]!r}")
    wrote = any(a["outcome"] in WROTE for a in reply.actions)
    if wrote and not reply.receipt:
        errors.append("a write happened but the reply carries no receipt")
    if reply.receipt and not reply.changes:
        errors.append("a receipt with no change-log rows behind it")

    # Date grounding (warning): every date the model states should be on a record, in a change, in the message,
    # or be today / a week boundary. Replies like "through Sep 14" (today + 21) are legitimate, hence no hard fail.
    monday = now.date() - timedelta(days=now.weekday())
    allowed = {now.date().isoformat()} | {(monday + timedelta(days=d)).isoformat() for d in (0, 6, 7, 13)}
    allowed |= dates_in(message, now.year)
    for launch in launches:
        allowed |= {d for d in (launch.ga_date, launch.beta_date) if d} | dates_in(launch.date_note + launch.risk_note, now.year)
    for row in reply.changes:
        allowed |= dates_in(f"{row['old']} {row['new']}", now.year)
    loose = sorted(dates_in(reply.prose, now.year) - allowed)
    if loose:
        warnings.append(f"dates not found on the calendar or in the message: {loose}")
    return errors, warnings
