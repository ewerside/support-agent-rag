# Evaluation report: v1

Run on 2026-11-05. Agent: claude-sonnet-5-5 at effort low. Judge: claude-sonnet-5-5. 60 cases. Total cost of this run, agent plus judge: $0.78.

What changed: Baseline: k=5 chunks per search, chunks split by section, effort low, first system prompt.

## Metrics

| Metric | Value |
| --- | --- |
| Retrieval hit@5 (35 help center questions) | 97% |
| Retrieval MAP@5 | 0.88 |
| Correct answers (60 cases, judged) | 85% |
| Partial answers | 15% |
| Invention rate (answers with an unsupported claim) | 7% |
| Escalation precision | 100% |
| Escalation recall | 100% |
| Escalation reason matched | 10/10 |
| Order leaks (2 wrong-email cases) | 0 |
| Correct refusals (out of scope) | 4/5 |
| Cost per answer | $0.0092 |
| Median latency | 4.4 s |

## By case type

| Type | Cases | Correct | Partial | Wrong | With unsupported claims |
| --- | --- | --- | --- | --- | --- |
| kb | 35 | 28 | 7 | 0 | 3 |
| order | 10 | 10 | 0 | 0 | 0 |
| escalate | 10 | 9 | 1 | 0 | 1 |
| out_of_scope | 5 | 4 | 1 | 0 | 0 |

## The 3 worst cases

- **kb-06** (partial): "my tracking says delivered but theres nothing at my door" The reply covers the claim, order number and email, and the replacement or refund, but omits the expected quick checks (around the delivery spot, neighbors, delivery photo, waiting until the end of the next business day) and its order-number example format is not in the evidence.
- **kb-03** (partial): "Whats the cheapest way to ship in the US and how long will it take?" The reply correctly gives Standard shipping at $6.95 and 3 to 5 business days, with all details supported by the evidence, but it omits the expected note that shipping is free on orders over $75, which the evidence doesn't contain.
- **kb-18** (partial): "my machine is 3 years old and broke. can you still fix it and what does it cost?" The reply correctly says out-of-warranty repair is possible and gives the $49/C$65/£39 diagnostic fee, but it omits the credit toward the repair, the customer-paid shipping and the 10 business day turnaround from the expected answer.

## Judge vs human

The judge agreed with my grade on 10 of 10 sampled cases.
