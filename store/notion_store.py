"""Notion backend — the live calendar. Notion is the database AND the display:
one source of truth, nothing to sync. Two data sources: Launches and Change Log
(created by scripts/provision_notion.py).

At 100x the volume you'd promote a real database and demote Notion to a
mirror; at this scale one source of truth beats API purity.
"""
from __future__ import annotations

import os

from agent.schema import Change, Launch
from store.base import Store

NOTION_VERSION = "2026-03-11"

# Launch field -> (Notion property name, property type)
PROPS = {
    "title": ("Launch", "title"),
    "status": ("Status", "select"),
    "dri": ("DRI", "rich_text"),
    "ga_date": ("GA date", "date"),
    "beta_date": ("Beta date", "date"),
    "date_confidence": ("Date confidence", "select"),
    "release_size": ("Release size", "select"),
    "risk_level": ("Risk", "select"),
    "risk_note": ("Risk note", "rich_text"),
    "feature_brief": ("Feature brief", "rich_text"),
    "audience": ("Audience / rollout", "rich_text"),
    "date_note": ("Date note", "rich_text"),
    "depends_on": ("Depends on", "relation"),
    "needs_dri_confirmation": ("Needs DRI confirmation", "checkbox"),
    "pending_change": ("Pending change", "rich_text"),
    "open_question": ("Open question", "rich_text"),
    "question_for": ("Question for", "rich_text"),
    "dri_id": ("DRI chat id", "rich_text"),
    "last_updated": ("Last updated", "date"),
    "last_updated_by": ("Last updated by", "rich_text"),
}
DEPENDS_TEXT = "Blocked by"   # fallback when the self-relation could not be provisioned


def client():
    from notion_client import Client
    return Client(auth=os.environ["NOTION_TOKEN"], notion_version=NOTION_VERSION)


def _rt(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": (text or "")[:2000]}}]


def _plain(prop: dict) -> str:
    return "".join(part.get("plain_text", "") for part in prop.get(prop["type"], []))


class NotionStore(Store):
    def __init__(self):
        self.notion = client()
        self.launches_ds = os.environ["NOTION_LAUNCHES_DS_ID"]
        self.changes_ds = os.environ["NOTION_CHANGES_DS_ID"]
        schema = self.notion.data_sources.retrieve(data_source_id=self.launches_ds)["properties"]
        self.relation_mode = schema.get(PROPS["depends_on"][0], {}).get("type") == "relation"

    # -- mapping ----------------------------------------------------------
    def _to_props(self, launch: Launch, only: set[str] | None = None) -> dict:
        out = {}
        for key, (name, kind) in PROPS.items():
            if key == "id" or (only is not None and key not in only):
                continue
            value = getattr(launch, key)
            if kind == "title":
                out[name] = {"title": _rt(value)}
            elif kind == "rich_text":
                out[name] = {"rich_text": _rt(value)}
            elif kind == "select":
                out[name] = {"select": {"name": value} if value else None}
            elif kind == "date":
                out[name] = {"date": {"start": value} if value else None}
            elif kind == "checkbox":
                out[name] = {"checkbox": bool(value)}
            elif kind == "relation":
                if self.relation_mode:
                    out[name] = {"relation": [{"id": i} for i in value]}
                else:
                    titles = [l.title for i in value if (l := self.get(i))]
                    out = {**out, DEPENDS_TEXT: {"rich_text": _rt(", ".join(titles))}}
        return out

    def _from_page(self, page: dict, titles: dict[str, str] | None = None) -> Launch:
        p = page["properties"]
        data = {"id": page["id"]}
        for key, (name, kind) in PROPS.items():
            prop = p.get(name)
            if prop is None:
                continue
            if kind in ("title", "rich_text"):
                data[key] = _plain(prop)
            elif kind == "select":
                data[key] = (prop["select"] or {}).get("name", "")
            elif kind == "date":
                data[key] = (prop["date"] or {}).get("start")
            elif kind == "checkbox":
                data[key] = prop["checkbox"]
            elif kind == "relation" and prop["type"] == "relation":
                data[key] = [r["id"] for r in prop["relation"]]
        if not self.relation_mode and titles and DEPENDS_TEXT in p:
            wanted = [t.strip() for t in _plain(p[DEPENDS_TEXT]).split(",") if t.strip()]
            data["depends_on"] = [i for i, t in titles.items() if t in wanted]
        data["last_updated"] = data.get("last_updated") or ""
        return Launch.from_dict(data)

    def _query(self, ds: str, **body) -> list[dict]:
        pages, cursor = [], None
        while True:
            res = self.notion.data_sources.query(data_source_id=ds, page_size=100,
                                                 **({"start_cursor": cursor} if cursor else {}), **body)
            pages += res["results"]
            cursor = res.get("next_cursor")
            if not res.get("has_more"):
                return [p for p in pages if not p.get("in_trash") and not p.get("archived")]

    # -- Store interface --------------------------------------------------
    def save(self, launch: Launch) -> Launch:
        page = self.notion.pages.create(
            parent={"type": "data_source_id", "data_source_id": self.launches_ds},
            properties=self._to_props(launch),
        )
        launch.id = page["id"]
        return launch

    def get(self, launch_id: str) -> Launch | None:
        from notion_client import APIResponseError
        try:
            page = self.notion.pages.retrieve(page_id=launch_id)
        except APIResponseError:
            return None
        if page.get("in_trash") or page.get("archived"):
            return None
        return self._from_page(page, None if self.relation_mode else self._titles())

    def update(self, launch: Launch, changed: set[str] | None = None) -> Launch:
        self.notion.pages.update(page_id=launch.id, properties=self._to_props(launch, changed))
        return launch

    def list(self) -> list[Launch]:
        pages = self._query(self.launches_ds)
        titles = {p["id"]: _plain(p["properties"][PROPS["title"][0]]) for p in pages}
        return [self._from_page(p, titles) for p in pages]

    def _titles(self) -> dict[str, str]:
        return {p["id"]: _plain(p["properties"][PROPS["title"][0]]) for p in self._query(self.launches_ds)}

    # No raw source-message column on purpose: this page is published to the web.
    def add_change(self, change: Change) -> None:
        props = {
            "Change": {"title": _rt(f"{change.launch_title}: {change.field}")},
            "When": {"date": {"start": change.timestamp}},
            "Actor": {"rich_text": _rt(change.actor)},
            "Field": {"select": {"name": change.field}},
            "Old": {"rich_text": _rt(change.old)},
            "New": {"rich_text": _rt(change.new)},
            "Note": {"rich_text": _rt(change.note)},
            "Launch id": {"rich_text": _rt(change.launch_id)},
        }
        if self.relation_mode:
            props["Launch"] = {"relation": [{"id": change.launch_id}]}
        self.notion.pages.create(parent={"type": "data_source_id", "data_source_id": self.changes_ds}, properties=props)

    def list_changes(self, launch_id: str | None = None) -> list[Change]:
        body = {"sorts": [{"property": "When", "direction": "ascending"}]}
        if launch_id:
            body["filter"] = {"property": "Launch id", "rich_text": {"equals": launch_id}}
        rows = []
        for page in self._query(self.changes_ds, **body):
            p = page["properties"]
            title = _plain(p["Change"])
            rows.append(Change(
                timestamp=(p["When"]["date"] or {}).get("start", ""), actor=_plain(p["Actor"]),
                launch_id=_plain(p["Launch id"]), launch_title=title.rsplit(":", 1)[0],
                field=(p["Field"]["select"] or {}).get("name", ""), old=_plain(p["Old"]), new=_plain(p["New"]),
                note=_plain(p["Note"]),
            ))
        return rows
