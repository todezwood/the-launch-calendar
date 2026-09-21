"""The receipt: what this message actually changed, written by code, not by the model.

Built from the change-log rows the Dispatcher wrote plus a read-back of each record
from the store, so it says what is on the calendar — not what the model believes it did.
Same three parts every time: saved, held for the DRI, not done. The person can then
agree or correct it in the same thread.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from agent.schema import Change, Launch
from agent.tools import _text
from store.base import Store

LABELS = {
    "title": "Title", "dri": "DRI", "status": "Status", "ga_date": "GA date", "beta_date": "Beta date",
    "date_confidence": "Date confidence", "date_note": "Date note", "release_size": "Size",
    "feature_brief": "Brief", "audience": "Audience", "risk_level": "Risk", "risk_note": "Risk note",
    "depends_on": "Dependencies",
}
_LONG = ("feature_brief", "audience", "date_note", "risk_note")
_WROTE = ("created", "updated", "held_for_dri")
_FAILED = ("error", "duplicate", "possible_duplicate")
CLOSING = "Not right? Reply here with the correction."


def _show(field: str, value, now: datetime) -> str:
    value = _text(value)
    if not value:
        return "none"
    if field in ("ga_date", "beta_date"):
        try:
            d = date.fromisoformat(value)
            return f"{d:%a %b} {d.day}" + (f", {d.year}" if d.year != now.year else "")
        except ValueError:
            return value
    return value.replace("_", " ") if field in ("risk_level", "date_confidence") else value


def _created(launch: Launch, now: datetime) -> str:
    parts = [launch.status,
             f"GA {_show('ga_date', launch.ga_date, now)}" + (f" ({launch.date_confidence})" if launch.ga_date else ""),
             *([f"beta {_show('beta_date', launch.beta_date, now)}"] if launch.beta_date else []),
             f"size {launch.release_size or 'not set'}", f"DRI {launch.dri or 'not set'}"]
    return "• " + " · ".join(parts)


def _lines(rows: list[Change], fresh: Launch | None, now: datetime) -> list[str]:
    out, last = [], {}
    for row in rows:
        last[row.field] = (last[row.field][0] if row.field in last else row.old, row)   # first old, last new
    for field, (old, row) in last.items():
        if field == "created":
            out.append(_created(fresh, now) if fresh else f"• {row.new}")
        elif field == "pending":
            try:
                proposed = json.loads(row.new)
            except ValueError:
                proposed = {}
            out += [f"• {LABELS.get(k, k)} → {_show(k, v, now)}" for k, v in proposed.items()] or ["• (see the record)"]
        elif field == "pending_resolved":
            out.append(f"• Held change {row.new.replace(' by DRI', '')}")
        elif field in LABELS:
            auto = " (auto)" if row.actor.startswith("launch-agent") else ""
            if field in _LONG or field == "depends_on":
                line = f"• {LABELS[field]} updated{auto}"
            else:
                line = f"• {LABELS[field]}: {_show(field, old, now)} → {_show(field, row.new, now)}{auto}"
            # Read-back: the calendar is the truth, not the intent.
            if fresh and field != "depends_on" and _text(getattr(fresh, field, None))[:2000] != row.new[:2000]:
                shows = "differs" if field in _LONG else f"shows {_show(field, getattr(fresh, field, None), now)}"
                line += f" — calendar {shows}, please check"
            out.append(line)
    return out


def build(changes: list[Change], actions: list[dict], store: Store, now: datetime, exhausted: bool = False) -> str:
    if not changes:
        return ""
    groups: dict[str, list[Change]] = {}
    for row in changes:
        groups.setdefault(row.launch_id, []).append(row)
    out = ["———"]
    for launch_id, rows in groups.items():
        try:
            fresh = store.get(launch_id)
        except Exception:
            fresh = None
        title = fresh.title if fresh else rows[-1].launch_title
        fields = {r.field for r in rows}
        if "pending" in fields:
            head = f"*Held for {fresh.dri if fresh and fresh.dri else 'the DRI'} — not applied*"
        elif "created" in fields:
            head = "*New*"
        elif all(r.actor == "launch-agent (dependency rule)" for r in rows):
            head = "*Also flagged*"
        else:
            head = "*Saved*"
        out.append(f"{head} · *{title}*" + ("" if fresh else " (couldn't re-read to verify)"))
        out += _lines(rows, fresh, now)

    wrote = [i for i, a in enumerate(actions) if a["outcome"] in _WROTE]
    # A failure the model then recovered from is not "not done"; only what failed after the last write is.
    failed = [a for a in actions[(wrote[-1] + 1 if wrote else 0):]
              if a["tool"] != "query_records" and a["outcome"] in _FAILED]
    if failed or exhausted:
        out.append("*Not done*")
        out += [f"• {a.get('title') or a.get('record_id') or a['tool']}: {(a.get('error') or 'failed').split('. ')[0].rstrip('.')}"
                for a in failed]
        if exhausted:
            out.append("• I ran out of steps — check the list above and resend anything missing")
    for a in actions:
        if a["outcome"] == "no_change":
            out.append(f"Already up to date: *{a.get('title') or a.get('record_id')}*")
    out.append(CLOSING)
    return "\n".join(out)
