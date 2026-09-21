"""ONE-SHOT: create the "Agent Log" Notion database (one row per handled message) under the parent page.

    python -m scripts.provision_agent_log

Needs NOTION_TOKEN and NOTION_PARENT_PAGE_ID. Appends NOTION_AGENT_LOG_DS_ID to .env; without that variable
the agent simply does not log. The "Hobbes performance" views over it (totals by kind, error rate, average
seconds, thumbs-down rate, duplicates refused) are a few minutes by hand, like the roadmap board.
"""
import os
import sys
from pathlib import Path

from adapters.cli import load_env
from scripts.provision_notion import page_id
from store.notion_store import client

KINDS = [("create", "green"), ("update", "blue"), ("question", "purple"), ("clarify", "yellow"), ("other", "gray")]
PROPERTIES = {
    "Event": {"title": {}}, "When": {"date": {}}, "Sender": {"rich_text": {}},
    "Kind": {"select": {"options": [{"name": n, "color": c} for n, c in KINDS]}},
    "Writes": {"number": {}}, "Held": {"number": {}}, "Duplicates refused": {"number": {}},
    "Resend caught": {"checkbox": {}}, "Error": {"checkbox": {}}, "Ref": {"rich_text": {}}, "Seconds": {"number": {}},
    "Rating": {"select": {"options": [{"name": "up", "color": "green"}, {"name": "down", "color": "red"}]}},
    "Reply ts": {"rich_text": {}},
}


def main() -> None:
    load_env()
    if os.environ.get("NOTION_AGENT_LOG_DS_ID"):
        sys.exit("NOTION_AGENT_LOG_DS_ID is already set — this script is one-shot.")
    database = client().databases.create(
        parent={"type": "page_id", "page_id": page_id(os.environ["NOTION_PARENT_PAGE_ID"])},
        title=[{"type": "text", "text": {"content": "Hobbes performance — Agent Log"}}],
        initial_data_source={"properties": PROPERTIES})
    ds = database["data_sources"][0]["id"]
    with Path(".env").open("a") as env:
        env.write(f"\nNOTION_AGENT_LOG_DS_ID={ds}\n")
    print(f"Created. NOTION_AGENT_LOG_DS_ID={ds} (appended to .env)\n{database.get('url', '')}")


if __name__ == "__main__":
    main()
