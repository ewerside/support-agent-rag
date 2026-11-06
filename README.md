# Support agent with RAG and an evaluation report

A support agent for a fictional coffee gear store that answers from the help center, looks up orders and opens a HubSpot ticket when a person is needed.

## Notes

- HubSpot moved private apps to "Legacy apps", so I used a Service Key instead. Service keys have no `tickets` scope, so the key uses `crm.objects.tickets.read` and `crm.objects.tickets.write`.
- I created a separate key (`portfolio-support-agent`) instead of adding tickets scopes to the key from my lead routing project, so the two projects don't share a credential.
