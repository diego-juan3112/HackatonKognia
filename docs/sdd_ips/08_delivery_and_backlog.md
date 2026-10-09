# 08 — Delivery plan, deployment gates and backlog

Deadline: **2026-10-09 16:00 America/Bogota**. Planning window starts at the
user's reported 09:13. Team size is unknown. Roles below are ownership slots,
not an assumption that three developers are available.

## Critical path

| Time | Outcome | Role / dependency | Cut rule |
|---|---|---|---|
| 09:13–09:40 | Accept scope, choose code baseline, validate API/schema and credentials | Integrator; T-01/T-02 | No extra domain or provider |
| 09:40–10:00 | Public Astro skeleton, backend health, session, one real source query | Deploy + backend; T-03 | Hosting must be tested before feature work expands |
| 10:00–11:00 | One public spoken question → tool → grounded spoken answer | Voice + backend; T-04/T-05 | Lock working voice baseline by 11:00 |
| 11:00–12:00 | Filters/counts/context correction and evidence panel | Backend + UI; T-05/T-06 | No vector dependency for exact questions |
| 12:00–13:00 | Interruptions, bounded errors, transcript and sentiment estimate | Voice/UI + integrator; T-07/T-08 | One model fallback only |
| 13:00–14:00 | Run acceptance; tune bottleneck; optional lexical repair polish | All roles; T-09 | Vector/shadow work only if every earlier P0 works |
| 14:00–14:30 | Fix failures; complete README and demonstration narrative | Integrator; T-10 | No new dependencies |
| 14:30–15:00 | Feature freeze, public external-browser rehearsal and release candidate | Integrator/deploy | Revert risky enhancements if necessary |
| 15:00–15:45 | Ten-minute rehearsal, recovery rehearsal, repository access and submission | Team | Maintain a known working deployment |
| 15:45–16:00 | Delivery buffer | Team | No architecture migration |

If starting late, preserve the final 90 minutes and remove optional work first.
With one implementer, do T-01→T-03→T-04/T-05 as one thin slice, then T-06→T-10.
With two, split data/backend and UI/voice; the backend owner also integrates.
With three, a third owner handles deployment/acceptance. All share the same
contracts; do not delegate conflicting edits to graph wiring or migrations.

## Implementable tasks

| ID | Deliverable / files | Dependencies | Contract and acceptance |
|---|---|---|---|
| T-01 | Select baseline; record D-09–D-18 and scope in root docs | none | F-01–F-08; discrepancy list resolved |
| T-02 | Socrata adapter + schema vocabulary + grain profile | T-01 | C-IPS; A-03–A-08, A-18 |
| T-03 | Public Astro/FastAPI health and external PostgreSQL, opaque sessions | T-01 | C-API; A-01, A-17 |
| T-04 | Voice adapter, mic island, warm TTS and playback | T-03 | C-VOICE; A-02, A-13 |
| T-05 | IPS graph and exact tools; brief and evidence rendering | T-02/T-03 | C-IPS/C-EVIDENCE; A-03–A-08 |
| T-06 | Canonical context, correction UI and checkpoint restoration | T-05 | C-STATE; A-09/A-10/A-17 |
| T-07 | Cancel, timeout, one fallback, stale-cache indication | T-04/T-06 | C-RECOVERY/C-MODEL; A-11/A-12/A-16 |
| T-08 | Small affect estimate and explicit tone preference | T-06 | C-AFFECT; A-14 |
| T-09 | Contract cases + public latency/quality measurement | T-02–T-08 | A-01–A-18; record failures and actual results |
| T-10 | Release README, demo script, tested public/repo URLs | T-09 | Rehearsal and delivery evidence |

These tasks are all **planned**, not completed implementation. SDK exploration
reduces risk in T-02 but does not complete its production adapter or contracts.

## Vercel-first deployment gate

1. Deploy Astro static frontend and a lean FastAPI backend as separate projects
   if needed. Configure public API base URL, backend-only secrets, explicit CORS
   and durable external PostgreSQL with pgvector capability.
2. Prove one request, one audio response and a ten-minute reconnectable session
   using the actual plan/runtime. Record function duration, package limits,
   concurrency and DB connection-pool behavior for that account.
3. Keep E5/PyTorch/model downloads out of the Vercel request bundle. Start with
   direct queries, lexical resolution and PostgreSQL caching. A vector-enabled
   function needs a remotely accessible compatible query embedder.
4. For streaming, prefer the minimal transport the implementation already supports.
   SSE carries text/events; audio capture and delivery require their own path.
   Do not assume SSE itself transports a bidirectional microphone stream.
5. Timebox failed packaging/voice transport work to **20 minutes**. Switch the
   backend to the repository's Azure Container Apps path if Vercel cannot run
   the actual dependencies; keep Astro on Vercel.

