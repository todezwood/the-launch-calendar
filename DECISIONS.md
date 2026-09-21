# Decisions

The calls that shaped this build, and what I'd revisit. Field-by-field rationale lives in `agent/schema.py`; this is the level above it.

## 1. Standardize the agent, not the humans
The brief's messages are one messy line each, and that is the right input. A form would get cleaner data and fewer announcements. So there is no form, no slash command, no required fields on the way in: the record is created immediately with whatever was said, and the agent asks at most two questions — only the ones another team plans around (GA date, release size).

The first hour of real use in Slack tested this harder than the suite did: for a bare `Dropbox connector` the deployed bot asked "is this a new launch?" and saved nothing — a polite form, by another name. The prompt now says a bare feature name that matches nothing *is* the announcement: create it, then ask.

The same hour killed the @mention. I forgot it myself, twice, and the bot sat silent — a required prefix is one more field on the form. The bot now treats every message in the launches channel as meant for it and answers in a thread. I first had it stay silent on anything that wasn't launch news; in use, silence read as "it's down", so that came out — telling chatter from news is the model's job, and a one-line reply is cheaper than a confused user. Trade: every channel message costs a model call, which is right for one dedicated channel and wrong for #general.

## 2. Rules live in code; judgment lives in the model
The model reads the message and decides *what is being said*. Everything that must never be wrong is enforced by the tool layer, and each rule has an offline test (`tests/test_rules.py`):

| Rule | Why it is not left to the prompt |
|---|---|
| A non-DRI's change is held as pending, never applied | Hearsay ("someone said in standup…") is the main way a calendar becomes untrustworthy |
| A date that moves later marks the record `slipped`; a removed date becomes `tbd` + `at_risk` | In a live run the model called a one-week slip "at risk". Code now wins. |
| A slip flags every downstream launch | The person announcing the slip rarely knows who depends on them |
| Same title can't be created twice, even with the model's "not a duplicate" override | In a live run the model re-created a record to correct a detail |
| A placeholder title ("place holder", "place", "tbd") is refused; a dependency of `"null"` means none | In a live run a garbled second tool call created a junk record |
| Message text is data, not instructions; one message is bounded by 8 model turns | One message should not be able to rewrite the calendar |
| Every write ends with a receipt made by code — saved / held for the DRI / not done, read back from the store | The model's summary is what it believes it did. The receipt is what is on the calendar, and the person can correct it in the same thread |
| Same text from the same person in the same place within 2 minutes, after a write: answered with the first receipt, not run again | "No reply, so I sent it again" would apply "slipping a week" twice |
| The model cannot write identity, governance, timestamps or history | Those come from the chat envelope, not from what someone typed |

Three of those rows exist because the live tests caught the model doing the wrong thing. That is the argument for the split: a prompt fix would have held until the next model update; the code fix holds.

I first capped a message at three changes. A reviewer sent four legitimate updates in one message and the fourth was refused; the cap also counted tool calls, not changes. It is gone. What bounds a message now is the turn limit; what keeps it honest is the DRI gate, the receipt and the change log. The trade, stated plainly: an injected message from a non-DRI can now park up to seven *held* changes instead of three. None is applied.

The receipt is the verification step, and it comes after the save, not before. "Here's what I'm about to do — confirm?" would make every one-line announcement a two-step form (§1). If the model call fails or runs out of turns after something was saved, the person still gets the receipt: the old error reply said "nothing was saved", which was not always true.

## 3. Three narrow tools, not one big one
`create_record`, `update_record`, `query_records`. Things I learned the hard way:
- **"Required field, empty string means unset" breaks the model.** It filled the blanks with stray markup and every create failed validation (first live run: 3 of 22). Fields that don't always apply are now optional, and code strips placeholder values.
- **The API caps combined strict-schema complexity.** All three tools as `strict` returned a 400, so `update` was validated in code instead, with a test proving out-of-schema input is rejected.
- **Strict mode made `create` sparse.** The final audit re-ran an unchanged, green suite and got 39/45. Logging the raw tool inputs showed why: in 7 of 7 creates the model sent only the required fields, then patched in the beta date and audience with a second call — and sometimes fired a garbled parallel duplicate. When one of those got through (a record titled "place"), it used up the three-changes budget I had then (§2), the repair was refused, and the launch lost its date. `create` is now validated in code like `update`, and the model makes one tool call per turn. Same test after: 6 of 6 creates complete in one call, half the model calls per launch. Only `query` stays strict.

## 4. Notion is the database and the display
One source of truth, nothing to sync, and the audience already lives there. A status-grouped board is the default view, not a date grid: stakeholders ask "what's coming and what's slipping", and a date grid hides exactly the records that need eyes — no date, a withdrawn date, an unconfirmed change. A Timeline tab sits second, for "when", and a filtered **Risks** table third — slipped, at risk, unconfirmed, or undated — so each of v1's three goals (roadmap, delivery dates, risks) has its own view. Its filter is the same rule as `agent/roadmap.py:is_risky`. A fourth tab, **Dependencies**, lists every launch that waits on another: a slip's blast radius, which the code already flags, made visible. The store is an interface (`store/base.py`), with a JSON implementation for local use and tests, so swapping in a real database later is one file. The change log is a second, append-only database and deliberately has no raw-message column, because the page is public. Public is a choice: reviewers need no login, the data is fictional, and what it does expose is testers' display names and chat ids. Production is a private workspace.

