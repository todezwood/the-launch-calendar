"""NotionStore's field mapping, round-tripped through a fake Notion client. No token needed."""
import uuid

import pytest

from agent.schema import Change, Launch
from store import notion_store
from store.notion_store import PROPS, NotionStore


class FakeNotion:
    """Just enough of the Notion API: stores what was written, echoes it back the way Notion does."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.pages = self.data_sources = self

    def retrieve(self, data_source_id=None, page_id=None):
        if data_source_id:
            return {"properties": {PROPS["depends_on"][0]: {"type": "relation"}}}
        return self.rows[page_id]

    def create(self, parent, properties):
        page = {"id": str(uuid.uuid4()), "ds": parent["data_source_id"], "properties": {}}
        self.rows[page["id"]] = page
        return self.update(page["id"], properties)

    def update(self, page_id, properties):
        for name, value in properties.items():
            (kind, body), = value.items()
            if kind in ("title", "rich_text"):
                body = [{"plain_text": part["text"]["content"]} for part in body]
            self.rows[page_id]["properties"][name] = {"type": kind, kind: body}
        return self.rows[page_id]

    def query(self, data_source_id, **_):
        return {"results": [p for p in self.rows.values() if p["ds"] == data_source_id], "has_more": False}


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("NOTION_LAUNCHES_DS_ID", "launches")
    monkeypatch.setenv("NOTION_CHANGES_DS_ID", "changes")
    monkeypatch.setattr(notion_store, "client", FakeNotion)
    return NotionStore()


def test_every_field_survives_a_round_trip(store):
    upstream = store.save(Launch(title="Connectors platform", dri="Sam Okafor", status="In Development"))
    sent = Launch(title="Box connector", dri="Alex Kim", dri_id="U_ALEX", status="Limited Beta", release_size="M",
                  feature_brief="Sync Box folders", audience="10 design partners", ga_date=None, beta_date="2026-09-01",
                  date_confidence="tbd", date_note="GA after beta feedback", risk_level="at_risk", risk_note="upstream slip",
                  depends_on=[upstream.id], needs_dri_confirmation=True, pending_change="Jordan Lee: status → On Hold",
                  open_question="What size is this?", question_for="U_ALEX",
                  last_updated="2026-08-24T10:00:00-07:00", last_updated_by="Alex Kim")
    saved = store.save(sent)
    assert store.get(saved.id).to_dict() == sent.to_dict()
    assert {l.title for l in store.list()} == {"Connectors platform", "Box connector"}


def test_partial_update_writes_only_the_changed_fields(store):
    launch = store.save(Launch(title="Saved views", dri="Priya Raman", status="In Development", ga_date="2026-09-01"))
    launch.ga_date, launch.title = None, "SHOULD NOT BE WRITTEN"
    store.update(launch, {"ga_date"})
    fresh = store.get(launch.id)
    assert fresh.ga_date is None and fresh.title == "Saved views"


def test_change_log_rows_read_back_in_order_for_one_launch(store):
    store.add_change(Change("2026-08-24T10:00:00-07:00", "Priya Raman", "abc", "Saved views", "ga_date", "2026-09-01", "", "vendor"))
    (row,) = store.list_changes()
    assert (row.launch_title, row.field, row.old, row.new, row.actor) == ("Saved views", "ga_date", "2026-09-01", "", "Priya Raman")