Current Vercel documentation has conflicting pages: the opened
[WebSocket guide](https://vercel.com/kb/guide/do-vercel-serverless-functions-support-websocket-connections)
describes native support in public beta, including ASGI/FastAPI, while the
[limits page](https://vercel.com/docs/limits) surfaced an older contrary statement.
Therefore do not repeat a categorical “Vercel cannot do WebSockets” claim, and
do not assume the beta works for the chosen account. Make a deployed smoke
test and reconnection check the gate. Connections and SSE remain duration-bound;
session state must be external.

[Astro's Vercel guide](https://docs.astro.build/en/guides/deploy/vercel/)
supports a static-site deployment without an SSR adapter. Use SSR only when a
specific feature requires it. [Vercel's FastAPI guide](https://vercel.com/docs/frameworks/backend/fastapi)
describes the function deployment model; preserve the existing ASGI application
through the supported entry point rather than assuming the repository layout
is detected automatically.

## Azure fallback and later telephony

Azure fallback gate: container builds, copies configuration/migrations,
connects to durable PostgreSQL, supports required HTTPS/WebSocket traffic,
has a verified startup path and a warmed voice client. Use a supported region
for the actual subscription. Prior project restrictions are historical evidence,
not a live resource inventory. If permitted by the budget, keep a warm instance
during judging. Resource provisioning and Terraform apply remain deliberate
implementation actions, not part of this planning delivery.

[Azure Container Apps ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview)
documents external HTTP ingress and WebSocket support.
[Twilio Media Streams](https://www.twilio.com/docs/voice/media-streams)
provides a later telephony transport. A later integration must address signature
validation, call/stream IDs, its audio format, interruption clearing and cost.
It reuses the same graph/tools but is not just a browser URL setting.

## Issue-ready backlog

The items below are local issue drafts; no GitHub issues were created.

| ID / title | Priority and dependency | Definition of done | Estimated effort |
|---|---|---|---|
| B-01 — Hybrid entity retrieval with pgvector | P1 after T-09 | Compatible E5 query compute, versioned site vectors, geographic constraints, measured entity recall vs lexical baseline, no aggregate regression | 2–4 h |
| B-02 — Gemini/OpenAI shadow comparison | P1 after T-09 | Same minimized context/evidence, 10% sample cap, no duplicate tools, comparison report and budget | 1–2 h |
| B-03 — Claude and Grok adapters | P2 after B-02 | Capability checks, provider-specific tool translation, same acceptance set, measured cost/latency | 2–4 h |
| B-04 — Native speech-to-speech spike | P2 after release | Compare OpenAI Realtime/Gemini Live with baseline using Spanish, tools, cancellation and actual first-audio latency | 2–4 h |
| B-05 — Full paginated snapshot and refresh | P1 after T-02 | Stable IDs, count/version reconciliation, idempotent upsert, atomic promotion, missing-row handling | 1–3 h |
| B-06 — Reviewed feedback evaluation loop | P1 after T-08/T-09 | Error taxonomy, anonymized cases, prompt versioning, regression report and rollback | 1–2 h |
| B-07 — Robust cloud STT / human diarization | P1 if browser gate fails, else P2 | Multi-browser capture; actual multi-human diarization evaluated separately from role labels | 2–4 h |
| B-08 — Azure deployment automation | P2 after working container deployment | Reproducible infrastructure, secrets, health, rollout/rollback and cost review; manual apply | 2–4 h |
| B-09 — Twilio inbound phone channel | P2 after B-08 or equivalent stable backend | Real test call, correct codec, interruption/reconnect, signed webhook validation, spend cap | 3–6 h |
| B-10 — Adaptive interaction study | P2 after B-06 | Compare explicit tone preference vs transcript/acoustic estimates, disclosure, measurable benefit, no diagnosis | 2–4 h |
| B-11 — Surprise document ingestion | Conditional, organizer clarification required | Separate source scope, supported file limits, provenance, no contamination of IPS answers | Re-estimate after scope clarification |

Effort ranges are planning estimates, not commitments. None should consume the
submission buffer. A generic new avatar is deliberately absent from this backlog.

## Ten-minute demo

- 0:00–1:00: open public URL, start voice, hear data brief and cutoff.
- 1:00–3:00: ask a directory question and a precise filtered count; show evidence.
- 3:00–5:00: interrupt, correct a municipality, then ask “¿y las privadas?”.
- 5:00–6:30: ask an unsupported live-availability question; show an honest limit.
- 6:30–8:00: inspect user/assistant transcript and request a more direct tone.
- 8:00–10:00: explain graph, source grain, context, provider choice and actual
  latency measurements. Demonstrate a controlled recovery only if reliable.

README release checklist: public URL and accessible repository, actual deployed
stack/model IDs, one architecture diagram, start/reset instructions, known
browser limits, historical source cutoff, benchmark results, and declaration
of AI-generated work. Do not publish placeholder URLs or planned features as done.