A third database, the **Agent Log**, gets one row per handled message, written after the reply so it adds no wait: kind (create / update / question / clarify / other), writes, held changes, duplicates refused, resends caught, error yes/no, seconds, and a 👍/👎 if someone reacts to the reply. Its views are the **Hobbes performance** page. Again no message text and no exception text. It answers "is it fast, is it failing, do people agree with it". It cannot answer "was the update correct": that needs ground truth, which only the offline tests have (§5). A failure to log never fails a reply, and with no table configured the agent simply does not log.

## 5. Tests are the brief's messages, replies and questions, run live, in order
Appendix B's "calendar as it stands today" was missing from the PDF, so the seed (`tests/fixtures/seed.json`) is mine; it includes the three launches the update messages assume exist. Each test name is one judgment call ("withdrawn date is cleared, not left stale"). Asserts are structural — what ended up on the calendar — so they survive prompt changes. A code audit pointed out that this never looks at the reply, and the transcript had the bot offering to "flag these to their DRI", which it cannot do. So every live reply now also passes a small deterministic lint (`tests/lint.py`): no offer of an action the agent can't perform, a receipt on every write; ungrounded dates are counted as warnings. `JUDGE=1` adds a scorecard at the end of the transcript (`tests/judge.py`): five yes/no criteria per reply, plus duplicates created, correct writes and unnecessary questions computed in code. The judge is the same model family grading itself, so it is a report, not a gate. I did not put a second model in the live path: twice the cost and latency for a sample. The clock is frozen so "next tues" means the same thing every run. A frozen clock also gave every record the same timestamp, which exposed a real bug: "most recent open question" was a coin flip on ties. Ties now break by creation order. A green run is committed in `tests/TRANSCRIPT.txt` for readers without an API key.

The five page-1 stakeholder questions are tests too, each asserting that a question writes nothing; Legal's gets an honest "not tracked yet", because data-touch is a field I left out.

This is a regression suite, not an eval, and a green run is a sample, not a proof — the same code went 45/45 one morning and 39/45 that afternoon (§3). It passed 3/22, 19/22, 21/22, 15/22 (a prompt change that backfired) and then 22/22 over an afternoon; a graded set of real intake messages is the next thing I'd build.

## 6. Small operational calls
- **Events API over HTTP on Cloud Run, max one instance.** Scale-to-zero costs cents; one instance makes the in-memory duplicate-event guard authoritative. Trade: a cold start can take a few seconds, shown to the user as a 👀 reaction.
- **One message at a time** (a lock). Concurrent edits are last-write-wins, and the change log makes that visible and recoverable. Fine at one team's volume; not at ten. The lock is not a queue: in live validation I fired five messages in 25 seconds and a slip was handled before the GA answer sent ahead of it, so the slip moved the beta date and had no GA date to move. At human pace it doesn't happen; the fix is a per-channel FIFO queue.
- **Validation by use, not just by suite.** Asking the brief's five stakeholder questions found what the 12 messages couldn't: a Sales question about a launch that wasn't on the calendar *created* it, with the asker as DRI. A question now never writes; there is a test for it.
- **Ownership in the demo.** Seeded launches belong to fictional DRIs, so a reviewer's update to one is held, correctly, for someone who will never confirm it. I did not add a self-claim bypass: it would hollow out the one rule the calendar's trust rests on. The CLI's `--as "Priya Raman"` shows the DRI path; reassignment is item 2 below.
- **Cost and latency.** About $0.05 per message. A cold start can take a few seconds — no reply in 30s, resend. A resend of something already saved is caught for two minutes and answered with the first receipt (§2); the guard, like the event guard, is in memory and resets on a cold start.
- **Replies know their thread.** The thread a record was last written from is stored on it (code-written, like the DRI's chat id). A bare "M" in that thread goes to that record, not to whichever question is newest — with two open questions for one person, it used to.
- **Errors reply with a reference id, never the exception text**, and never claim "nothing was saved": a failure after a write is still a write. A Notion outage surfaces as an error; only "no such page" reads as "no such record".
- **Secrets in Secret Manager, read by a dedicated service account** with access to those secrets only.

## What I'd revisit first
0. **The bot sometimes nags.** After recording a launch it occasionally adds "still waiting on the size for X" about a *different* record. The prompt forbids it and that cut it from every run to about one in three; I did not strip sentences from replies in code, because the same filter would delete a legitimate clarifying question. The real fix is structural: show the model its open questions only when the message could be an answer to one.
1. Held changes wait on the board until the DRI speaks to the bot. They should be pushed to the DRI.
2. DRI identity is a chat id captured at creation. Reassignment and people leaving need a real story.
3. Matching an update to a record is the model reading the whole calendar. That works at tens of launches; at hundreds it needs retrieval first.
4. The open question is one text blob matched by the model. Deriving "what is still missing" from the record's empty fields would make it data.
5. A record write and its change-log rows are separate Notion calls, not a transaction. A failure between them leaves a change without its log row; the receipt's read-back would show the record, not the gap.
6. The change log stores names, not chat ids. Two people with one display name are one actor.
7. A removed 👍/👎 is ignored; the last reaction added wins. Ratings are a signal, not a metric, until there are enough of them.
