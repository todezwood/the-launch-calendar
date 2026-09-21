"""Which Slack messages the bot acts on. No network: Slack and the engine are faked."""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_SIGNING_SECRET", "test")

from adapters import slack_app  # noqa: E402


class FakeSlack:
    def __init__(self):
        self.said = []

    def users_info(self, user):
        return {"user": {"profile": {"display_name": {"U2": "Dana Whitfield"}.get(user, "Alex Kim")}}}

    def auth_test(self):
        return {"user_id": "UBOT"}

    def reactions_add(self, **_): pass
    def reactions_remove(self, **_): pass


@pytest.fixture
def slack(monkeypatch, tmp_path):
    from agent import engine
    heard = []

    def handle(text, *a, thread=""):
        heard.append((text, thread))
        if "boom" in text:
            raise RuntimeError("secret internals")
        receipt = "• GA date: Tue Sep 1 → Tue Sep 8" if "slip" in text.lower() else ""    # only a write has a receipt
        return engine.Reply(text=f"heard: {text}", receipt=receipt)

    monkeypatch.setattr(engine, "handle", handle)
    from store.json_store import JsonStore
    monkeypatch.setattr(slack_app, "_store", JsonStore(str(tmp_path / "calendar.json")))
    slack_app._seen.clear(), slack_app._recent.clear(), slack_app._names.clear()

    def send(event, client, via=slack_app.on_message):
        via(event, client, lambda **kw: client.said.append(kw) or {"ts": f"reply-{event['ts']}"})
        return client.said
    send.heard = heard
    return send


def test_a_channel_message_needs_no_mention_and_is_answered_in_a_thread(slack):
    said = slack({"channel": "C1", "ts": "1", "user": "U1", "text": "Dropbox connector"}, FakeSlack())
    assert said == [{"text": "heard: Dropbox connector", "thread_ts": "1"}]


def test_a_thread_reply_is_answered_in_the_same_thread(slack):
    said = slack({"channel": "C1", "ts": "2", "thread_ts": "1", "user": "U1", "text": "M"}, FakeSlack())
    assert said == [{"text": "heard: M", "thread_ts": "1"}]


def test_a_mention_fires_two_slack_events_but_gets_one_answer(slack):
    event, client = {"channel": "C1", "ts": "1", "user": "U1", "text": "<@UBOT> next tues"}, FakeSlack()
    slack(event, client)
    assert slack(event, client, via=slack_app.on_mention) == [{"text": "heard: next tues", "thread_ts": "1"}]


def test_a_dm_is_answered_inline_not_in_a_thread(slack):
    said = slack({"channel": "D1", "channel_type": "im", "ts": "1", "user": "U1", "text": "M"}, FakeSlack())
    assert said == [{"text": "heard: M", "thread_ts": None}]


def test_the_bots_own_messages_and_edits_are_never_answered(slack):
    assert slack({"channel": "C1", "ts": "3", "bot_id": "B1", "user": "UBOT", "text": "hi"}, FakeSlack()) == []
    assert slack({"channel": "C1", "ts": "4", "subtype": "message_changed", "user": "U1", "text": "hi"}, FakeSlack()) == []


def test_the_engine_is_told_which_thread_the_message_is_in(slack):
    slack({"channel": "C1", "ts": "2", "thread_ts": "1", "user": "U1", "text": "M"}, FakeSlack())
    slack({"channel": "D1", "channel_type": "im", "ts": "3", "user": "U1", "text": "M"}, FakeSlack())
    assert slack.heard == [("M", "C1:1"), ("M", "")]


def test_other_mentions_become_names_and_own_is_stripped(slack):
    slack({"channel": "C1", "ts": "1", "user": "U1", "text": "<@UBOT> <@U2|dana> owns Bulk export now"}, FakeSlack())
    assert slack.heard[0][0] == "@Dana Whitfield owns Bulk export now"


