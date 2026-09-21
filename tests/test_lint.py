"""The reply lint itself. No API key needed."""
from agent.engine import Reply
from tests.conftest import NOW
from tests.lint import FAKE_OFFER, WRONG_NEXT_WEEK, dates_in, lint


def test_fake_offers_are_caught_and_real_work_is_not():
    for bad in ("Happy to flag any of these to their DRI if you'd like.", "Want me to ping Dana?", "I'll let Sam know.",
                "I can remind you on Friday.", "Should I follow up with the vendor?"):
        assert FAKE_OFFER.search(bad), bad
    for fine in ("I'll keep the calendar current.", "I can update the date once it's confirmed.", "Held until Dana confirms.",
                 "I've flagged Box connector as at risk.", "I can't message anyone — I only keep the calendar."):
        assert not FAKE_OFFER.search(fine), fine


def test_next_week_answered_with_this_week_is_caught():
    assert WRONG_NEXT_WEEK.search("Next week (Aug 25–31): Self-serve trials") and WRONG_NEXT_WEEK.search("August 24 to August 30")
    assert not WRONG_NEXT_WEEK.search("Next week (Aug 31 – Sep 6): Self-serve trials goes GA Aug 31")


def test_a_write_without_a_receipt_is_an_error_and_a_loose_date_is_only_a_warning(store):
    wrote = [{"tool": "update_record", "outcome": "updated"}]
    errors, _ = lint("slip it", Reply(text="ok", prose="ok", actions=wrote), store.list(), NOW)
    assert errors == ["a write happened but the reply carries no receipt"]
    errors, warnings = lint("when is saved views?", Reply(text="x", prose="Saved views is Sep 1; SCIM lands Oct 9."), store.list(), NOW)
    assert not errors and "2026-10-09" in warnings[0] and "2026-09-01" not in warnings[0]
    assert dates_in("2026-09-14 and Sept. 7 and Feb 30", 2026) == {"2026-09-14", "2026-09-07"}
