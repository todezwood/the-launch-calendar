"""Slack adapter — thin. Events API over HTTP (not Socket Mode: Cloud Run
scales to zero). Bolt verifies the request signature and acks within 3s; the
listener below then runs on Bolt's worker thread.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import traceback
import uuid
from datetime import datetime

from slack_bolt import App

from adapters.cli import TZ, open_store
from agent.schema import Sender

# No auth.test call at boot: a cold start should spend its 3 seconds acking Slack, and a
# bad token should fail one reply, not crash-loop the container.
app = App(token=os.environ.get("SLACK_BOT_TOKEN"), signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
          token_verification_enabled=False)

_seen: set[tuple[str, str]] = set()     # authoritative because the service runs --max-instances 1
_seen_lock = threading.Lock()
_work_lock = threading.Lock()           # one message at a time: last-write-wins stays readable
_names: dict[str, str] = {}
_store = None


def _first_time(event: dict) -> bool:
    # Keyed on (channel, ts), not event_id: a DM that @mentions the bot fires BOTH
    # message.im and app_mention — two event ids, one message.
    key = (event.get("channel", ""), event.get("ts", ""))
    with _seen_lock:
        if key in _seen:
            return False
        _seen.add(key)
        return True


def _sender(client, user_id: str) -> Sender:
    if user_id not in _names:
        try:
            profile = client.users_info(user=user_id)["user"]
            _names[user_id] = profile["profile"].get("display_name") or profile.get("real_name") or user_id
        except Exception:
            _names[user_id] = user_id
    return Sender(id=user_id, name=_names[user_id])


def _react(client, event: dict, add: str, remove: str | None = None) -> None:
    try:
        if remove:
            client.reactions_remove(channel=event["channel"], timestamp=event["ts"], name=remove)
        client.reactions_add(channel=event["channel"], timestamp=event["ts"], name=add)
    except Exception:
        pass   # a reaction is a nicety, never a reason to fail


def _handle(event: dict, client, say) -> None:
    if event.get("bot_id") or event.get("subtype") or not event.get("user"):
        return                                  # loop guard: never answer bots, edits, joins
    if not _first_time(event):
        return
    _react(client, event, "eyes")
    started, ref, outcome, error, tools = time.time(), uuid.uuid4().hex[:8], "ok", "", []
    thread = event.get("thread_ts") or (event["ts"] if event.get("channel_type") != "im" else None)
    try:
        with _work_lock:
            global _store
            from agent import engine            # lazy: keeps cold-start ack fast
            _store = _store or open_store()
            text = re.sub(r"<@[A-Z0-9]+>", "", event.get("text", "")).strip()
            reply = engine.handle(text, _sender(client, event["user"]), datetime.now(TZ), _store)
            tools = reply.tools_called
        say(text=reply.text, thread_ts=thread)
        _react(client, event, "white_check_mark", remove="eyes")
    except Exception as err:
        outcome, error = "error", f"{type(err).__name__}: {err}"
        traceback.print_exc()
        # Never the exception text: replies and the change log are readable by others.
        say(text=f"Something went wrong on my side and nothing was saved — please send that again. (ref {ref})", thread_ts=thread)
        _react(client, event, "x", remove="eyes")
    print(json.dumps({"severity": "ERROR" if error else "INFO", "ref": ref, "event_ts": event.get("ts"),
                      "user": event.get("user"), "latency_ms": int((time.time() - started) * 1000),
                      "tools_called": tools, "outcome": outcome, "error": error}), flush=True)


@app.event("app_mention")
def on_mention(event, client, say):
    _handle(event, client, say)


@app.event("message")
def on_message(event, client, say):
    if event.get("channel_type") == "im":
        _handle(event, client, say)
