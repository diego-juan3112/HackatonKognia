# IPS voice agent — SDD implementation package

Version: 1.0.0 · Prepared: 2026-10-09 · Deadline: **16:00 America/Bogota**.
Status: **proposed implementation plan, with verified public API research**.

Build a public Spanish voice assistant that queries Colombia's IPS dataset,
shows its evidence, accepts corrections, and recovers from failed turns.
The user confirmed that actions mean **consulting IPS and correcting the
conversation**. Booking appointments and creating external requests are out of scope.

## The five priorities

1. A working public voice loop, with audible answers and interruption handling.
2. Correct API-backed answers, exact counts, visible source and data cutoff.
3. Conversation state that survives corrections and recoverable failures.
4. Live user/assistant transcript and a lightweight sentiment panel.
5. A team that can explain the selected model, context, tools and measured latency.

**First public skeleton by 10:00; feature freeze at 14:30; release candidate at
15:00; submission by 15:45.** These are planning targets, not completed work.
The available window starts at the user's stated 09:13, totaling 6 h 47 min.

## Read in this order

| Document | Decision it enables |
|---|---|
| [00 Context and scope](00_context_and_scope.md) | What is required and which earlier decisions change |
| [01 Architecture](01_architecture.md) | Where each capability belongs and how the graph runs |
| [02 Tool and state contracts](02_tool_contracts.md) | Exact boundaries for data, tools, models and recovery |
| [03 API and voice events](03_api_and_voice.md) | Frontend/backend integration and cancellation |
| [04 Data and retrieval](04_data_and_retrieval.md) | Socrata SDK, SODA3, exact queries, cache and pgvector |
| [05 Acceptance and measurement](05_acceptance.md) | What must pass before calling the MVP ready |
| [06 Implementation rules](06_rules.md) | SDD workflow and reconciliation with existing rules |
| [07 Models and feedback](07_models_and_feedback.md) | Provider choice, context transfer and useful differentiation |
| [08 Delivery and backlog](08_delivery_and_backlog.md) | Timed tasks, cut lines and issue-ready improvements |
| [09 Research and sources](09_research_and_sources.md) | What was actually inspected and verified |

The numbering follows `origin/docs/contratos` at
`aef1196b5a4319985758424cca145d52da2fd083`; the package is additive under
`docs/sdd_ips/` because the local checkout is `spike/demo-voz-avatar` at
`ff7c2c6`. No branch was switched or merged. The local and reference branches
have different LLM factories and authentication routes; do not mix their
instructions as if they described the same revision.

## Evidence that changes the design

The [saved API probe](evidence/socrata_probe.json) recorded 41,427 capacity rows,
9,320 distinct provider codes and 10,921 distinct site codes. All returned
cutoff groups point to **2022-11-05**. Counts of site codes are not a validated
count of physical sites. The source describes installed capacity, not live
vacancies, appointment availability or current clinical suitability.

Use structured queries for filters and arithmetic. Use embeddings for names
and wording only when they improve retrieval. Keep vector search off the
critical path until the public voice loop works.

## Delivery status

- Completed here: repository/reference review, attachment review, official-source
  research, read-only REST/SDK probes, this SDD package and documentary checks.
- Not completed here: product changes, provider benchmarks, full ingestion,
  embeddings, deployment, live voice acceptance or GitHub issue publication.
- Source attachments contain inconsistent document-upload instructions. The
  current user request and spoken challenge prioritize the IPS API. Preserve
  that scope; ask the organizers whether surprise uploads will still be graded.

Technical documents use English to follow repository conventions. All customer
messages and the demonstration are in Spanish.
