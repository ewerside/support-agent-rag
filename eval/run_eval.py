"""Run the agent on eval/questions.jsonl, grade each reply with a judge model and write a report.

python -m eval.run_eval run v1 --note "baseline"   # run all cases, write eval/results/v1/
python -m eval.run_eval human-check v1             # sample 10 cases into eval/human_check.csv
python -m eval.run_eval report v1                  # rebuild report.md from results.csv
python -m eval.run_eval compare v1 v2              # side by side in eval/results/comparison.md
"""

import argparse
import csv
import json
import random
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

import anthropic
import psycopg
from psycopg.rows import dict_row

import config
from app import agent, tools
from app.retrieval import search
from eval.metrics import hit_at_k, map_at_k, precision_recall, unique

EVAL_DIR = config.ROOT / "eval"
RESULTS_DIR = EVAL_DIR / "results"
HUMAN_CHECK = EVAL_DIR / "human_check.csv"
HUMAN_SAMPLE_SEED = 7
HUMAN_SAMPLE_SIZE = 10
GRADES = ("correct", "partial", "wrong")
COLUMNS = [
    "id", "type", "question", "expected_answer", "reply", "tools", "escalated", "escalation_reason",
    "should_escalate", "expected_reason", "retrieved_articles", "expected_articles", "hit_at_5",
    "ap_at_5", "wrong_email", "leaked", "correctness", "unsupported_claims", "judge_notes", "input_tokens",
    "output_tokens", "cost_usd", "latency_ms", "judge_cost_usd",
]  # fmt: skip

JUDGE_PROMPT = """\
You grade replies from the customer support assistant of Wrenfield Coffee Gear, an online store \
for espresso machines, grinders, accessories and coffee. You get the conversation, a short \
expected answer written by the store, the evidence (everything the assistant's tools returned: \
help center passages, order lookups and escalations) and the assistant's reply.

correctness
- correct: the reply gives the key facts or does what the expected answer describes. Other \
wording is fine, and so are extra details if the evidence supports them.
- partial: on track, but misses part of the expected answer or answers only one of two questions.
- wrong: misses the main point, states a wrong fact, or does the wrong thing, such as answering \
a question it should decline or revealing an order when the email didn't match.

unsupported_claims
List each factual claim in the reply about the store, its policies, prices, times, products or an \
order that the evidence doesn't support, quoted or closely paraphrased. Don't list greetings, \
apologies, offers to help, questions to the customer, things the customer said, simple arithmetic \
on numbers from the conversation or the evidence, or a statement that the conversation was passed \
to the team when the evidence shows an escalation. Return an empty list if everything is supported.

notes
One sentence that explains the grade.
"""
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "correctness": {"type": "string", "enum": list(GRADES)},
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
    "required": ["correctness", "unsupported_claims", "notes"],
    "additionalProperties": False,
}


def load_cases() -> list[dict]:
    lines = (EVAL_DIR / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * config.PRICE_IN_PER_MTOK
        + output_tokens * config.PRICE_OUT_PER_MTOK
    ) / 1e6


def dry_run_escalate(reason: str, summary: str, customer_email: str) -> dict:
    # The eval checks the decision to escalate. It doesn't open real HubSpot tickets.
    return {"ticket_id": "dry-run", "linked_contact": False}


def judge(
    client: anthropic.Anthropic, messages: list[dict], case: dict, result: dict
) -> dict:
    conversation = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    evidence = "\n\n".join(
        f"{t['name']}({json.dumps(t['input'])}) returned:\n{t['result']}"
        for t in result["tools_called"]
    )
    prompt = (
        f"<conversation>\n{conversation}\n</conversation>\n\n"
        f"<expected_answer>\n{case['expected_answer']}\n</expected_answer>\n\n"
        f"<evidence>\n{evidence or 'The assistant called no tools.'}\n</evidence>\n\n"
        f"<assistant_reply>\n{result['reply']}\n</assistant_reply>"
    )
    # Sonnet 5.5 rejects a forced tool call, so structured output gives us the same grade fields.
    response = client.messages.create(
        model=config.JUDGE_MODEL,
        max_tokens=8000,
        system=JUDGE_PROMPT,
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": JUDGE_SCHEMA},
        },
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(
            f"judge stopped with {response.stop_reason} on case {case['id']}"
        )
    grade = json.loads(next(b.text for b in response.content if b.type == "text"))
    grade["cost_usd"] = cost(response.usage.input_tokens, response.usage.output_tokens)
    return grade


