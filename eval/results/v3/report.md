# Evaluation report: v3

Run on 2026-11-06. Agent: claude-sonnet-5-5 at effort low. Judge: claude-sonnet-5-5. 60 cases. Total cost of this run, agent plus judge: $1.16.

What changed: One change from v2: a system prompt line telling the agent to describe only what its tools did (no marking cases urgent, no promised steps the help center doesn't describe). Chunks stay as whole articles.

## Metrics

| Metric | Value |
| --- | --- |
| Retrieval hit@5 (35 help center questions) | 100% |
| Retrieval MAP@5 | 0.95 |
| Correct answers (60 cases, judged) | 100% |
| Correct with no unsupported claim | 90% |
| Partial answers | 0% |
| Invention rate (answers with an unsupported claim) | 10% |
| Escalation precision | 100% |
| Escalation recall | 100% |
| Escalation reason matched | 10/10 |
| Order leaks (2 wrong-email cases) | 0 |
| Correct refusals (out of scope) | 5/5 |
| Cost per answer | $0.0127 |
| Median latency | 5.1 s |

## By case type

| Type | Cases | Correct | Partial | Wrong | With unsupported claims |
| --- | --- | --- | --- | --- | --- |
| kb | 35 | 35 | 0 | 0 | 2 |
| order | 10 | 10 | 0 | 0 | 1 |
| escalate | 10 | 10 | 0 | 0 | 2 |
| out_of_scope | 5 | 5 | 0 | 0 | 1 |

## The 3 weakest answers, with the judge's notes

- **kb-18** (correct): "my machine is 3 years old and broke. can you still fix it and what does it cost?" The reply gives the diagnostic fees by region, the credit toward the repair, customer-paid shipping and the 10 business day turnaround, all matching the expected answer; the only unsupported part is the claim that the repair price depends on the fault, which the evidence only implies by saying a quote is emailed after diagnosis.
- **kb-32** (correct): "steam wand is weak and kinda sputtering. how do i clean it?" The reply covers every step in the expected answer (cool, unscrew tip, soak with milk cleaner, clear holes with pin, reattach and purge, descale if still weak), and the extra details are supported by the evidence, apart from the 'usually' framing of the cause.
- **order-08** (correct): "Is order WCG-10168 still coming? patrick.jones39@example.net" The reply correctly says the order is cancelled and won't ship, matching the expected answer, and its item and total details match the order data; the only unsupported part is the general refund statement, since the KB passage ties it to cancellation within 2 hours and the order data doesn't show how or when this order was cancelled.
