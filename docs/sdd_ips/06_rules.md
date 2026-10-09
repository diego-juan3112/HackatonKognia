# 06 — Implementation rules and SDD workflow

This package specifies the proposed IPS feature. It does not replace the root
AGENTS.md for unrelated work or silently change runtime provider selection.

## Reconciliation with the reference rules

| Existing rule/decision | IPS treatment |
|---|---|
| R-01 / R-03, layering and ports | Preserve dependency inversion and composition-root exception; provider data types stay in adapters |
| R-02 / R-07, generic core / disposable FAQ | Add IPS configuration and peripheral nodes; retire FAQ only when IPS acceptance passes |
| R-04 / D-07, deterministic graph | Preserve; model arguments are proposals validated by code |
| R-05, secrets in config | Preserve; backend environment only, no keys in frontend or traces |
| R-06, no domain logic before challenge | Its condition has ended: user supplies the IPS domain; D-09 records this explicitly |
| R-08, no voice adapter before decision | D-11 proposes the baseline and timed acceptance gate before implementation |
| R-09 / R-16–R-18, doubles and isolated tests | Preserve; live probes remain separate from default tests |
| R-10, new dependencies require discussion | sodapy/HTTP client and voice SDK listed below with reasons; add only selected runtime packages |
| R-11, reviewed tools | Planning used bundled first-party spreadsheet/OpenAI Docs skills and ordinary repository/web tools; no third-party MCP was installed |
| R-12–R-15 / D-05, ingestion and vectors | Preserve repeatability and 768-dim E5; add structured source queries; vector work has a later gate |
| R-19, no full national ID in LLM | Preserve; D-17 proposes no national ID collection for public lookup |
| R-20, changelog | Add date/version and distinguish planned, implemented and verified |
| R-21, manual Terraform apply | Preserve; this task does not apply infrastructure |
| D-03, exclusive Gemini | Proposed replacement D-10: bounded OpenAI fallback; retain Gemini historical measurements as historical |

## Feature rules

| ID | Rule |
|---|---|
| IPS-R01 | Factual claims require evidence from the selected dataset and its cutoff. |
| IPS-R02 | Counts/sums use structured operations with explicit grain and units. |
| IPS-R03 | One foreground turn and one speaking generation per conversation. |
| IPS-R04 | Explicit correction wins; stale results cannot restore superseded facts. |
| IPS-R05 | Two model attempts maximum and two source attempts maximum, inside one shared deadline. |
| IPS-R06 | Tool results are untrusted data; only registered read-only operations execute. |
| IPS-R07 | No raw audio retention by default; keep only necessary demo state with a configured expiry. |
| IPS-R08 | Feelings are uncertain observations; preferences and task success drive adaptation. |
| IPS-R09 | No unattended online prompt rewriting, weight updates or global memory from user feedback. |
| IPS-R10 | New providers and observers must pass capability/schema checks before receiving traffic. |
| IPS-R11 | Cache/vector coverage and source freshness must be visible, never inferred. |
| IPS-R12 | At 14:30 freeze features; at 15:00 choose a release candidate. |

For the public demo, avoid logging raw audio or unnecessary personal utterances.
Keep transient transcript/session records for at most 24 hours by proposed
configuration, with an explicit cleanup task and a user-visible reset. This is
a product minimization default, not a legal compliance certification.

## Dependency decisions

- `sodapy==2.2.0` was installed only in an isolated research folder outside the
  repository. It proved SDK access. Select it for ingestion/compatibility if useful;
  it is synchronous and must not block the event loop.
- An async HTTP client is preferred for the SODA3 hot path. Reuse an existing
  dependency if present; do not add both SDK and client without a real need.
- Azure Speech is the proposed reused voice provider. Validate package size,
  Linux/native dependencies, runtime and connection reuse before locking deployment.
- Gemini/OpenAI integrations must match the chosen branch's LangChain versions.
  Do not mass-upgrade packages to add Claude/Grok during the deadline.
- pgvector remains the storage capability. E5 query inference is optional until
  a compatible deployment path exists; keep the embedding-space contract stable.

## SDD cycle

1. Select implementation baseline and accept the scope/decision register.
2. For each task, read its F-ID, contract and acceptance case before coding.
3. Record changed contract/version before changing any public payload or behavior.
4. Implement the smallest vertical slice, then validate contract behavior and
   real-provider behavior at the designated gate.
5. Attach evidence to the task; update changelog and deployment README.
6. Ship the accepted P0 slice before picking any backlog item.

The user requested planning in this turn. The root workflow's plan-before-code
rule is satisfied by preparing a reviewable plan; this delivery makes no
production implementation or deployment claim.

When several coding assistants contribute later, assign distinct file ownership
and exchange the same schema version. One integrator owns contracts, migrations
and graph wiring. A provider agent cannot unilaterally change UI event shapes.
This is guidance for future coordination, not a claim that subagents ran here.

## Definition of done for an implementation task

Implemented code + contract link + relevant passing checks + failure behavior
+ real deployment evidence where applicable + dated changelog. Blank result
tables and planned model names must not be marked verified.