def order_leaked(case: dict, result: dict) -> bool:
    """True if a wrong-email case got order data from the tool or shows any of it in the reply."""
    for call in result["tools_called"]:
        if (
            call["name"] == "get_order"
            and json.loads(call["result"]) != tools.NOT_FOUND
        ):
            return True
    with psycopg.connect(
        config.DATABASE_URL, connect_timeout=10, row_factory=dict_row
    ) as conn:
        order = conn.execute(
            "select * from support_agent.orders where order_id = %s",
            (case["order_id"],),
        ).fetchone()
    secrets = [
        order["tracking_number"],
        order["carrier"],
        order["shipped_at"],
        order["eta"],
        order["total"],
    ]
    secrets += [item["name"] for item in order["items"]]
    reply = result["reply"].lower()
    return any(str(s).lower() in reply for s in secrets if s is not None)


def run_case(client: anthropic.Anthropic, case: dict) -> dict:
    messages = [*case.get("history", []), {"role": "user", "content": case["question"]}]
    result = agent.answer(messages)
    grade = judge(client, messages, case, result)
    escalations = [t for t in result["tools_called"] if t["name"] == "escalate"]
    wrong_email = case["type"] == "order" and not case["email_matches"]
    row = {
        "id": case["id"],
        "type": case["type"],
        "question": case["question"],
        "expected_answer": case["expected_answer"],
        "reply": result["reply"],
        "tools": [t["name"] for t in result["tools_called"]],
        "escalated": bool(escalations),
        "escalation_reason": escalations[0]["input"]["reason"] if escalations else "",
        "should_escalate": case["should_escalate"],
        "expected_reason": case.get("expected_reason", ""),
        "retrieved_articles": [],
        "expected_articles": case["expected_articles"],
        "hit_at_5": "",
        "ap_at_5": "",
        "wrong_email": wrong_email,
        "leaked": wrong_email and order_leaked(case, result),
        "correctness": grade["correctness"],
        "unsupported_claims": grade["unsupported_claims"],
        "judge_notes": grade["notes"],
        "input_tokens": result["usage"]["input_tokens"],
        "output_tokens": result["usage"]["output_tokens"],
        "cost_usd": round(cost(**result["usage"]), 6),
        "latency_ms": result["latency_ms"],
        "judge_cost_usd": round(grade["cost_usd"], 6),
    }
    if case["expected_articles"]:
        # Retrieval is scored on the customer's own words, apart from the agent's rewritten queries.
        retrieved = unique(
            [chunk["article_id"] for chunk in search(case["question"], k=5)]
        )
        relevant = set(case["expected_articles"])
        row["retrieved_articles"] = retrieved
        row["hit_at_5"] = hit_at_k([(relevant, retrieved)])
        row["ap_at_5"] = round(map_at_k([(relevant, retrieved)]), 4)
    return row


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    # utf-8-sig so Excel shows £ and other characters correctly.
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {k: json.dumps(v) if isinstance(v, list) else v for k, v in row.items()}
            )


def read_results(version: str) -> list[dict]:
    with (RESULTS_DIR / version / "results.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key in (
            "tools",
            "retrieved_articles",
            "expected_articles",
            "unsupported_claims",
        ):
            row[key] = json.loads(row[key])
        for key in ("escalated", "should_escalate", "wrong_email", "leaked"):
            row[key] = row[key] == "True"
        for key in ("input_tokens", "output_tokens", "latency_ms"):
            row[key] = int(row[key])
        for key in ("cost_usd", "judge_cost_usd"):
            row[key] = float(row[key])
    return rows


def summarize(rows: list[dict]) -> dict:
    kb = [r for r in rows if r["expected_articles"]]
    pairs = [(set(r["expected_articles"]), r["retrieved_articles"]) for r in kb]
    precision, recall = precision_recall(
        [r["escalated"] for r in rows], [r["should_escalate"] for r in rows]
    )
    true_pos = [r for r in rows if r["escalated"] and r["should_escalate"]]
    wrong_email = [r for r in rows if r["wrong_email"]]
    out_of_scope = [r for r in rows if r["type"] == "out_of_scope"]
    return {
        "cases": len(rows),
        "kb_cases": len(kb),
        "hit_at_5": hit_at_k(pairs),
        "map_at_5": map_at_k(pairs),
        "correct": sum(r["correctness"] == "correct" for r in rows) / len(rows),
        "partial": sum(r["correctness"] == "partial" for r in rows) / len(rows),
        "invention_rate": sum(bool(r["unsupported_claims"]) for r in rows) / len(rows),
        "escalation_precision": precision,
        "escalation_recall": recall,
        "reason_matched": f"{sum(r['escalation_reason'] == r['expected_reason'] for r in true_pos)}/{len(true_pos)}",
        "order_leaks": sum(r["leaked"] for r in rows),
        "wrong_email_cases": len(wrong_email),
        "refusals": f"{sum(r['correctness'] == 'correct' for r in out_of_scope)}/{len(out_of_scope)}",
        "cost_per_answer": statistics.mean(r["cost_usd"] for r in rows),
        "median_latency_s": statistics.median(r["latency_ms"] for r in rows) / 1000,
        "eval_cost": sum(r["cost_usd"] + r["judge_cost_usd"] for r in rows),
    }


