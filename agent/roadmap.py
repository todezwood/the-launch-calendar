"""The Roadmap view: grouped by status, sorted by next date, risks inline.

Deliberately NOT a date grid. Stakeholders ask "what's coming and what's
slipping", not "what's on Tuesday" — and a date grid hides exactly the work
that needs eyes: launches with no date, a removed date, or an unconfirmed
change. Here those sort to the bottom of their group with a marker, in view.
"""
from __future__ import annotations

from agent import governance
from agent.schema import STATUSES, Launch

RISK_MARK = {"on_track": "", "at_risk": "⚠️ at risk", "slipped": "🔻 slipped"}


def next_date(launch: Launch) -> str | None:
    """The next date a stakeholder cares about: beta until it's in beta, then GA."""
    if launch.status in ("Planned", "In Development", "Internal") and launch.beta_date:
        return launch.beta_date
    return launch.ga_date or launch.beta_date


def is_risky(launch: Launch) -> bool:
    if launch.status in ("GA", "Cancelled"):
        return launch.needs_dri_confirmation
    return (
        launch.risk_level != "on_track"
        or launch.needs_dri_confirmation
        or (not launch.ga_date and not launch.beta_date)
    )


def line(launch: Launch) -> str:
    dates = []
    if launch.beta_date:
        dates.append(f"beta {launch.beta_date}")
    if launch.ga_date:
        dates.append(f"GA {launch.ga_date} ({launch.date_confidence})")
    if not dates:
        dates.append("no date")
    bits = [f"*{launch.title}*", " / ".join(dates), f"DRI {launch.dri or '?'}", f"size {launch.release_size or '?'}"]
    mark = RISK_MARK.get(launch.risk_level, "")
    if mark:
        bits.append(f"{mark}: {launch.risk_note}" if launch.risk_note else mark)
    held = governance.pending(launch)
    if launch.needs_dri_confirmation and held:
        bits.append(f"❓ unconfirmed — {held.get('reported_by', 'someone')} says: {held.get('note', '')} (awaiting {launch.dri or 'DRI'})")
    return " · ".join(bits)


def render(launches: list[Launch], only_risky: bool = False) -> str:
    if only_risky:
        launches = [l for l in launches if is_risky(l)]
    if not launches:
        return "Nothing at risk right now." if only_risky else "The calendar is empty."
    out = []
    for status in STATUSES:
        group = [l for l in launches if l.status == status]
        if not group:
            continue
        group.sort(key=lambda l: (next_date(l) is None, next_date(l) or "", l.title.lower()))
        out.append(f"{status} ({len(group)})")
        out.extend(f"  • {line(l)}" for l in group)
    return "\n".join(out)
