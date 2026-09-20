# Hobbes — the Launch Calendar agent

**Standardize the agents, not the humans.** People keep announcing launches the way they already do — one messy line in Slack. The agent is the translation layer that turns those lines into one calendar Marketing, Sales, Support, Legal and Leadership can trust without pinging the DRI. v1 goal: visibility into the **roadmap, delivery dates, and risks**.

**Live:** DM `@Hobbes` in the demo Slack workspace (invite: _TODO_) · calendar: _TODO public Notion link_ · up through _TODO date_.
Try it in 60 seconds — DM these and watch the Notion board: `Dropbox connector` → then `next tues` → then `someone said saved views is on hold, not my project`.

```
pip install -r requirements.txt && cp .env.example .env     # add ANTHROPIC_API_KEY
python -m scripts.seed && python -m adapters.cli --as "Alex Kim"   # chat locally (JSON store)
python -m adapters.cli roadmap                               # or: risks | history
pytest -v                                                    # one line per judgment call
```
`pytest -v` runs 9 rule tests offline plus the 12 Appendix B messages against the live model (needs a key; a green run is committed in `tests/TRANSCRIPT.txt`). Appendix B's "calendar as it stands today" was missing from the PDF, so I seeded my own (`tests/fixtures/seed.json`).

## Fields, and why (rationale per field lives in `agent/schema.py`)
- **Title, DRI, GA date, Status, Release size, Feature brief** — the required set. DRI defaults to whoever announced it. **Status speaks GTM language** (Planned → In Development → Internal → Limited Beta → Open Beta → GA): "can Sales talk about it?" is readable from one word, and beta is its own status. Size = how much go-to-market it needs (S quiet, M support heads-up, L blog + enablement).
- **Beta date + Audience/rollout** — half the real messages are betas or staged rollouts; a beta slip needs a date to slip.
- **Date confidence** (committed / target / tbd) + **date note** — "about two weeks, assuming nothing breaks" is not a promise, and a withdrawn date becomes an honest blank. This is Sales' "is that date still true?"
- **Risk level + note, Depends on** — risk is set *by code* on every slip or removed date, and a slip flags every downstream launch.
- **Needs DRI confirmation + pending change** — governance. The agent knows who is speaking: the DRI's change applies; anyone else's ("someone said in standup…") is held and shown as unconfirmed, never blindly applied.
- **Change log** (second database, append-only: who, when, field, old → new) — Leadership's "what slipped, and when did we find out?"
- **Open question / last updated by** — lets a bare `M` or `next tues` land on the right record; shows staleness.

The model gets three narrow tools (create / update / query). It cannot write identity, governance, timestamps or history — code does that from the Slack envelope. Max 3 changes per message; message text is treated as data, not instructions.

## What I left out
| Left out | Why not v1 | Trigger to revisit |
|---|---|---|
| Reminders, staleness nudges, notifications | Part 2 scope; trust in the record comes first | Once DRIs rely on it — the change log is already the event feed |
| Linear/Jira sync | The store is an adapter interface (Notion, JSON today) | First team that lives in an issue tracker |
| Legal/data-touch flag, goal linkage | Needs Legal's definitions, not my guess | Legal asks their page-1 question of the bot |
| Date-grid view, approval workflow, permissions | See display; governance gate covers the real risk | >1 workspace or external readers |

## Display: a status-grouped board, not a date grid
The calendar is a Notion board grouped by Status, sorted by date, risk shown inline (same view in the CLI). Stakeholders ask "what's coming and what's slipping," not "what's on Tuesday" — and a date grid hides exactly the launches that need eyes: no date, a removed date, an unconfirmed change. Notion is both database and display: one source of truth, nothing to sync. (Board view is built by hand in ~90 seconds: Board → group by Status → sort by GA date.)

## Next, and what stayed manual
1. **Keep-it-fresh loop** (Part 2): weekly "what changed" digest per audience, DRI nudges on stale or past-date records, and the pending-confirmation queue pushed to the DRI instead of waiting on the board.
2. **An eval, not just tests** — the 12 messages are regression; next is a graded set of real intake messages. 3. **Production shape**: private workspace (no public page), Cloud Tasks + a real database with Notion as mirror at ~10× volume; today concurrent edits are last-write-wins, visible and recoverable via the change log.

Manual today: confirming held changes (DRI replies to the bot), the Notion board view, Slack app install. Cost ≈ $0.05/message. Cold start can take a few seconds — no reply in 30s, resend.