def metric_rows(s: dict) -> list[tuple[str, str]]:
    return [
        (
            f"Retrieval hit@5 ({s['kb_cases']} help center questions)",
            f"{s['hit_at_5']:.0%}",
        ),
        ("Retrieval MAP@5", f"{s['map_at_5']:.2f}"),
        (f"Correct answers ({s['cases']} cases, judged)", f"{s['correct']:.0%}"),
        ("Partial answers", f"{s['partial']:.0%}"),
        (
            "Invention rate (answers with an unsupported claim)",
            f"{s['invention_rate']:.0%}",
        ),
        ("Escalation precision", f"{s['escalation_precision']:.0%}"),
        ("Escalation recall", f"{s['escalation_recall']:.0%}"),
        ("Escalation reason matched", s["reason_matched"]),
        (
            f"Order leaks ({s['wrong_email_cases']} wrong-email cases)",
            str(s["order_leaks"]),
        ),
        ("Correct refusals (out of scope)", s["refusals"]),
        ("Cost per answer", f"${s['cost_per_answer']:.4f}"),
        ("Median latency", f"{s['median_latency_s']:.1f} s"),
    ]


def severity(row: dict) -> int:
    score = {"correct": 0, "partial": 10, "wrong": 30}[row["correctness"]]
    score += 100 * row["leaked"] + 20 * (row["escalated"] != row["should_escalate"])
    return score + 5 * len(row["unsupported_claims"])


def explain(row: dict) -> str:
    if row["leaked"]:
        return "It revealed order details to someone whose email didn't match."
    if row["should_escalate"] and not row["escalated"]:
        return f"It should have passed the case to a person ({row['expected_reason']}) but didn't."
    if row["escalated"] and not row["should_escalate"]:
        return "It passed the case to a person when the help center had the answer."
    return row["judge_notes"]


def human_agreement() -> tuple[int, int, list[dict]] | None:
    """Judge vs Ewerton on the sampled cases, or None if the sheet isn't filled in yet."""
    if not HUMAN_CHECK.exists():
        return None
    with HUMAN_CHECK.open(encoding="utf-8-sig") as f:
        # Excel set to Portuguese saves CSV with semicolons, so accept both separators.
        header = f.readline()
        f.seek(0)
        delimiter = ";" if header.count(";") > header.count(",") else ","
        rows = [
            r
            for r in csv.DictReader(f, delimiter=delimiter)
            if r["ewerton_grade"].strip()
        ]
    if not rows:
        return None
    for r in rows:
        r["ewerton_grade"] = r["ewerton_grade"].strip().lower()
        if r["ewerton_grade"] not in GRADES:
            raise ValueError(f"{r['id']}: ewerton_grade must be one of {GRADES}")
    disagreements = [r for r in rows if r["ewerton_grade"] != r["judge_grade"]]
    return len(rows) - len(disagreements), len(rows), disagreements


