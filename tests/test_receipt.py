"""The receipt is made by code from what was actually written. No API key needed."""
from types import SimpleNamespace

import pytest

from agent import engine, prompts, receipt
from agent.tools import Dispatcher, compact
from tests.conftest import ALEX, JORDAN, NOW, SAM


def update(d, record_id, **changes):
    return d.call("update_record", {"record_id": record_id, **changes})


def built(d, store, **kw):
    return receipt.build(d.changes, d.actions, store, NOW, **kw)


def test_receipt_lists_exactly_the_changes_with_labels_and_real_dates(store):
    d = Dispatcher(store, SAM, NOW)
    update(d, "connectors-platform", ga_date="2026-09-04", release_size="M")
    text = built(d, store)
    assert "*Saved* · *Connectors Platform*" in text
    assert "• GA date: Fri Aug 28 → Fri Sep 4" in text and "2026-09-04" not in text
    assert "• Size: L → M" in text and text.endswith(receipt.CLOSING)
    assert "Not done" not in text and "please check" not in text


def test_held_change_is_shown_as_not_applied(store):
    d = Dispatcher(store, JORDAN, NOW)
    update(d, "bulk-export", status="On Hold")
    text = built(d, store)
    assert "*Held for Dana Whitfield — not applied* · *Bulk export*" in text and "• Status → On Hold" in text
    assert "*Saved*" not in text


def test_auto_risk_and_downstream_rows_are_marked(store):
    d = Dispatcher(store, SAM, NOW)
    d.call("create_record", {"title": "Box connector", "status": "In Development", "depends_on": ["connectors-platform"],
                             "release_size": "M", "date_confidence": "tbd", "risk_level": "on_track"})
    text = built(Dispatcher(store, SAM, NOW), store)
    assert text == ""                                   # a fresh dispatcher wrote nothing
    d2 = Dispatcher(store, SAM, NOW)
    update(d2, "connectors-platform", ga_date="2026-09-04")
    text = built(d2, store)
    assert "• Risk: on track → slipped (auto)" in text
    assert "*Also flagged* · *Box connector*" in text and "• Risk: on track → at risk (auto)" in text


def test_failure_after_last_write_is_listed_as_not_done_but_a_recovered_one_is_not(store):
    d = Dispatcher(store, SAM, NOW)
    update(d, "no-such-record", status="GA")                        # fails, then the model recovers...
    update(d, "connectors-platform", status="Limited Beta")         # ...with a write
    assert "Not done" not in built(d, store)
    d.call("create_record", {"title": "Connectors Platform", "status": "Planned"})   # fails after the last write
    text = built(d, store)
    assert "*Not done*" in text and "• Connectors Platform: This record already exists" in text


def test_readback_mismatch_is_reported(store):
    d = Dispatcher(store, SAM, NOW)
    update(d, "connectors-platform", status="Limited Beta")

    class Tampered:
        def get(self, launch_id):
            launch = store.get(launch_id)
            return type(launch).from_dict({**launch.to_dict(), "status": "Planned"})

    assert "• Status: Internal → Limited Beta — calendar shows Planned, please check" in built(d, Tampered())


def test_record_that_cannot_be_reread_says_so(store):
    d = Dispatcher(store, SAM, NOW)
    update(d, "connectors-platform", status="Limited Beta")

    class Down:
        def get(self, launch_id):
            raise RuntimeError("notion is down")

    assert "(couldn't re-read to verify)" in built(d, Down())


def test_no_write_no_receipt(store):
    d = Dispatcher(store, SAM, NOW)
    d.call("query_records", {"view": "list"})
    update(d, "connectors-platform", status="Internal")      # no_change
    assert built(d, store) == ""


# -- engine level: a scripted model ----------------------------------------------------------------

def _tool_use(n, record_id, **changes):
    return SimpleNamespace(stop_reason="tool_use", content=[
        SimpleNamespace(type="tool_use", id=f"t{n}", name="update_record", input={"record_id": record_id, **changes})])


def _scripted(monkeypatch, responses):
    calls = iter(responses)

    def create(**kw):
        step = next(calls)
        if isinstance(step, Exception):
            raise step
        return step

    monkeypatch.setattr(engine, "_anthropic", lambda: SimpleNamespace(messages=SimpleNamespace(create=create)))


