"""The governance gate: one rule inside change management, enforced in code.

A change from the record's DRI applies. A change from anyone else is HELD —
stored on the record as pending, flagged for DRI confirmation, logged — and the
calendar keeps saying what the DRI last said. The model cannot talk its way
past this: it never sees a tool that writes these fields.
"""
from __future__ import annotations

import json

from agent.schema import Launch, Sender


def is_dri(sender: Sender, launch: Launch) -> bool:
    if not launch.dri and not launch.dri_id:
        return True  # nobody owns it yet; first credible voice wins
    if launch.dri_id:
        return sender.id == launch.dri_id
    return sender.name.strip().lower() == launch.dri.strip().lower()


def hold(launch: Launch, sender: Sender, proposed: dict, note: str, now_iso: str) -> None:
    """Park a non-DRI change on the record instead of applying it."""
    launch.needs_dri_confirmation = True
    launch.pending_change = json.dumps(
        {"reported_by": sender.name, "reported_at": now_iso, "proposed": proposed, "note": note}
    )


def pending(launch: Launch) -> dict | None:
    if not launch.pending_change:
        return None
    try:
        return json.loads(launch.pending_change)
    except ValueError:
        return {"note": launch.pending_change, "proposed": {}}


def clear(launch: Launch) -> None:
    launch.needs_dri_confirmation = False
    launch.pending_change = ""
