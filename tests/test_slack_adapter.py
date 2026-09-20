"""Which Slack messages the bot acts on. No network: Slack and the engine are faked."""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_SIGNING_SECRET", "test")

from adapters import slack_app  # noqa: E402


class FakeSlack:
    def __init__(self, thread_authors=()):
        self.thread_authors, self.said = thread_authors, []

    def auth_test(self):
        return {"user_id": "U_BOT"}

    def conversations_replies(self, **_):
        return {"messages": [{"user": u} for u in self.thread_authors]}

    def users_info(self, user):
        return {"user": {"profile": {"display_name": "Alex Kim"}}}

    def reactions_add(self, **_): pass
    def reactions_remove(self, **_): pass


@pytest.fixture
def slack(monkeypatch):
    from agent import engine
    monkeypatch.setattr(engine, "handle", lambda text, *a: SimpleNamespace(text=f"heard: {text}", tools_called=[]))
    monkeypatch.setattr(slack_app, "_store", object())
    for seen in (slack_app._seen, slack_app._my_threads):
        seen.clear()

    def send(event, client):
        slack_app.on_message(event, client, lambda **kw: client.said.append(kw))
        return client.said
    return send


def test_channel_chatter_without_a_mention_is_ignored(slack):
    assert slack({"channel": "C1", "ts": "1", "user": "U1", "text": "lunch?"}, FakeSlack()) == []


def test_thread_reply_to_the_bot_needs_no_mention(slack):
    event = {"channel": "C1", "ts": "2", "thread_ts": "1", "user": "U1", "text": "M"}
    said = slack(event, FakeSlack(thread_authors=["U1", "U_BOT"]))
    assert said == [{"text": "heard: M", "thread_ts": "1"}]


def test_thread_reply_in_someone_elses_thread_is_ignored(slack):
    event = {"channel": "C1", "ts": "2", "thread_ts": "1", "user": "U1", "text": "M"}
    assert slack(event, FakeSlack(thread_authors=["U1", "U2"])) == []


def test_the_bots_own_messages_are_never_answered(slack):
    event = {"channel": "D1", "channel_type": "im", "ts": "3", "bot_id": "B1", "user": "U_BOT", "text": "hi"}
    assert slack(event, FakeSlack()) == []
