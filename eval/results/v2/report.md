# Evaluation report: v2

Run on 2026-11-06. Agent: claude-sonnet-5-5 at effort low. Judge: claude-sonnet-5-5. 60 cases. Total cost of this run, agent plus judge: $1.07.

What changed: One change from v1: each chunk is a whole article instead of one section, so search_kb returns 5 full articles. Everything else is the same as v1.

## Metrics

| Metric | Value |
| --- | --- |
| Retrieval hit@5 (35 help center questions) | 100% |
| Retrieval MAP@5 | 0.95 |
| Correct answers (60 cases, judged) | 100% |
| Partial answers | 0% |
| Invention rate (answers with an unsupported claim) | 10% |
| Escalation precision | 100% |
| Escalation recall | 100% |
| Escalation reason matched | 10/10 |
| Order leaks (2 wrong-email cases) | 0 |
| Correct refusals (out of scope) | 5/5 |
| Cost per answer | $0.0116 |
| Median latency | 4.2 s |

## By case type

| Type | Cases | Correct | Partial | Wrong | With unsupported claims |
| --- | --- | --- | --- | --- | --- |
| kb | 35 | 35 | 0 | 0 | 3 |
| order | 10 | 10 | 0 | 0 | 1 |
| escalate | 10 | 10 | 0 | 0 | 2 |
| out_of_scope | 5 | 5 | 0 | 0 | 0 |

## The 3 worst cases

- **kb-05** (correct): "If I order at 3pm on a tuesday does it still ship today?" The reply gives the 1 pm local warehouse time cutoff and says a 3 pm order leaves the next business day, matching the expected answer; the 'Probably not' hedge is minor, and naming Wednesday assumes no holiday, which the evidence doesn't confirm.
- **kb-18** (correct): "my machine is 3 years old and broke. can you still fix it and what does it cost?" The reply matches the expected answer on the diagnostic fees in all three currencies, the credit toward the repair, customer-paid shipping and the 10 business day turnaround. The only unsupported part is the stated reason that the repair cost depends on the fault, though the evidence does say a quote is emailed after diagnosis.
- **kb-26** (correct): "I bought a kettle last week and now it's cheaper on your site. can I get the difference back?" The reply gives the key facts from the expected answer (14 days, refund of the difference to the original payment method, order number), but it also asks for the checkout email, which the evidence does not require.
