"""Local JSON backend — dev and the test suite only. Never live alongside
Notion, so there is nothing to drift."""
from __future__ import annotations

import json
from pathlib import Path

from agent.schema import Change, Launch
from store.base import Store


class JsonStore(Store):
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if self.path.exists():
            data = json.loads(self.path.read_text())
        else:
            data = {"launches": [], "changes": []}
        self._launches = {d["id"]: Launch.from_dict(d) for d in data["launches"]}
        self._changes = [Change(**c) for c in data["changes"]]

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "launches": [l.to_dict() for l in self._launches.values()],
            "changes": [c.to_dict() for c in self._changes],
        }, indent=2))

    def _slug(self, title: str) -> str:
        base = "-".join("".join(c.lower() if c.isalnum() else " " for c in title).split())[:48] or "launch"
        slug, n = base, 2
        while slug in self._launches:
            slug, n = f"{base}-{n}", n + 1
        return slug

    def save(self, launch: Launch) -> Launch:
        launch.id = self._slug(launch.title)
        self._launches[launch.id] = launch
        self._flush()
        return launch

    def get(self, launch_id: str) -> Launch | None:
        return self._launches.get(launch_id)

    def update(self, launch: Launch, changed: set[str] | None = None) -> Launch:
        self._launches[launch.id] = launch
        self._flush()
        return launch

    def list(self) -> list[Launch]:
        return list(self._launches.values())

    def add_change(self, change: Change) -> None:
        self._changes.append(change)
        self._flush()

    def list_changes(self, launch_id: str | None = None) -> list[Change]:
        return [c for c in self._changes if launch_id is None or c.launch_id == launch_id]
