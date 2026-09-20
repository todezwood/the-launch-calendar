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
        return {"user": {"profile": {"display_name": "Alex Kim"}}}

    def reactions_add(self, **_): pass
    def reactions_remove(self, **_): pass


@pytest.fixture
def slack(monkeypatch):
    from agent import engine
    monkeypatch.setattr(engine, "handle", lambda text, *a: SimpleNamespace(text=f"heard: {text}", tools_called=[]))
    monkeypatch.setattr(slack_app, "_store", object())
    slack_app._seen.clear()

    def send(event, client, via=slack_app.on_message):
        via(event, client, lambda **kw: client.said.append(kw))
        return client.said
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
