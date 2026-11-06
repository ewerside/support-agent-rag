# Evaluation: v1 vs v2

- v1: Baseline: k=5 chunks per search, chunks split by section, effort low, first system prompt.
- v2: One change from v1: each chunk is a whole article instead of one section, so search_kb returns 5 full articles. Everything else is the same as v1.

| Metric | v1 | v2 |
| --- | --- | --- |
| Retrieval hit@5 (35 help center questions) | 97% | 100% |
| Retrieval MAP@5 | 0.88 | 0.95 |
| Correct answers (60 cases, judged) | 85% | 100% |
| Partial answers | 15% | 0% |
| Invention rate (answers with an unsupported claim) | 7% | 10% |
| Escalation precision | 100% | 100% |
| Escalation recall | 100% | 100% |
| Escalation reason matched | 10/10 | 10/10 |
| Order leaks (2 wrong-email cases) | 0 | 0 |
| Correct refusals (out of scope) | 4/5 | 5/5 |
| Cost per answer | $0.0092 | $0.0116 |
| Median latency | 4.4 s | 4.2 s |

## Cases whose grade changed

- kb-03: partial -> correct
- kb-06: partial -> correct
- kb-18: partial -> correct
- kb-21: partial -> correct
- kb-23: partial -> correct
- kb-28: partial -> correct
- kb-31: partial -> correct
- esc-03: partial -> correct
- oos-03: partial -> correct

## Metrics that got worse in v2

- Invention rate: 7% -> 10%
- Cost per answer: $0.0092 -> $0.0116

## Judge vs human

On 10 sampled v1 cases, the judge agreed with my grade on 10.
