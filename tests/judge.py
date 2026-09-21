"""Offline reply-quality scorecard. Runs only with JUDGE=1, after the live tests, and only reports:
a judge is a sample (and here the same model family grading itself), so it never fails a test.
"""
import json
import os

CRITERIA = ["grounded", "date_math", "on_topic", "honest_capabilities", "short_max_2_questions"]
PROMPT = """You are grading one reply from a launch-calendar chat agent. It can ONLY read and write its calendar; \
it cannot message or notify anyone. Today is {today}. Weeks run Monday to Sunday.

<message from="{sender}">{message}</message>
<reply>{reply}</reply>
<tool_actions>{actions}</tool_actions>
<rows_this_message_wrote>{changes}</rows_this_message_wrote>
<change_log_so_far>{log}</change_log_so_far>
<calendar_after>{calendar}</calendar_after>

Answer with JSON only, each value true or false:
{{"grounded": every fact in the reply is supported by the calendar, the change rows or the message,
"date_math": every relative date was resolved correctly against today,
"on_topic": it addresses this message and does not bring up other records' open questions,
"honest_capabilities": it never offers or claims an action it cannot perform,
"short_max_2_questions": it is a few lines and asks at most two questions,
"why": "one short sentence on any false"}}"""


def scorecard(run: list[dict], passed: int, total: int, titles: list[str], warnings: list[str]) -> str:
    from agent import engine
    client, model = engine._anthropic(), os.environ.get("JUDGE_MODEL", engine.MODEL)
    tally, notes, judge_errors = {c: 0 for c in CRITERIA}, [], 0
    for item in run:
        try:
            raw = client.messages.create(model=model, max_tokens=2000, messages=[{"role": "user", "content": PROMPT.format(
                **{k: json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v for k, v in item.items()})}])
            text = "".join(b.text for b in raw.content if b.type == "text")
            verdict = json.loads(text[text.index("{"):text.rindex("}") + 1])
        except Exception:
            judge_errors += 1
            continue
        for c in CRITERIA:
            tally[c] += bool(verdict.get(c))
        if not all(verdict.get(c) for c in CRITERIA):
            notes.append(f"  - [{item['test']}] {verdict.get('why', '')}")
    graded = len(run) - judge_errors
    normal = [t.strip().lower() for t in titles]
    lines = [f"REPLY-QUALITY SCORECARD — {graded} replies graded by {model} (a report, not a gate; judge errors: {judge_errors})"]
    lines += [f"  {c:<24}{tally[c]}/{graded}" for c in CRITERIA]
    lines += [f"  {'duplicates created':<24}{len(normal) - len(set(normal))}   (same title twice in the final calendar; computed in code)",
              f"  {'correct writes':<24}{passed}/{total}   (live tests whose structural asserts passed; computed in code)",
              f"  {'unnecessary questions':<24}{sum(i['reply'].split('———')[0].count('?') > 2 for i in run)}   (replies asking more than two; computed in code)",
              f"  {'lint warnings':<24}{len(warnings)}"]
    return "\n".join(lines + [f"  - {w}" for w in warnings] + (["  judge said no on:"] + notes if notes else []))
