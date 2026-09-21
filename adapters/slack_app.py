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


RESEND_WINDOW = 120    # seconds
# Nobody guesses that a reaction is feedback, so every reply that saved something says so.
RATE_HINT = "_Did I get this right? React 👍 or 👎 on this message._"
_recent: dict[tuple, tuple[float, str]] = {}    # (user, channel, thread, text) -> (when, receipt) for messages that WROTE


def _resend_key(event: dict, text: str) -> tuple:
    # The raw thread_ts, not the reply thread: a top-level resend has a new ts every time.
    return (event["user"], event.get("channel", ""), event.get("thread_ts") or "",
            re.sub(r"\s+", " ", text).strip(" .!?").lower())


def _resent(key: tuple) -> str | None:
    """'No reply, so I sent it again' must not apply "slip it a week" twice. One-shot: a third send goes through."""
    when, receipt = _recent.pop(key, (0.0, ""))
    return receipt if time.monotonic() - when < RESEND_WINDOW else None


def _remember(key: tuple, receipt: str) -> None:
    now = time.monotonic()
    for old in [k for k, (when, _) in _recent.items() if now - when >= RESEND_WINDOW]:
        del _recent[old]
    while len(_recent) >= 200:
        del _recent[next(iter(_recent))]
    _recent[key] = (now, receipt)


def _bot_id(client) -> str:
    if "bot" not in _names:
        try:
            _names["bot"] = client.auth_test()["user_id"]
        except Exception:
            return ""
    return _names["bot"]


def _readable(text: str, client, bot: str) -> str:
    """The bot's own @mention is noise; anyone else's is a name the model needs ("<@U7> owns this now")."""
    def name(match: re.Match) -> str:
        return "" if match[1] == bot else "@" + _sender(client, match[1]).name
    return re.sub(r"\s+", " ", re.sub(r"<@([A-Z0-9]+)(?:\|[^>]*)?>", name, text)).strip()


def _handle(event: dict, client, say, bot_id: str | None = None) -> None:
    if event.get("bot_id") or event.get("subtype") or not event.get("user"):
        return                                  # loop guard: never answer bots, edits, joins
    if not _first_time(event):
        return
    _react(client, event, "eyes")
    started, ref, outcome, error, tools = time.time(), uuid.uuid4().hex[:8], "ok", "", []
    thread = event.get("thread_ts") or (event["ts"] if event.get("channel_type") != "im" else None)
    posted, sender, stats = None, event["user"], {"kind": "other"}
    try:
        with _work_lock:
            global _store
            from agent import engine            # lazy: keeps cold-start ack fast
            _store = _store or open_store()
            text = _readable(event.get("text", ""), client, bot_id or _bot_id(client))
            key = _resend_key(event, text)
            # Checked inside the lock: the resend arrives while the first copy is still being handled.
            already = _resent(key)
            if already:
                outcome = "resend_caught"
                posted = f"Already handled this a moment ago — here's what I saved:\n{already}\nIf you meant it again, send it once more."
            else:
                who = _sender(client, event["user"])
                reply = engine.handle(text, who, datetime.now(TZ), _store,
                                      thread=f"{event.get('channel', '')}:{thread}" if thread else "")
                tools, sender = reply.tools_called, who.name
                posted = reply.text + (f"\n{RATE_HINT}" if reply.receipt else "")
                outcomes = [a["outcome"] for a in reply.actions]
                stats = {"kind": reply.kind, "writes": sum(o in ("created", "updated") for o in outcomes),
                         "held": outcomes.count("held_for_dri"),
                         "dup_refused": sum(o in ("duplicate", "possible_duplicate") for o in outcomes)}
                if reply.receipt:
                    _remember(key, reply.receipt)
                if reply.error:
                    outcome, error = "partial", reply.error
    except Exception as err:
        outcome, error = "error", f"{type(err).__name__}: {err}"
        traceback.print_exc()
        # Never the exception text: replies and the change log are readable by others. And never "nothing
        # was saved": a failure after a write is still a write.
        posted = ("Something went wrong on my side. Your change may or may not have been saved — "
                  f"check the calendar before resending. (ref {ref})")
    reply_ts = ""
    try:
        reply_ts = (say(text=posted, thread_ts=thread) or {}).get("ts", "")
        _react(client, event, "x" if outcome == "error" else "white_check_mark", remove="eyes")
    except Exception as err:        # the work is done; a failed post must not be reported as a failed save
        outcome, error = "say_failed", f"{type(err).__name__}: {err}"
        traceback.print_exc()
    print(json.dumps({"severity": "ERROR" if error else "INFO", "ref": ref, "event_ts": event.get("ts"),
                      "user": event.get("user"), "latency_ms": int((time.time() - started) * 1000),
                      "tools_called": tools, "outcome": outcome, "error": error}), flush=True)
    try:    # after the reply, so logging adds no wait — and a failure to log is never a failure to answer
        _store and _store.log_event({**stats, "when": datetime.now(TZ).isoformat(timespec="seconds"), "sender": sender,
                                     "resend": outcome == "resend_caught", "error": bool(error), "ref": ref,
                                     "seconds": round(time.time() - started, 1), "reply_ts": reply_ts})
    except Exception:
        traceback.print_exc()


@app.event("app_mention")
def on_mention(event, client, say, context=None):
    _handle(event, client, say, (context or {}).get("bot_user_id"))


@app.event("message")
def on_message(event, client, say, context=None):
    if event.get("bot_id") or event.get("subtype"):
        return
    # Every message in the launches channel (and every DM) is for the bot: nobody has to remember the @.
    _handle(event, client, say, (context or {}).get("bot_user_id"))


_RATINGS = {"+1": "up", "thumbsup": "up", "-1": "down", "thumbsdown": "down"}


@app.event("reaction_added")
def on_reaction(event, client, context=None):
    """👍 / 👎 on one of the bot's replies is the person agreeing or disagreeing with it. Last one wins;
    a removed reaction is ignored; any other emoji is ignored."""
    try:
        rating = _RATINGS.get(event.get("reaction", "").split("::")[0])       # "+1::skin-tone-3" is still a 👍
        item, bot = event.get("item", {}), (context or {}).get("bot_user_id") or _bot_id(client)
        if not rating or item.get("type") != "message" or (event.get("item_user") and event["item_user"] != bot):
            return
        global _store
        _store = _store or open_store()
        _store.set_rating(item.get("ts", ""), rating)
    except Exception:
        traceback.print_exc()
