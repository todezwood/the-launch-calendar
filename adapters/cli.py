"""Terminal adapter — run the agent locally without Slack.

  python -m adapters.cli --as "Alex Kim"             # chat with the agent
  python -m adapters.cli --as "Alex Kim" "Dropbox connector"
  python -m adapters.cli roadmap | risks | history    # read-only views, no model call

`--as` stands in for the Slack identity: it decides whether your update is
applied (you're the DRI) or held for confirmation (you're not).
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from agent import roadmap
from agent.schema import Sender
from store.base import Store

TZ = ZoneInfo(os.environ.get("LAUNCH_AGENT_TZ", "America/Los_Angeles"))


def load_env(path: str = ".env") -> None:
    """Tiny .env reader so local runs need no extra dependency."""
    if Path(path).exists():
        for raw in Path(path).read_text().splitlines():
            if "=" in raw and not raw.lstrip().startswith("#"):
                key, _, value = raw.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def open_store(backend: str | None = None) -> Store:
    backend = backend or os.environ.get("LAUNCH_STORE", "json")
    if backend == "notion":
        from store.notion_store import NotionStore
        return NotionStore()
    from store.json_store import JsonStore
    return JsonStore(os.environ.get("LAUNCH_JSON_PATH", "data/calendar.json"))


def sender_from(name: str) -> Sender:
    return Sender(id="U_" + name.split()[0].upper(), name=name)


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Hobbes, the Launch Calendar agent (local)")
    parser.add_argument("--as", dest="who", default=os.environ.get("USER", "someone").title(), help="who is speaking")
    parser.add_argument("--store", choices=["json", "notion"], default=None)
    parser.add_argument("message", nargs="*", help="a message, or: roadmap | risks | history")
    args = parser.parse_args()
    store = open_store(args.store)
    text = " ".join(args.message).strip()

    if text == "roadmap":
        return print(roadmap.render(store.list()))
    if text == "risks":
        return print(roadmap.render(store.list(), only_risky=True))
    if text == "history":
        for c in store.list_changes():
            print(f"{c.timestamp}  {c.actor:<28} {c.launch_title}: {c.field}  {c.old!r} -> {c.new!r}  {c.note}")
        return

    from agent import engine
    sender = sender_from(args.who)

    def say(message: str) -> None:
        reply = engine.handle(message, sender, datetime.now(TZ), store)
        print(f"\n🗓  {reply.text}\n")

    if text:
        return say(text)
    print(f"Hobbes, the Launch Calendar agent — speaking as {sender.name}. Ctrl-D to quit.")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            return
        if line:
            say(line)


if __name__ == "__main__":
    main()
