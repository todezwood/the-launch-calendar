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
        return {"user_id": "UBOT"}

    def conversations_replies(self, **_):
        return {"messages": [{"user": u} for u in self.thread_authors]}

    def users_info(self, user):
        return {"user": {"profile": {"display_name": "Alex Kim"}}}

    def reactions_add(self, **_): pass
    def reactions_remove(self, **_): pass


@pytest.fixture
def slack(monkeypatch):
    from agent import engine
    def handle(text, *a, overheard=False):
        # Stand-in for the model: overheard chatter gets an empty reply, everything else is answered.
        quiet = overheard and text == "lunch?"
        return SimpleNamespace(text="" if quiet else f"heard{' (overheard)' if overheard else ''}: {text}", tools_called=[])
    monkeypatch.setattr(engine, "handle", handle)
    monkeypatch.setattr(slack_app, "_store", object())
    for seen in (slack_app._seen, slack_app._my_threads):
        seen.clear()

    def send(event, client):
        slack_app.on_message(event, client, lambda **kw: client.said.append(kw))
        return client.said
    return send


def test_channel_chatter_is_heard_but_gets_no_reply(slack):
    assert slack({"channel": "C1", "ts": "1", "user": "U1", "text": "lunch?"}, FakeSlack()) == []


def test_launch_news_in_the_channel_needs_no_mention_and_is_answered_in_a_thread(slack):
    said = slack({"channel": "C1", "ts": "1", "user": "U1", "text": "Dropbox connector"}, FakeSlack())
    assert said == [{"text": "heard (overheard): Dropbox connector", "thread_ts": "1"}]


def test_a_mention_is_addressed_not_overheard(slack):
    said = slack({"channel": "C1", "ts": "1", "user": "U1", "text": "<@UBOT> lunch?"}, FakeSlack())
    assert said == [{"text": "heard: lunch?", "thread_ts": "1"}]


def test_thread_reply_to_the_bot_needs_no_mention(slack):
    event = {"channel": "C1", "ts": "2", "thread_ts": "1", "user": "U1", "text": "M"}
    said = slack(event, FakeSlack(thread_authors=["U1", "UBOT"]))
    assert said == [{"text": "heard: M", "thread_ts": "1"}]


def test_thread_reply_in_someone_elses_thread_is_only_overheard(slack):
    event = {"channel": "C1", "ts": "2", "thread_ts": "1", "user": "U1", "text": "M"}
    assert slack(event, FakeSlack(thread_authors=["U1", "U2"])) == [{"text": "heard (overheard): M", "thread_ts": "1"}]


def test_the_bots_own_messages_are_never_answered(slack):
    event = {"channel": "D1", "channel_type": "im", "ts": "3", "bot_id": "B1", "user": "UBOT", "text": "hi"}
    assert slack(event, FakeSlack()) == []
