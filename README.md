# Support agent with RAG and an evaluation report

A support agent for a fictional coffee gear store that answers from the help center, looks up orders and opens a HubSpot ticket when a person is needed.

## Notes

- The plan used the name Kestrel Coffee Gear, but Kestrel Coffee Roasters is a real roaster in Vermont that also sells coffee subscriptions. I renamed the store to Wrenfield Coffee Gear, and order numbers use `WCG-10001` instead of `KCG-10001`.

- The tables live in a `support_agent` schema, not `public`. My Supabase database is shared with other portfolio projects, and Supabase exposes `public` through its REST API.
- In fastembed 0.9.1, `query_embed` for `bge-small-en-v1.5` gives the same vector as `passage_embed`. The model card recommends the instruction "Represent this sentence for searching relevant passages: " for short queries, so I add it to queries myself. On the 40 article titles used as queries, it moved the right article to first place in 40 of 40 cases instead of 39.
- HubSpot moved private apps to "Legacy apps", so I used a Service Key instead. Service keys have no `tickets` scope, so the key uses `crm.objects.tickets.read` and `crm.objects.tickets.write`.
- The plan asked for a forced `grade` tool for the judge. Claude Sonnet 5.5 rejects forced tool use with a 400, so the judge returns the same three fields through structured output (`output_config.format` with a JSON schema).
- The evaluation doesn't open real HubSpot tickets. It swaps `escalate` for a stub, because what it measures is the decision to escalate and the reason. Ticket creation is tested on its own in the chat.
- HubSpot now documents date-versioned paths like `/crm/objects/2026-09/tickets`. I kept the `/crm/v3/...` paths from the plan because they still work, and switching is a one-line change per call.
- I created a separate key (`portfolio-support-agent`) instead of adding tickets scopes to the key from my lead routing project, so the two projects don't share a credential.
