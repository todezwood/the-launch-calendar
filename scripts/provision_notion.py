"""ONE-SHOT: create the two Notion databases under a parent page and print their ids.

  NOTION_TOKEN=... NOTION_PARENT_PAGE_ID=<page link or id> python -m scripts.provision_notion

Share the parent page with the integration first. Not idempotent on purpose —
it refuses to run if the ids are already in the environment. The Roadmap board
view is ~90 seconds by hand afterwards: Board layout, group by Status, sort by
GA date (documented in the README).
"""
import os
import re
import sys

from adapters.cli import load_env
from agent.schema import DATE_CONFIDENCE, RELEASE_SIZES, RISK_LEVELS, STATUSES
from store.notion_store import DEPENDS_TEXT, PROPS, client

COLORS = {"Planned": "gray", "In Development": "blue", "Internal": "purple", "Limited Beta": "yellow",
          "Open Beta": "orange", "GA": "green", "On Hold": "red", "Cancelled": "brown",
          "on_track": "green", "at_risk": "yellow", "slipped": "red",
          "committed": "green", "target": "yellow", "tbd": "gray"}
OPTIONS = {"status": STATUSES, "release_size": RELEASE_SIZES, "date_confidence": DATE_CONFIDENCE, "risk_level": RISK_LEVELS}


def select(values):
    return {"select": {"options": [{"name": v, "color": COLORS.get(v, "default")} for v in values]}}


def page_id(value: str) -> str:
    """Accepts a bare id or a pasted page link (the id is the last 32 hex characters of the path)."""
    found = re.findall(r"[0-9a-f]{32}", value.split("?")[0].replace("-", "").lower())
    if not found:
        sys.exit("NOTION_PARENT_PAGE_ID should be the page link or its 32-character id.")
    return found[-1]


def main() -> None:
    load_env()
    if os.environ.get("NOTION_LAUNCHES_DS_ID"):
        sys.exit("NOTION_LAUNCHES_DS_ID is already set — this script is one-shot.")
    notion, parent = client(), {"type": "page_id", "page_id": page_id(os.environ["NOTION_PARENT_PAGE_ID"])}

    props = {}
    for key, (name, kind) in PROPS.items():
        if kind == "relation":
            continue                       # self-relation needs the data source id; added below
        props[name] = select(OPTIONS[key]) if kind == "select" else {kind: {}}
    launches = notion.databases.create(
        parent=parent, title=[{"type": "text", "text": {"content": "Launch Calendar"}}],
        initial_data_source={"properties": props})
    launches_ds = launches["data_sources"][0]["id"]

    changes = notion.databases.create(
        parent=parent, title=[{"type": "text", "text": {"content": "Launch Change Log"}}],
        initial_data_source={"properties": {
            "Change": {"title": {}}, "When": {"date": {}}, "Actor": {"rich_text": {}}, "Field": {"select": {}},
            "Old": {"rich_text": {}}, "New": {"rich_text": {}}, "Note": {"rich_text": {}}, "Launch id": {"rich_text": {}},
        }})
    changes_ds = changes["data_sources"][0]["id"]

    try:
        relation = {"relation": {"data_source_id": launches_ds, "type": "single_property", "single_property": {}}}
        notion.data_sources.update(data_source_id=launches_ds, properties={PROPS["depends_on"][0]: relation})
        notion.data_sources.update(data_source_id=changes_ds, properties={"Launch": relation})
        mode = "relation"
    except Exception as err:   # timeboxed fallback: readers see "Blocked by: X" either way
        print(f"Relation setup failed ({err}); falling back to a text column.")
        notion.data_sources.update(data_source_id=launches_ds, properties={DEPENDS_TEXT: {"rich_text": {}}})
        mode = "text"

    print(f"\nDependencies stored as: {mode}\nAdd to .env / Secret Manager:\n")
    print(f"NOTION_LAUNCHES_DS_ID={launches_ds}\nNOTION_CHANGES_DS_ID={changes_ds}")
    print(f"\nLaunch Calendar: {launches.get('url')}\nChange Log:      {changes.get('url')}")


if __name__ == "__main__":
    main()
