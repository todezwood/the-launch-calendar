"""engine.handle(message, sender, now) -> Reply

The whole agent behind one function. Adapters (CLI, Slack) and stores (JSON,
Notion) swap around it; this file does not know which ones are in use.
`now` is injected so fuzzy dates ("next tues") are testable.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime

from agent import prompts
from agent.schema import Sender
from agent.tools import TOOLS, Dispatcher
from store.base import Store

MODEL = os.environ.get("LAUNCH_AGENT_MODEL", "claude-sonnet-5")
MAX_TURNS = 6

_client = None


def _anthropic():
    # Imported lazily: the Slack ack path must stay fast on a cold start.
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(timeout=25.0, max_retries=1)
    return _client


@dataclass
class Reply:
    text: str
    actions: list[dict] = field(default_factory=list)   # what the tools actually did

    @property
    def tools_called(self) -> list[str]:
        return [a["tool"] for a in self.actions]


def handle(message: str, sender: Sender, now: datetime, store: Store, overheard: bool = False) -> Reply:
    """`overheard`: said in the channel, not to the bot. Launch news is still recorded; anything
    else gets an empty Reply, which the adapter posts as nothing at all."""
    dispatcher = Dispatcher(store, sender, now)
    messages = [{"role": "user", "content": prompts.context(message, sender, now, store.list(), overheard)}]
    text = ""

    for _ in range(MAX_TURNS):
        response = _anthropic().messages.create(
            model=MODEL,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=[{"type": "text", "text": prompts.SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=messages,
        )
        text = "\n".join(b.text for b in response.content if b.type == "text").strip()
        if response.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": [
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result := dispatcher.call(block.name, block.input), ensure_ascii=False),
                "is_error": not result.get("ok", True),
            }
            for block in response.content if block.type == "tool_use"
        ]})

    if overheard and prompts.NO_REPLY in text:
        # Staying quiet is only allowed when nothing was written; a silent write is never OK.
        text = "Noted on the calendar." if dispatcher.actions else ""
        return Reply(text=text, actions=dispatcher.actions)
    if not text:
        text = "I couldn't work that one out — could you rephrase it?"
    return Reply(text=text, actions=dispatcher.actions)
