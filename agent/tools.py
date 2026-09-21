"""The three tools the model may call, and the code that executes them.

The tool input schemas are a NARROWED projection of schema.py: the model can
propose titles, dates, statuses — it can never write who said something, who
the DRI's chat id is, the governance flag, timestamps, or change-log rows.
Those come from the message envelope and are written here, in code.

Only the fields that always apply are required; everything else is optional and
simply omitted when the message doesn't speak to it.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime

from agent import governance, roadmap
from agent.schema import DATE_CONFIDENCE, RELEASE_SIZES, RISK_LEVELS, STATUSES, Change, Launch, Sender
from store.base import Store

STRICT = os.environ.get("STRICT_TOOLS", "1") == "1"

_DATE = "ISO date YYYY-MM-DD, already resolved against today's date. Omit if not provided."


def _s(desc: str) -> dict:
    return {"type": "string", "description": desc}


def _enum(values: list[str], desc: str) -> dict:
    return {"type": "string", "enum": values, "description": desc}


def _tool(name: str, description: str, properties: dict, required: list[str], strict: bool = True) -> dict:
    tool = {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }
    if STRICT and strict:
        tool["strict"] = True
    return tool


_SHARED = {
    "title": _s("Short canonical launch title, e.g. 'SharePoint connector'."),
    "dri_name": _s("The DRI's name ONLY if the message names someone other than the sender. Otherwise omit."),
    "ga_date": _s("General-availability date. " + _DATE),
    "beta_date": _s("Date the beta / early-access / internal rollout starts, when the message gives one. " + _DATE),
    "date_note": _s("The assumption behind a fuzzy date, e.g. \"'end of the month' -> 2026-08-31\" or 'assuming nothing breaks'. Omit if none."),
    "feature_brief": _s("One or two lines on what is shipping. Omit if not provided."),
    "audience": _s("Who gets it and in what order, e.g. 'internal first, then early adopters'. Omit if not provided."),
    "risk_note": _s("One line on why this is at risk, if the message says so. Omit otherwise."),
    "open_question": _s("If your reply asks the sender something about this record, the question(s) verbatim. Omit if you are not asking anything."),
}

TOOLS = [
    _tool(
        "create_record",
        "Create a NEW launch record. Only for launches not already on the calendar — if one "
        "might already exist, use update_record. Create immediately with what you have; never wait for answers.",
        {
            "title": _SHARED["title"],
            "dri_name": _SHARED["dri_name"],
            "status": _enum(STATUSES, "Current stage, not the future one. A launch that is 'planned to ship next week' is In Development."),
            "ga_date": _SHARED["ga_date"],
            "beta_date": _SHARED["beta_date"],
            "date_confidence": _enum(["tbd", "target", "committed"], "committed = firm promise; target = estimate or hedged; tbd = no GA date."),
            "date_note": _SHARED["date_note"],
            "release_size": _enum(RELEASE_SIZES + ["unknown"], "S/M/L only when stated or obvious (a keyboard shortcut is S). Otherwise unknown."),
            "feature_brief": _SHARED["feature_brief"],
            "audience": _SHARED["audience"],
            "risk_level": _enum(RISK_LEVELS, "on_track unless the message signals trouble."),
            "risk_note": _SHARED["risk_note"],
            "depends_on": {"type": "array", "items": {"type": "string"}, "description": "Ids of existing records this launch cannot ship without. Usually empty."},
            "open_question": _SHARED["open_question"],
            "confirmed_not_duplicate": {"type": "boolean", "description": "Set true only when retrying after a possible-duplicate warning and you are sure this is a different launch."},
        },
        required=["title", "status", "date_confidence", "release_size", "risk_level"],
        # Not strict: under the strict grammar the model sent only the required fields and patched the rest in
        # with a second call — a launch whose beta date depends on a follow-up landing. _checked validates it.
        strict=False,
    ),
    _tool(
        "update_record",
        "Change an existing launch record. Provide only what changed; omit everything else. "
        "If the sender is not the record's DRI the change is held for DRI confirmation instead of applied — "
        "the result tells you which happened.",
        {
            "record_id": _s("Id of the record, exactly as shown in the calendar."),
            "title": _s("New title, only if renaming. Omit otherwise."),
            "dri_name": _s("New DRI name, only if ownership is changing. Omit otherwise."),
            "status": _enum(STATUSES + ["unchanged"], "New stage, or unchanged."),
            "ga_date": _SHARED["ga_date"],
            "clear_ga_date": {"type": "boolean", "description": "True to REMOVE the GA date (someone is un-committing). Confidence becomes tbd."},
            "beta_date": _SHARED["beta_date"],
            "clear_beta_date": {"type": "boolean", "description": "True to remove the beta date."},
            "date_confidence": _enum(DATE_CONFIDENCE + ["unchanged"], "New confidence in the GA date, or unchanged."),
            "date_note": _SHARED["date_note"],
            "release_size": _enum(RELEASE_SIZES + ["unchanged"], "New size, or unchanged."),
            "feature_brief": _s("The FULL updated brief (not a diff) if scope changed. Omit otherwise."),
            "audience": _s("The full updated audience/rollout text. Omit if unchanged."),
            "risk_level": _enum(RISK_LEVELS + ["unchanged"], "Only set when the message speaks to risk; slips and removed dates are flagged automatically."),
            "risk_note": _SHARED["risk_note"],
            "add_depends_on": {"type": "array", "items": {"type": "string"}, "description": "Record ids to add as upstream dependencies."},
            "remove_depends_on": {"type": "array", "items": {"type": "string"}, "description": "Record ids to remove from dependencies."},
            "answers_open_question": {"type": "boolean", "description": "True if this message answers the record's open question."},
            "open_question": _SHARED["open_question"],
            "pending_decision": _enum(["none", "confirm", "reject"], "When the DRI responds to a held (unconfirmed) change: confirm applies it, reject discards it."),
            "change_note": _s("One line for the change log: what changed and why, in the sender's terms."),
        },
        # The API caps the combined complexity of strict schemas and this one tips it over.
        # Its inputs are validated in code instead (_checked), which holds for every tool anyway.
        required=["record_id"],
        strict=False,
    ),
    _tool(
        "query_records",
        "Read the calendar to answer a question. 'roadmap' and 'risk' return a pre-rendered view — relay it as is. "
        "'history' returns the change log (what slipped, and when we found out).",
        {
            "view": _enum(["list", "roadmap", "risk", "history"], "Which view."),
            "text": _s("Filter: words that must appear in title/brief/audience/DRI. Omit for all."),
            "status": _enum(STATUSES + ["any"], "Filter by stage."),
            "date_from": _s("Only launches with a beta or GA date on/after this ISO date. Omit for no bound."),
            "date_to": _s("Only launches with a beta or GA date on/before this ISO date. Omit for no bound."),
            "record_id": _s("For 'history': limit to one record. Omit for all."),
        },
        required=["view"],
    ),
]


def compact(launch: Launch) -> dict:
    """A record as the model sees it: no empty fields, held change decoded."""
    data = {k: v for k, v in launch.to_dict().items() if v not in ("", None, [], False)}
    data.pop("dri_id", None)
    data.pop("question_for", None)
    data.pop("thread", None)
    held = governance.pending(launch)
    if held:
        data["pending_change"] = held
    return data


def _iso(value: str, label: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ToolError(f"{label} must be an ISO date (YYYY-MM-DD), got {value!r}.")


class ToolError(Exception):
    pass


class Dispatcher:
    """Executes tool calls for ONE inbound message from ONE sender."""

    def __init__(self, store: Store, sender: Sender, now: datetime, thread: str = ""):
        self.store, self.sender, self.now, self.thread = store, sender, now, thread
        self.mutations = 0
        self.actions: list[dict] = []   # what actually happened — for logs and tests
        self.changes: list[Change] = []  # every change-log row this message wrote — the receipt is built from these

    # -- plumbing ---------------------------------------------------------
    def call(self, name: str, args: dict) -> dict:
        handler = {"create_record": self._create, "update_record": self._update, "query_records": self._query}.get(name)
        try:
            if handler is None:
                raise ToolError(f"Unknown tool {name!r}.")
            result = handler(_checked(name, args))
        except ToolError as err:
            result = {"ok": False, "error": str(err)}
        self.actions.append({"tool": name, "outcome": result.get("outcome", "error" if not result.get("ok", True) else "ok"),
                             "record_id": result.get("record", {}).get("id", args.get("record_id", "")),
                             "title": result.get("record", {}).get("title") or args.get("title", ""),
                             "error": result.get("error", "")})
        return result

    def _log(self, launch: Launch, field: str, old, new, note: str = "", actor: str | None = None) -> None:
        change = Change(
            timestamp=self.now.isoformat(timespec="seconds"), actor=actor or self.sender.name,
            launch_id=launch.id, launch_title=launch.title, field=field,
            old=_text(old), new=_text(new), note=note,
        )
        self.changes.append(change)
        self.store.add_change(change)

    def _stamp(self, launch: Launch) -> None:
        launch.last_updated = self.now.isoformat(timespec="seconds")
        launch.last_updated_by = self.sender.name

    def _stamp_thread(self, launch: Launch) -> set[str]:
        """The chat thread a record was last written from, so a bare reply there finds it."""
        if self.thread and launch.thread != self.thread:
            launch.thread = self.thread
            return {"thread"}
        return set()

    # -- create -----------------------------------------------------------
    def _create(self, a: dict) -> dict:
        title = a["title"].strip()
        if not title or re.sub(r"[^a-z]", "", title.lower()) in _NOT_A_TITLE:
            raise ToolError("A record needs a real title: the name of the launch. Nothing was created.")
        same = [l for l in self.store.list() if l.title.strip().lower() == title.lower()]
        if same:   # the override below is for look-alikes, never for the same title
            return {"ok": False, "outcome": "duplicate",
                    "error": "This record already exists (you may have just created it). Use update_record on it.",
                    "similar": [{"id": l.id, "title": l.title, "dri": l.dri} for l in same]}
        if not a.get("confirmed_not_duplicate"):
            similar = self.store.find(title)
            if similar:
                return {"ok": False, "outcome": "possible_duplicate",
                        "error": "A similar record already exists. Use update_record on it, or retry with confirmed_not_duplicate=true if this is genuinely a different launch.",
                        "similar": [{"id": l.id, "title": l.title, "dri": l.dri} for l in similar]}
        ga, beta = _iso(a["ga_date"], "ga_date"), _iso(a["beta_date"], "beta_date")
        named = a["dri_name"].strip()
        other_dri = bool(named) and named.lower() != self.sender.name.lower()
        launch = Launch(
            title=title,
            dri=named if other_dri else self.sender.name,
            dri_id="" if other_dri else self.sender.id,
            status=a["status"], ga_date=ga, beta_date=beta,
            date_confidence="tbd" if not ga else a["date_confidence"],
            date_note=a["date_note"].strip(),
            release_size="" if a["release_size"] == "unknown" else a["release_size"],
            feature_brief=a["feature_brief"].strip(), audience=a["audience"].strip(),
            risk_level=a["risk_level"], risk_note=a["risk_note"].strip(),
            depends_on=self._valid_ids(a["depends_on"]),
        )
        self._set_question(launch, a["open_question"])
        self._stamp(launch)
        self._stamp_thread(launch)
        launch = self.store.save(launch)
        self.mutations += 1
        self._log(launch, "created", "", f"{launch.status}; GA {ga or 'none'}; beta {beta or 'none'}; size {launch.release_size or '?'}")
        return {"ok": True, "outcome": "created", "record": compact(launch)}

    # -- update -----------------------------------------------------------
    def _update(self, a: dict) -> dict:
        launch = self.store.get(a["record_id"].strip())
        if not launch:
            raise ToolError("No record with that id. Valid ids: " + ", ".join(l.id for l in self.store.list()))

        proposed: dict = {}
        for key in ("title", "feature_brief", "audience", "date_note", "risk_note"):
            if a[key].strip():
                proposed[key] = a[key].strip()
        if a["dri_name"].strip():
            proposed["dri"] = a["dri_name"].strip()
        for key in ("status", "date_confidence", "release_size", "risk_level"):
            if a[key] != "unchanged":
                proposed[key] = a[key]
        for key in ("ga_date", "beta_date"):
            value = _iso(a[key], key)
            if a[f"clear_{key}"]:
                proposed[key] = None
            elif value:
                proposed[key] = value
        add, remove = self._valid_ids(a["add_depends_on"]), set(a["remove_depends_on"])
        if add or remove:
            proposed["depends_on"] = [d for d in dict.fromkeys(launch.depends_on + add) if d not in remove and d != launch.id]
        note = a["change_note"].strip()
        sender_is_dri = governance.is_dri(self.sender, launch)

        # The DRI ruling on a held change
        decision = a["pending_decision"]
        held = governance.pending(launch)
        if decision != "none":
            if not sender_is_dri:
                raise ToolError(f"Only the DRI ({launch.dri}) can confirm or reject a held change.")
            if held and decision == "confirm":
                proposed = {**held.get("proposed", {}), **proposed}

        # THE GATE: a non-DRI's change is held, not applied.
        if not sender_is_dri:
            if not proposed:
                raise ToolError("Nothing to change.")
            governance.hold(launch, self.sender, proposed, note, self.now.isoformat(timespec="seconds"))
            self.store.update(launch, {"needs_dri_confirmation", "pending_change"} | self._stamp_thread(launch))
            self.mutations += 1
            self._log(launch, "pending", "", _text(proposed), note=f"Held for {launch.dri} to confirm. {note}".strip())
            return {"ok": True, "outcome": "held_for_dri",
                    "message": f"NOT applied: {self.sender.name} is not the DRI. Held as unconfirmed until {launch.dri} confirms. "
                               "The record's own fields are unchanged. Tell the sender exactly that.",
                    "record": compact(launch)}

        changed: set[str] = set()
        date_events: list[str] = []
        for key, new in proposed.items():
            old = getattr(launch, key)
            if old == new:
                continue
            setattr(launch, key, new)
            changed.add(key)
            self._log(launch, key, old, new, note)
            if key in ("ga_date", "beta_date"):
                label = "GA" if key == "ga_date" else "Beta"
                if new is None:
                    date_events.append(f"{label} date {old} removed")
                elif old and new > old:
                    date_events.append(f"{label} slipped {old} → {new}")
        if "dri" in changed:
            launch.dri_id = self.sender.id if launch.dri.lower() == self.sender.name.lower() else ""
            changed.add("dri_id")

        # Risk is derived in code so it cannot be forgotten.
        if launch.ga_date is None and launch.date_confidence != "tbd":
            self._set(launch, "date_confidence", "tbd", changed, note)
        slipped = any("slipped" in e for e in date_events)
        if slipped and launch.risk_level != "slipped":
            # A date that moved later is a slip, whatever the model called it.
            self._set(launch, "risk_level", "slipped", changed, note)
            if not proposed.get("risk_note"):
                self._set(launch, "risk_note", "; ".join(date_events) + (f" — {note}" if note else ""), changed, "")
        elif "risk_level" not in proposed:
            if date_events:
                level = "slipped" if any("slipped" in e for e in date_events) else "at_risk"
                self._set(launch, "risk_level", level, changed, note)
                self._set(launch, "risk_note", "; ".join(date_events) + (f" — {note}" if note else ""), changed, "")
            elif proposed.get("status") == "On Hold":
                self._set(launch, "risk_level", "at_risk", changed, note)
            elif proposed.get("status") == "GA" and launch.risk_level != "on_track":
                self._set(launch, "risk_level", "on_track", changed, note)
                self._set(launch, "risk_note", "", changed, "")

        if held and (decision != "none" or set(held.get("proposed", {})) & changed):
            governance.clear(launch)
            changed |= {"needs_dri_confirmation", "pending_change"}
            self._log(launch, "pending_resolved", _text(held.get("proposed", {})),
                      "rejected by DRI" if decision == "reject" else "confirmed by DRI", note)

        if a["answers_open_question"] and launch.open_question:
            launch.open_question, launch.question_for = "", ""
            changed |= {"open_question", "question_for"}
        if a["open_question"].strip():
            self._set_question(launch, a["open_question"])
            changed |= {"open_question", "question_for"}

        if not changed:
            return {"ok": True, "outcome": "no_change", "message": "Record already says that.", "record": compact(launch)}

        self._stamp(launch)
        self.store.update(launch, changed | {"last_updated", "last_updated_by"} | self._stamp_thread(launch))
        self.mutations += 1
        downstream = self._flag_downstream(launch, date_events, proposed)
        return {"ok": True, "outcome": "updated", "changed": sorted(changed), "record": compact(launch),
                "downstream_flagged": downstream}

    def _set(self, launch: Launch, key: str, new, changed: set[str], note: str) -> None:
        old = getattr(launch, key)
        if old != new:
            setattr(launch, key, new)
            changed.add(key)
            self._log(launch, key, old, new, note, actor="launch-agent (risk rule)")

    def _set_question(self, launch: Launch, question: str) -> None:
        question = question.strip()
        if question:
            launch.open_question, launch.question_for = question, self.sender.id

    def _valid_ids(self, ids: list[str]) -> list[str]:
        bad = [i for i in ids if not self.store.get(i)]
        if bad:
            raise ToolError(f"Unknown record ids in dependencies: {bad}")
        return list(dict.fromkeys(ids))

    def _flag_downstream(self, upstream: Launch, date_events: list[str], proposed: dict) -> list[dict]:
        """A slip upstream puts every dependent launch at risk — visibly."""
        reason = "; ".join(date_events) or ("put on hold" if proposed.get("status") == "On Hold" else "")
        if not reason:
            return []
        flagged = []
        for other in self.store.list():
            if upstream.id not in other.depends_on or other.status in ("GA", "Cancelled"):
                continue
            changed: set[str] = set()
            if other.risk_level == "on_track":
                self._set_dep(other, "risk_level", "at_risk", changed)
            self._set_dep(other, "risk_note", f"Upstream '{upstream.title}': {reason}", changed)
            if changed:
                self.store.update(other, changed)
                flagged.append({"id": other.id, "title": other.title, "dri": other.dri})
        return flagged

    def _set_dep(self, launch: Launch, key: str, new, changed: set[str]) -> None:
        old = getattr(launch, key)
        if old != new:
            setattr(launch, key, new)
            changed.add(key)
            self._log(launch, key, old, new, actor="launch-agent (dependency rule)")

    # -- query ------------------------------------------------------------
    def _query(self, a: dict) -> dict:
        launches = self.store.list()
        words = a["text"].lower().split()
        if words:
            launches = [l for l in launches if all(
                w in f"{l.title} {l.feature_brief} {l.audience} {l.dri}".lower() for w in words)]
        if a["status"] != "any":
            launches = [l for l in launches if l.status == a["status"]]
        lo, hi = _iso(a["date_from"], "date_from"), _iso(a["date_to"], "date_to")
        if lo or hi:
            def in_window(l: Launch) -> bool:
                return any(d and (not lo or d >= lo) and (not hi or d <= hi) for d in (l.beta_date, l.ga_date))
            launches = [l for l in launches if in_window(l)]
        view = a["view"]
        if view == "history":
            ids = {l.id for l in launches}
            rid = a["record_id"].strip()
            rows = [c.to_dict() for c in self.store.list_changes(rid or None) if rid or c.launch_id in ids]
            return {"ok": True, "outcome": "queried", "changes": rows[-60:]}
        if view in ("roadmap", "risk"):
            return {"ok": True, "outcome": "queried", "rendered": roadmap.render(launches, only_risky=view == "risk")}
        return {"ok": True, "outcome": "queried", "records": [compact(l) for l in launches]}


_NEUTRAL = ("unchanged", "unknown", "any", "none")
_NOT_A_TITLE = ("placeholder", "place", "untitled", "unknown", "none", "null", "tbd", "na", "test", "newlaunch", "launch")


_TYPES = {"string": str, "boolean": bool, "array": list}


def _is_blank(value: str) -> bool:
    """Models sometimes fill a field they mean to leave out with a placeholder or stray markup."""
    v = value.strip()
    return not v or ("<" in v and ">" in v) or v.lower() in ("empty", "n/a", "null", "none", "unused", "unset", "placeholder")


def _checked(name: str, args: dict) -> dict:
    """Validate tool input against its schema and fill omitted keys. Strict mode
    already guarantees this where it is on; code never relies on it."""
    props = next(t for t in TOOLS if t["name"] == name)["input_schema"]["properties"]
    unknown = set(args) - set(props)
    if unknown:
        raise ToolError(f"Unknown fields: {sorted(unknown)}")
    out = {k: v for k, v in args.items() if not (isinstance(v, str) and _is_blank(v))}
    for key, spec in props.items():
        if key in out:
            if not isinstance(out[key], _TYPES[spec["type"]]):
                raise ToolError(f"{key} must be a {spec['type']}.")
            if "enum" in spec and out[key] not in spec["enum"]:
                raise ToolError(f"{key} must be one of {spec['enum']}.")
            if spec["type"] == "array":
                if not all(isinstance(i, str) for i in out[key]):
                    raise ToolError(f"{key} must be a list of record ids.")
                out[key] = [i for i in out[key] if not _is_blank(i)]      # ["null"] means "none"
            continue
        if spec["type"] == "boolean":
            out[key] = False
        elif spec["type"] == "array":
            out[key] = []
        elif "enum" in spec:
            out[key] = next((v for v in spec["enum"] if v in _NEUTRAL), spec["enum"][0])
        else:
            out[key] = ""
    return out


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        import json
        return json.dumps(value)
    return str(value)
