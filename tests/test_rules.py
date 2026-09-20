"""The rules that are enforced in CODE, not in the prompt. No API key needed."""
from agent.tools import MAX_MUTATIONS_PER_MESSAGE, TOOLS, Dispatcher
from tests.conftest import JORDAN, NOW, PRIYA, SAM, SEED_COUNT


def update(d, record_id, **changes):
    return d.call("update_record", {"record_id": record_id, **changes})


def test_hearsay_from_non_dri_is_held_and_record_is_untouched(store):
    result = update(Dispatcher(store, JORDAN, NOW), "bulk-export", status="On Hold", change_note="heard in standup")
    record = store.get("bulk-export")
    assert result["outcome"] == "held_for_dri"
    assert record.status == "In Development"
    assert record.needs_dri_confirmation and "Jordan Lee" in record.pending_change
    assert store.list_changes("bulk-export")[-1].field == "pending"


def test_dri_confirming_a_held_change_applies_it_and_clears_the_flag(store):
    from tests.conftest import Sender
    update(Dispatcher(store, JORDAN, NOW), "bulk-export", status="On Hold")
    dana = Sender("U_DANA", "Dana Whitfield")
    update(Dispatcher(store, dana, NOW), "bulk-export", pending_decision="confirm")
    record = store.get("bulk-export")
    assert record.status == "On Hold" and not record.needs_dri_confirmation and not record.pending_change


def test_non_dri_cannot_confirm_a_held_change(store):
    update(Dispatcher(store, JORDAN, NOW), "bulk-export", status="On Hold")
    result = update(Dispatcher(store, JORDAN, NOW), "bulk-export", pending_decision="confirm")
    assert not result["ok"] and store.get("bulk-export").status == "In Development"


def test_removing_a_date_sets_tbd_and_flags_risk(store):
    update(Dispatcher(store, PRIYA, NOW), "saved-views", clear_ga_date=True, change_note="vendor has not confirmed")
    record = store.get("saved-views")
    assert record.ga_date is None and record.date_confidence == "tbd" and record.risk_level == "at_risk"


def test_slip_is_logged_with_old_and_new_date_and_marks_record_slipped(store):
    update(Dispatcher(store, SAM, NOW), "connectors-platform", ga_date="2026-09-04")
    record = store.get("connectors-platform")
    row = next(c for c in store.list_changes("connectors-platform") if c.field == "ga_date")
    assert (row.old, row.new, row.actor) == ("2026-08-28", "2026-09-04", "Sam Okafor")
    assert record.risk_level == "slipped"


def test_model_cannot_soften_a_slip_to_at_risk(store):
    update(Dispatcher(store, SAM, NOW), "connectors-platform", ga_date="2026-09-04", risk_level="at_risk")
    assert store.get("connectors-platform").risk_level == "slipped"


def test_upstream_slip_flags_every_downstream_launch(store):
    d = Dispatcher(store, SAM, NOW)
    d.call("create_record", {"title": "Box connector", "status": "In Development", "depends_on": ["connectors-platform"],
                             "release_size": "M", "date_confidence": "tbd", "risk_level": "on_track"})
    result = update(d, "connectors-platform", ga_date="2026-09-04")
    assert [f["title"] for f in result["downstream_flagged"]] == ["Box connector"]
    assert store.get("box-connector").risk_level == "at_risk"


def test_creating_a_launch_that_looks_like_an_existing_one_is_refused(store):
    result = Dispatcher(store, PRIYA, NOW).call("create_record", {"title": "Saved views v2", "status": "Planned"})
    assert result["outcome"] == "possible_duplicate" and len(store.list()) == SEED_COUNT


def test_same_title_cannot_be_created_twice_even_with_the_override(store):
    result = Dispatcher(store, PRIYA, NOW).call("create_record", {
        "title": "saved views", "status": "Planned", "date_confidence": "tbd", "release_size": "unknown",
        "risk_level": "on_track", "confirmed_not_duplicate": True})
    assert result["outcome"] == "duplicate" and len(store.list()) == SEED_COUNT


def test_a_placeholder_is_not_a_launch(store):
    # Seen live: a garbled second tool call created a record titled "place holder".
    d = Dispatcher(store, PRIYA, NOW)
    junk = d.call("create_record", {"title": "place holder", "status": "Planned", "confirmed_not_duplicate": True})
    real = d.call("create_record", {"title": "Audit log export", "status": "Planned", "depends_on": ["null"]})
    assert not junk["ok"] and real["ok"] and store.get(real["record"]["id"]).depends_on == []
    assert len(store.list()) == SEED_COUNT + 1


def test_one_message_cannot_make_more_than_three_changes(store):
    d = Dispatcher(store, SAM, NOW)
    results = [d.call("create_record", {"title": f"Injected launch {n}", "status": "Planned", "confirmed_not_duplicate": True})
               for n in range(MAX_MUTATIONS_PER_MESSAGE + 2)]
    assert sum(r["ok"] for r in results) == MAX_MUTATIONS_PER_MESSAGE
    assert len(store.list()) == SEED_COUNT + MAX_MUTATIONS_PER_MESSAGE


def test_model_tools_cannot_write_identity_or_governance_fields():
    forbidden = {"dri_id", "needs_dri_confirmation", "pending_change", "last_updated", "last_updated_by",
                 "question_for", "actor"}
    for tool in TOOLS:
        assert not forbidden & set(tool["input_schema"]["properties"]), tool["name"]


def test_tool_input_outside_the_schema_is_rejected_in_code(store):
    d = Dispatcher(store, PRIYA, NOW)
    assert not update(d, "saved-views", status="Shipped!!")["ok"]
    assert not update(d, "saved-views", dri_id="U_JORDAN")["ok"]
    assert store.get("saved-views").status == "In Development"
