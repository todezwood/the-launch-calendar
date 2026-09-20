# Hobbes — the Launch Calendar agent

**Standardize the agents, not the humans.** People announce launches the way they already do — one messy line in Slack — and the agent turns that into a calendar every team can trust without pinging the DRI. v1 goal: visibility into the **roadmap, delivery dates, and risks**.

**Live:** talk in the launches channel of the demo Slack (no @mention; tell me who to add) and watch the [public Notion calendar](https://aspiring-tendency-ab9.notion.site/Launch-Calendar-3e173b0fc753801ca77bd9b5c2e86168) ([screenshot](docs/roadmap.png)). Try `Dropbox connector` → in the thread, `next tues` → `someone said saved views is on hold, not my project`. Seeded launches belong to fictional DRIs, so your change to one is *held as unconfirmed* — the governance rule, working.

```
pip install -r requirements.txt && cp .env.example .env    # add ANTHROPIC_API_KEY
python -m scripts.seed && python -m adapters.cli --as "Alex Kim"   # or: roadmap | risks
pytest -v    # 12 Appendix B messages, 5 bare replies, 5 stakeholder questions; green run: tests/TRANSCRIPT.txt
```

## Fields, and why (per field: `agent/schema.py`; the calls: `DECISIONS.md`)
- **Title, DRI, GA date, Status, Release size, Feature brief** — required. **Status speaks GTM language** (Planned → In Development → Internal → Limited Beta → Open Beta → GA): "can Sales talk about it?" is one word. Size = GTM effort (S quiet, M support note, L blog + enablement).
- **Beta date, Audience** — half the brief's messages are betas or staged rollouts. **Date confidence** — "about two weeks, assuming nothing breaks" is a target, not a promise; a withdrawn date becomes an honest blank.
- **Risk level, Depends on** — set *by code* on slips and removed dates; slips flag dependents.
- **Needs DRI confirmation** — hearsay is held, not applied. **Change log** (who, when, old → new) — "what slipped, and when did we find out?"

## What I left out
| Left out | Why not v1 | Revisit when |
|---|---|---|
| Reminders, nudges, notifications | Part 2; trust in the record comes first | DRIs rely on it |
| Legal/data-touch flag, goal linkage | Needs Legal's definitions, not my guess | Legal asks the bot |
| Tracker sync, approvals, permissions | Store is an adapter; the DRI gate covers the risk | A team lives in Linear |

## Display: one view per goal
A Notion **board grouped by Status** (roadmap), a **Timeline** (delivery dates), **Risks** (slipped, at risk, unconfirmed, undated) and **Dependencies** (who a slip hits next). The board is the default, not a date grid: a grid hides exactly the launches that need eyes — the ones with no date. Notion is both database and display.

## Next, and what stayed manual
**Next:** (1) the Part 2 keep-it-fresh loop — "what changed" digests, stale-record nudges, held changes pushed to the DRI; (2) a graded eval of real intake messages; (3) production shape — private workspace, a queue, a real database with Notion as mirror.
**Manual today:** confirming held changes, DRI reassignment, Notion view setup, Slack install.