def test_error_reply_never_claims_nothing_was_saved_and_never_leaks_the_exception(slack):
    (said,) = slack({"channel": "C1", "ts": "1", "user": "U1", "text": "boom"}, FakeSlack())
    assert "may or may not have been saved" in said["text"] and "(ref " in said["text"]
    assert "nothing was saved" not in said["text"] and "secret internals" not in said["text"]


def test_a_failed_post_is_not_reported_as_a_failed_save(slack):
    def broken_say(**kw):
        raise ConnectionError("slack is down")
    slack_app.on_message({"channel": "C1", "ts": "1", "user": "U1", "text": "slip it a week"}, FakeSlack(), broken_say)
    assert [h[0] for h in slack.heard] == ["slip it a week"]       # handled once, no second "error" message attempted


def test_resend_of_a_write_is_caught_once_then_allowed(slack):
    client = FakeSlack()
    slack({"channel": "C1", "ts": "1", "user": "U1", "text": "Saved views is slipping a week"}, client)
    slack({"channel": "C1", "ts": "2", "user": "U1", "text": "saved views  is slipping a week."}, client)   # the resend
    slack({"channel": "C1", "ts": "3", "user": "U1", "text": "Saved views is slipping a week"}, client)     # they mean it
    assert len(slack.heard) == 2
    assert client.said[1]["text"].startswith("Already handled this a moment ago") and "Tue Sep 8" in client.said[1]["text"]


def test_a_resend_from_someone_else_or_after_the_window_is_handled_normally(slack, monkeypatch):
    client = FakeSlack()
    slack({"channel": "C1", "ts": "1", "user": "U1", "text": "slip it a week"}, client)
    slack({"channel": "C1", "ts": "2", "user": "U2", "text": "slip it a week"}, client)
    monkeypatch.setattr(slack_app, "RESEND_WINDOW", 0)
    slack({"channel": "C1", "ts": "3", "user": "U2", "text": "slip it a week"}, client)
    assert len(slack.heard) == 3


def test_repeated_question_is_answered_again(slack):
    client = FakeSlack()
    slack({"channel": "C1", "ts": "1", "user": "U1", "text": "what lands next week?"}, client)
    slack({"channel": "C1", "ts": "2", "user": "U1", "text": "what lands next week?"}, client)
    assert len(slack.heard) == 2


def test_every_handled_message_is_logged_without_its_text(slack):
    slack({"channel": "C1", "ts": "1", "user": "U1", "text": "Saved views is slipping a week"}, FakeSlack())
    (row,) = slack_app._store.events
    assert row["sender"] == "Alex Kim" and row["reply_ts"] == "reply-1" and row["seconds"] >= 0 and not row["error"]
    assert "slipping" not in str(row)


def test_thumbs_reaction_sets_rating_and_other_emoji_are_ignored(slack):
    slack({"channel": "C1", "ts": "1", "user": "U1", "text": "slip it a week"}, FakeSlack())
    react = lambda name, ts="reply-1", **kw: slack_app.on_reaction(
        {"reaction": name, "item": {"type": "message", "channel": "C1", "ts": ts}, **kw}, FakeSlack(), {"bot_user_id": "UBOT"})
    react("eyes"), react("-1", ts="someone-elses-message"), react("+1", item_user="U1")
    assert "rating" not in slack_app._store.events[0]
    react("+1::skin-tone-3", item_user="UBOT")
    assert slack_app._store.events[0]["rating"] == "up"
    react("thumbsdown")
    assert slack_app._store.events[0]["rating"] == "down"         # the last reaction wins


def test_logging_failure_never_fails_the_reply(slack, monkeypatch):
    def broken(event):
        raise ConnectionError("notion is down")
    monkeypatch.setattr(slack_app._store, "log_event", broken)
    said = slack({"channel": "C1", "ts": "1", "user": "U1", "text": "Dropbox connector"}, FakeSlack())
    assert said == [{"text": "heard: Dropbox connector", "thread_ts": "1"}]
