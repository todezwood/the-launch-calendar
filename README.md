# Hobbes — the Launch Calendar agent

**Standardize the agents, not the humans.** People announce launches as they already do — one messy line in Slack — and the agent turns that into a calendar every team can trust without pinging the DRI. v1 goal: visibility into the **roadmap, delivery dates, and risks**.

**Live:** talk in the launches channel of the demo Slack (no @mention; tell me whom to add) and watch the [public Notion calendar](https://aspiring-tendency-ab9.notion.site/Launch-Calendar-3e173b0fc753801ca77bd9b5c2e86168) ([screenshot](docs/roadmap.png)). Try `Dropbox connector` → in the thread, `next tues` → `someone said saved views is on hold, not my project`. Every write ends with a code-made receipt (saved / held / not done), correctable in-thread. Seeded launches have fictional DRIs, so your change to one is *held as unconfirmed* — the governance rule.

```
pip install -r requirements.txt && cp .env.example .env    # add ANTHROPIC_API_KEY
python -m scripts.seed && python -m adapters.cli --as "Alex Kim"   # or: roadmap | risks
pytest -v    # Appendix B's 12 messages, bare replies, stakeholder questions, reply lint; green run: tests/TRANSCRIPT.txt
```

## Fields, and why (per field: `agent/schema.py`; the calls: `DECISIONS.md`)
- **Title, DRI, GA date, Status, Release size, Feature brief** — required. **Status speaks GTM language** (Planned → … → Limited Beta → Open Beta → GA): "can Sales talk about it?" is one word. Size = GTM effort (S quiet, M support note, L blog).
- **Beta date, Audience** — half the brief's messages are betas. **Date confidence** — "about two weeks, assuming nothing breaks" is a target, not a promise; a withdrawn date becomes a blank.
- **Risk level, Depends on** — set *by code* on slips and removed dates; slips flag dependents.
- **Needs DRI confirmation** — hearsay is held, not applied. **Change log** (who, when, old → new) — "what slipped, and when did we find out?"

## What I left out
| Left out | Why not v1 | Revisit when |
|---|---|---|
| Reminders, nudges, notifications | Part 2; trust in the record comes first | DRIs rely on it |
| Legal/data-touch flag, goal linkage | Needs Legal's definitions, not my guess | Legal asks the bot |
| Tracker sync, approvals, permissions | Store is an adapter; the DRI gate covers the risk | A team lives in Linear |

## Display: one view per goal
A Notion **board grouped by Status** (roadmap), a **Timeline** (delivery dates), **Risks** and **Dependencies** (who a slip hits next). The board is the default: a date grid hides the launches that need eyes — those with no date. A **Hobbes performance** log records every handled message — speed, errors, duplicates, 👍/👎 — never its text.

## Next, and what stayed manual
**Next:** (1) the Part 2 keep-it-fresh loop — "what changed" digests, stale-record nudges, held changes pushed to the DRI; (2) a graded eval of real intake messages; (3) production shape — private workspace, a queue, a real database behind Notion.
**Manual today:** confirming held changes, DRI reassignment, Notion view setup, Slack install.