def test_turn_limit_still_returns_a_receipt(store, monkeypatch):
    sizes = ["S", "M", "L"]
    _scripted(monkeypatch, [_tool_use(n, "connectors-platform", release_size=sizes[n % 3]) for n in range(engine.MAX_TURNS)])
    reply = engine.handle("resize it a lot", SAM, NOW, store)
    assert reply.prose == "Done — details below." and "ran out of steps" in reply.receipt
    assert reply.text.endswith(receipt.CLOSING) and reply.kind == "update"


def test_api_error_after_a_write_returns_the_receipt(store, monkeypatch):
    _scripted(monkeypatch, [_tool_use(0, "connectors-platform", status="Limited Beta"), TimeoutError("model timed out")])
    reply = engine.handle("platform is in limited beta", SAM, NOW, store)
    assert "here is what did get saved" in reply.prose and "• Status: Internal → Limited Beta" in reply.receipt
    assert reply.error.startswith("TimeoutError")


def test_api_error_before_any_write_is_raised(store, monkeypatch):
    _scripted(monkeypatch, [TimeoutError("model timed out")])
    with pytest.raises(TimeoutError):
        engine.handle("platform is in limited beta", SAM, NOW, store)


# -- thread-aware context ---------------------------------------------------------------------------

def _two_open_questions(store):
    Dispatcher(store, ALEX, NOW, "C1:100.1").call("create_record", {
        "title": "Dropbox connector", "status": "Planned", "open_question": "When is GA, and is it S, M or L?"})
    Dispatcher(store, ALEX, NOW, "C1:200.2").call("create_record", {
        "title": "Audit log export", "status": "Planned", "open_question": "When is GA, and is it S, M or L?"})


def test_context_shows_only_the_threads_open_question(store):
    _two_open_questions(store)
    older = prompts.context("M", ALEX, NOW, store.list(), "C1:100.1")
    assert "- [dropbox-connector]" in older and "- [audit-log-export]" not in older
    assert "reply in the thread about [dropbox-connector] Dropbox connector" in older
    anywhere = prompts.context("M", ALEX, NOW, store.list())
    assert anywhere.index("- [audit-log-export]") < anywhere.index("- [dropbox-connector]")   # no thread: newest first


def test_thread_with_no_open_question_still_names_its_record(store):
    update(Dispatcher(store, SAM, NOW, "C1:300.3"), "connectors-platform", status="Limited Beta")
    text = prompts.context("make it L", SAM, NOW, store.list(), "C1:300.3")
    assert "reply in the thread about [connectors-platform]" in text and "- none" in text


def test_create_update_and_hold_stamp_the_thread_and_compact_hides_it(store):
    _two_open_questions(store)
    assert store.get("dropbox-connector").thread == "C1:100.1"
    update(Dispatcher(store, ALEX, NOW, "C1:900.9"), "dropbox-connector", release_size="M")
    assert store.get("dropbox-connector").thread == "C1:900.9"       # the latest thread wins
    update(Dispatcher(store, JORDAN, NOW, "C1:500.5"), "bulk-export", status="On Hold")
    assert store.get("bulk-export").thread == "C1:500.5"
    update(Dispatcher(store, ALEX, NOW), "dropbox-connector", release_size="L")   # a DM or the CLI: no thread
    assert store.get("dropbox-connector").thread == "C1:900.9"
    assert "thread" not in compact(store.get("dropbox-connector"))


def test_context_gives_week_windows_in_code(store):
    text = prompts.context("what lands next week?", ALEX, NOW, store.list())     # NOW is Mon 2026-08-24
    assert "This week: 2026-08-24 (Mon) to 2026-08-30 (Sun). Next week: 2026-08-31 (Mon) to 2026-09-06 (Sun)." in text


def test_kind_is_derived_from_what_the_tools_did():
    kind = lambda prose="", *outcomes: engine.Reply(text=prose, prose=prose, actions=[{"tool": "t", "outcome": o} for o in outcomes]).kind
    assert kind("", "queried", "created") == "create" and kind("", "held_for_dri") == "update" and kind("", "queried") == "question"
    assert kind("Which connector?") == "clarify" and kind("I just track launches.") == "other"
