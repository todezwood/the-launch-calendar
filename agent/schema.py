"""The Launch Calendar schema — every field earns its place.

v1's goal is visibility into three things: the ROADMAP, DELIVERY DATES, and
RISKS. Each field below maps to one of those, and to a stakeholder question the
calendar has to answer without anyone pinging the DRI.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

# Status speaks go-to-market language, not engineering language. The line that
# matters to Sales/Marketing is "can I talk about it / can I sell it":
#   Planned, In Development  -> not yet
#   Internal                 -> dogfooding only, don't mention externally
#   Limited Beta             -> named/flagged accounts only
#   Open Beta                -> any customer can use it; talk about it, caveat it
#   GA                       -> sell it
# Beta is its own status on purpose (test message 9 asks exactly this).
STATUSES = [
    "Planned",
    "In Development",
    "Internal",
    "Limited Beta",
    "Open Beta",
    "GA",
    "On Hold",
    "Cancelled",
]

# Release size is a proxy for "how much go-to-market does this need":
#   S = ships quietly (changelog line at most)
#   M = support heads-up + changelog / in-app note
#   L = full launch: blog post, sales enablement, support training
RELEASE_SIZES = ["S", "M", "L"]

# committed = DRI has promised the date; target = best estimate ("about two
# weeks, assuming nothing breaks"); tbd = no date anyone should repeat to a
# customer (test message 7 removes a date — that must be representable).
DATE_CONFIDENCE = ["committed", "target", "tbd"]

RISK_LEVELS = ["on_track", "at_risk", "slipped"]


@dataclass
class Launch:
    # --- Roadmap: what is going out, who owns it -------------------------
    id: str = ""                    # store-assigned (slug locally, page id in Notion)
    title: str = ""                 # REQUIRED. What people call it in chat.
    dri: str = ""                   # REQUIRED. One accountable human; default = whoever announced it.
    dri_id: str = ""                # Chat user id of the DRI. Set by code from the message envelope;
                                    #   it is what the governance gate compares against.
    status: str = "Planned"         # REQUIRED. GTM-readable stage (see STATUSES).
    release_size: str = ""          # REQUIRED (may be unanswered). Drives Marketing/Support prep.
    feature_brief: str = ""         # One or two lines on what it is; scope changes land here (msg 10).
    audience: str = ""              # Who gets it and in what order ("internal first, then early
                                    #   adopters", "flagged for a handful of accounts"). Sales' question.

    # --- Delivery dates --------------------------------------------------
    ga_date: str | None = None      # REQUIRED field, but may be empty: an honest blank beats a stale date.
    beta_date: str | None = None    # Half of real announcements are betas; a beta slip needs a date to slip.
    date_confidence: str = "tbd"    # committed / target / tbd — Sales' "is the date still true?"
    date_note: str = ""             # The assumption behind a fuzzy date ("'end of the month' -> Aug 31").

    # --- Risks -----------------------------------------------------------
    risk_level: str = "on_track"    # on_track / at_risk / slipped. Set by code on slips and removed dates.
    risk_note: str = ""             # Why, in one line.
    depends_on: list[str] = field(default_factory=list)   # Upstream launches. A slip flags everything downstream.
    needs_dri_confirmation: bool = False   # Governance: a non-DRI reported a change; it is held, not applied.
    pending_change: str = ""        # The held change (who said what), until the DRI confirms or rejects.

    # --- Trust / bookkeeping (never writable by the model) ---------------
    open_question: str = ""         # What the agent last asked about this record...
    question_for: str = ""          #   ...and whom. Makes a bare "M" or "next tues" land on the right record.
    last_updated: str = ""          # Staleness is the calendar's core failure mode (msg A).
    last_updated_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Launch":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class Change:
    """One append-only row of history. Answers Leadership's question:
    "what slipped, and when did we find out?" """
    timestamp: str
    actor: str          # who told the agent (from the chat envelope, never from the model)
    launch_id: str
    launch_title: str
    field: str          # which field, or "created" / "pending" / "pending_resolved"
    old: str
    new: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Sender:
    """Who is talking to the agent. Comes from Slack (or --as on the CLI)."""
    id: str
    name: str


# Left out of v1 on purpose (README "what I left out"):
#   goal / initiative linkage, legal & data-touch flag, notification prefs,
#   approval workflow, per-field permissions.
