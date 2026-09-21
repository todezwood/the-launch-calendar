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

from agent import prompts, receipt
from agent.schema import Sender
from agent.tools import TOOLS, Dispatcher
from store.base import Store

MODEL = os.environ.get("LAUNCH_AGENT_MODEL", "claude-sonnet-5")
MAX_TURNS = 8   # bounds one message: at most 7 tool calls and a closing reply

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
    text: str                                            # what gets posted: the model's prose, then the receipt
    actions: list[dict] = field(default_factory=list)   # what the tools actually did
    prose: str = ""                                      # the model's words alone
    receipt: str = ""                                    # code-made: what was saved, held, not done ("" if no write)
    changes: list[dict] = field(default_factory=list)   # the change-log rows this message wrote
    error: str = ""                                      # set when the model call failed after something was saved

    @property
    def tools_called(self) -> list[str]:
        return [a["tool"] for a in self.actions]

    @property
    def kind(self) -> str:
        outcomes = {a["outcome"] for a in self.actions}
        if "created" in outcomes:
            return "create"
        if outcomes & {"updated", "held_for_dri"}:
            return "update"
        if "queried" in outcomes:
            return "question"
        return "clarify" if "?" in self.prose else "other"


def handle(message: str, sender: Sender, now: datetime, store: Store, thread: str = "") -> Reply:
    dispatcher = Dispatcher(store, sender, now, thread)
    messages = [{"role": "user", "content": prompts.context(message, sender, now, store.list(), thread)}]
    text, error, exhausted = "", "", False

    try:
        for _ in range(MAX_TURNS):
            response = _anthropic().messages.create(
                model=MODEL,
                max_tokens=8000,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                system=[{"type": "text", "text": prompts.SYSTEM, "cache_control": {"type": "ephemeral"}}],
                tools=TOOLS,
                # One tool call per turn: the junk records seen in live runs were all garbled *parallel* calls.
                tool_choice={"type": "auto", "disable_parallel_tool_use": True},
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
        else:
            exhausted = True   # the last turn was still a tool call: its write landed, the model never summed up
    except Exception as err:
        if not dispatcher.changes:
            raise
        # Something was already saved. Saying "nothing was saved" would be a lie: show exactly what landed.
        text, error = "I hit an error partway — here is what did get saved:", f"{type(err).__name__}: {err}"

    if not text or (exhausted and dispatcher.changes):
        text = "Done — details below." if dispatcher.changes else "I couldn't work that one out — could you rephrase it?"
    made = receipt.build(dispatcher.changes, dispatcher.actions, store, now, exhausted)
    return Reply(text=f"{text}\n\n{made}" if made else text, actions=dispatcher.actions, prose=text, receipt=made,
                 changes=[c.to_dict() for c in dispatcher.changes], error=error)