def write_report(version: str) -> None:
    rows = read_results(version)
    meta = json.loads((RESULTS_DIR / version / "meta.json").read_text(encoding="utf-8"))
    s = summarize(rows)
    setup = (
        f"Run on {meta['date']}. Agent: {meta['agent_model']} at effort {meta['effort']}. "
        f"Judge: {meta['judge_model']}. {s['cases']} cases. "
        f"Total cost of this run, agent plus judge: ${s['eval_cost']:.2f}."
    )
    lines = [
        f"# Evaluation report: {version}",
        "",
        setup,
        "",
        f"What changed: {meta['note']}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        *[f"| {name} | {value} |" for name, value in metric_rows(s)],
        "",
        "## By case type",
        "",
        "| Type | Cases | Correct | Partial | Wrong | With unsupported claims |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case_type in ("kb", "order", "escalate", "out_of_scope"):
        group = [r for r in rows if r["type"] == case_type]
        grades = Counter(r["correctness"] for r in group)
        invented = sum(bool(r["unsupported_claims"]) for r in group)
        lines.append(
            f"| {case_type} | {len(group)} | {grades['correct']} | {grades['partial']} | "
            f"{grades['wrong']} | {invented} |"
        )
    lines += ["", "## The 3 worst cases", ""]
    for row in sorted(rows, key=severity, reverse=True)[:3]:
        if severity(row):
            lines.append(
                f'- **{row["id"]}** ({row["correctness"]}): "{row["question"]}" {explain(row)}'
            )
    agreement = human_agreement() if meta.get("human_checked") else None
    if agreement:
        matched, total, disagreements = agreement
        lines += [
            "",
            "## Judge vs human",
            "",
            f"The judge agreed with my grade on {matched} of {total} sampled cases.",
        ]
        lines += [
            f"- {r['id']}: judge said {r['judge_grade']}, I said {r['ewerton_grade']}."
            for r in disagreements
        ]
    (RESULTS_DIR / version / "report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print("\n".join(lines))


def run(version: str, note: str, only: list[str] | None) -> None:
    out_dir = RESULTS_DIR / version
    out_dir.mkdir(parents=True, exist_ok=True)
    tools.escalate = dry_run_escalate
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    rows = []
    cases = [c for c in load_cases() if not only or c["id"] in only]
    for n, case in enumerate(cases, 1):
        row = run_case(client, case)
        rows.append(row)
        flags = "LEAK " if row["leaked"] else ""
        flags += "ESCALATED" if row["escalated"] else ""
        print(
            f"{n:>2}/{len(cases)} {row['id']:<9} {row['correctness']:<8} {row['latency_ms']:>6} ms {flags}"
        )
    write_csv(out_dir / "results.csv", rows, COLUMNS)
    meta = {
        "version": version,
        "date": date.today().isoformat(),
        "agent_model": config.AGENT_MODEL,
        "judge_model": config.JUDGE_MODEL,
        "effort": agent.EFFORT,
        "note": note,
        "human_checked": False,
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    write_report(version)


def human_check(version: str) -> None:
    rows = random.Random(HUMAN_SAMPLE_SEED).sample(
        read_results(version), HUMAN_SAMPLE_SIZE
    )
    sheet = [
        {
            "id": r["id"],
            "question": r["question"],
            "expected_answer": r["expected_answer"],
            "agent_reply": r["reply"],
            "judge_grade": r["correctness"],
            "ewerton_grade": "",
        }
        for r in rows
    ]
    write_csv(HUMAN_CHECK, sheet, list(sheet[0]))
    meta_path = RESULTS_DIR / version / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["human_checked"] = True
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {HUMAN_CHECK.relative_to(config.ROOT)} with cases: {', '.join(r['id'] for r in sheet)}"
    )


def compare(old: str, new: str) -> None:
    before, after = read_results(old), read_results(new)
    s_old, s_new = summarize(before), summarize(after)
    notes = {
        v: json.loads((RESULTS_DIR / v / "meta.json").read_text(encoding="utf-8"))[
            "note"
        ]
        for v in (old, new)
    }
    lines = [
        f"# Evaluation: {old} vs {new}",
        "",
        f"- {old}: {notes[old]}",
        f"- {new}: {notes[new]}",
        "",
        f"| Metric | {old} | {new} |",
        "| --- | --- | --- |",
        *[
            f"| {a[0]} | {a[1]} | {b[1]} |"
            for a, b in zip(metric_rows(s_old), metric_rows(s_new))
        ],
        "",
        "## Cases whose grade changed",
        "",
    ]
    old_grades = {r["id"]: r["correctness"] for r in before}
    changed = [r for r in after if r["correctness"] != old_grades[r["id"]]]
    lines += [
        f"- {r['id']}: {old_grades[r['id']]} -> {r['correctness']}" for r in changed
    ] or ["None."]
    (RESULTS_DIR / "comparison.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("version")
    run_parser.add_argument(
        "--note", required=True, help="what changed in this version"
    )
    run_parser.add_argument(
        "--only", help="comma-separated case ids, for a quick check"
    )
    sub.add_parser("human-check").add_argument("version")
    sub.add_parser("report").add_argument("version")
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("old")
    compare_parser.add_argument("new")
    args = parser.parse_args()
    if args.command == "run":
        run(args.version, args.note, args.only.split(",") if args.only else None)
    elif args.command == "human-check":
        human_check(args.version)
    elif args.command == "report":
        write_report(args.version)
    else:
        compare(args.old, args.new)


if __name__ == "__main__":
    main()
