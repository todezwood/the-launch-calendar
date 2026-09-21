# Hobbes, the Launch Calendar agent

## The problem
Launch news lives buried in Slack. Sales, Support and Marketing cannot tell what is shipping, when, or what just slipped, so they ping the DRI and still get surprised. The usual fix is a form or a tracker that slows the business down, and it goes stale. My view: **standardize the agents, not the humans.** Let people keep posting the way they do, and have an agent turn those messages into a clean record.

## The goal
One calendar every team can trust, giving visibility into the **roadmap, delivery dates, risks, and dependencies**.

## What I built
- **Lives in Slack.** Post in the launches channel or DM Hobbes. No form, no @mention, no special format.
- **Creates and updates launches in Notion.** It reads the message, finds the right launch, and saves what changed. "Next tues" becomes a real date.
- **Answers questions**, such as "what lands next week?" or "what is at risk?"
- **Sends a receipt after every save.** Code builds it, not the model, so it shows what was saved, held, or not done. Reply in the thread to correct it.
- **Protects ownership.** A change from anyone but the DRI is held until the DRI confirms. Hearsay never changes the calendar.
- **Flags risk.** A date that moves later is marked as slipped, and every launch that depends on it is flagged.
- **Refuses duplicates**, and catches the same message sent twice.
- **Keeps a change log**: who changed what, when, old value to new value.
- **One Notion view per goal**: a board by Status (roadmap), a Timeline (dates), Risks and Dependencies.
- **Hobbes performance**: Performance metrics page tracks speed, errors and 👍/👎.

## What I would do next, and why
1. **Notifications.** Send held changes to the DRI, and tell teams when a launch they care about moves. Today Hobbes only speaks when spoken to.
2. **Serve the whole business.** Give each team a checkbox on every launch: Legal sign-off, Marketing's announcement, Sales training, Support's answers. A list of dates becomes a launch readiness view.
3. **Connect to the release pipeline and other agents.** Hobbes learns from CI/CD when something ships or slips, and checks with a docs agent that customer docs are ready. The calendar stays current without a person typing every update.
4. **Calendar hygiene.** Background jobs that find stale or never-closed launches, check accuracy, nudge owners, and send a weekly "what changed" digest.
5. **Real observability.** Move metrics into Datadog or Grafana: uptime, run time, errors, logs, 👍/👎, and how often someone replies "that is not right". That shows where to make the agent better.
6. **Production ready for GC AI.** Deploy inside GC AI's infrastructure: its cloud, Slack and secrets, a private workspace, a queue, a real database, alerts, and its own CI/CD pipeline.

## What I left manual (most visible first)
1. **Progress updates.** Every create, update and "it shipped" starts with a person posting. No link to other systems yet (next step 3).
2. **Confirming held changes.** The DRI has to come to Hobbes. Notifications were out of scope (next step 1).
3. **Checking Hobbes' work.** A person reads the receipt and corrects it. A human is the last accuracy check, on purpose.
4. **Cleaning up.** Nothing finds a launch that went quiet or never closed (next step 4).
5. **Watching Hobbes.** Nothing alerts on errors or 👎. Someone has to open the performance page (next step 5).

## Try it
**Live:** post in the demo Slack and watch the [public calendar](https://aspiring-tendency-ab9.notion.site/Launch-Calendar-3e173b0fc753801ca77bd9b5c2e86168) update ([screenshot](docs/roadmap.png)).

**On your laptop** (no Slack or Notion needed, only an Anthropic API key):
```
python3 -m venv .venv && source .venv/bin/activate         # 1. a clean Python environment
pip install -r requirements.txt && cp .env.example .env    # 2. install, then put your key in .env
python -m scripts.seed                                     # 3. load the 7 sample launches
python -m adapters.cli --as "Alex Kim"                     # 4. chat with Hobbes in the terminal
pytest -v                                                  # optional: run the tests (saved run: tests/TRANSCRIPT.txt)
```
