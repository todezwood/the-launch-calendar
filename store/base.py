"""Store interface. The engine only ever talks to this — Notion is the live
backend, local JSON is the dev/test backend, and a Linear/Jira/Postgres backend
is one more subclass."""
from __future__ import annotations

from abc import ABC, abstractmethod

from agent.schema import Change, Launch


class Store(ABC):
    @abstractmethod
    def save(self, launch: Launch) -> Launch:
        """Create a new record; returns it with `id` assigned."""

    @abstractmethod
    def get(self, launch_id: str) -> Launch | None: ...

    @abstractmethod
    def update(self, launch: Launch, changed: set[str] | None = None) -> Launch:
        """Persist an existing record. `changed` names the fields that moved,
        so remote backends can send a minimal patch."""

    @abstractmethod
    def list(self) -> list[Launch]: ...

    @abstractmethod
    def add_change(self, change: Change) -> None: ...

    @abstractmethod
    def list_changes(self, launch_id: str | None = None) -> list[Change]: ...

    # The agent log: one row per handled message, for the performance page. Optional — a store
    # without one simply does not log. Never message text: the Notion page is public.
    def log_event(self, event: dict) -> None:
        return None

    def set_rating(self, reply_ts: str, rating: str) -> bool:
        """Record a 👍/👎 on the reply posted at `reply_ts`. False if that reply is not in the log."""
        return False

    def find(self, text: str) -> list[Launch]:
        """Loose title match, used by the duplicate guard."""
        want = _tokens(text)
        if not want:
            return []
        hits = []
        for launch in self.list():
            have = _tokens(launch.title)
            if not have:
                continue
            overlap = len(want & have) / min(len(want), len(have))
            if overlap >= 0.67:
                hits.append(launch)
        return hits


_STOP = {"the", "a", "an", "for", "of", "in", "to", "and", "support", "new", "v2"}


def _tokens(text: str) -> set[str]:
    cleaned = "".join(c.lower() if c.isalnum() else " " for c in text)
    return {t for t in cleaned.split() if t not in _STOP}
