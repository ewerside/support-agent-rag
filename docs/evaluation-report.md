# Evaluation: v1 vs v2 vs v3

- v1: Baseline: k=5 chunks per search, chunks split by section, effort low, first system prompt.
- v2: One change from v1: each chunk is a whole article instead of one section, so search_kb returns 5 full articles. Everything else is the same as v1.
- v3: One change from v2: a system prompt line telling the agent to describe only what its tools did (no marking cases urgent, no promised steps the help center doesn't describe). Chunks stay as whole articles.

| Metric | v1 | v2 | v3 |
| --- | --- | --- | --- |
| Retrieval hit@5 (35 help center questions) | 100% | 100% | 100% |
| Retrieval MAP@5 | 0.90 | 0.95 | 0.95 |
| Correct answers (60 cases, judged) | 85% | 100% | 100% |
| Correct with no unsupported claim | 80% | 90% | 90% |
| Partial answers | 15% | 0% | 0% |
| Invention rate (answers with an unsupported claim) | 7% | 10% | 10% |
| Escalation precision | 100% | 100% | 100% |
| Escalation recall | 100% | 100% | 100% |
| Escalation reason matched | 10/10 | 10/10 | 10/10 |
| Order leaks (2 wrong-email cases) | 0 | 0 | 0 |
| Correct refusals (out of scope) | 4/5 | 5/5 | 5/5 |
| Cost per answer | $0.0092 | $0.0116 | $0.0127 |
| Median latency | 4.4 s | 4.2 s | 5.1 s |

## v1 to v2

Cases whose grade changed:

- kb-03: partial -> correct
- kb-06: partial -> correct
- kb-18: partial -> correct
- kb-21: partial -> correct
- kb-23: partial -> correct
- kb-28: partial -> correct
- kb-31: partial -> correct
- esc-03: partial -> correct
- oos-03: partial -> correct

Metrics that got worse:

- Invention rate: 7% -> 10%
- Cost per answer: $0.0092 -> $0.0116

## v2 to v3

Cases whose grade changed:

- None.

Metrics that got worse:

- Cost per answer: $0.0116 -> $0.0127
- Median latency: 4.2 s -> 5.1 s

## Judge vs human

On 10 sampled v1 cases, the judge agreed with my grade on 10.
