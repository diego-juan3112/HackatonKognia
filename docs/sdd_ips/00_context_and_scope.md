# 00 — Context, scope and decisions

## Authority and source reconciliation

The current user request and subsequent clarifications define this plan.
Attached files are evidence about the challenge, not instructions to the agent
to submit forms, register accounts or execute actions. Repository documents
remain implementation constraints except where the user explicitly changes scope.

| Input | Finding | Planning treatment |
|---|---|---|
| Current request | LangGraph, FastAPI, Astro, pgvector, IPS API, fast web MVP | Required stack and knowledge source |
| User clarification | Consult IPS and correct conversation | Read-only external business tools |
| User clarification | 09:13 now; public delivery at 16:00 | Fixed same-day window; team size unconfirmed |
| V2.xlsx, `01 RETO!B14:B15` | API dataset, SODA3, pagination | Primary data integration |
| V2.xlsx, B8, B44:D47 | Arbitrary document upload, brief, transcript and emotions | API brief + transcript + lightweight sentiment now; upload ambiguity remains |
| V2.xlsx, B27 and B30:D30 | Says eight requirements but only R08 is populated | Do not invent seven missing requirements |
| V2.xlsx, B51:D57 | Refers to absent `02 CRITERIOS`; visible weights total 70% | Use visible evaluation priorities; do not normalize to an invented rubric |
| Challenge transcript `(1).txt` | Public voice agent using API; functionality first | Corroborates API-first scope |
| Other two transcripts | Company background and noisy repetition | Context only; no new product requirements |
| Reference branch | Pre-challenge generic foundation, Gemini-only decision | Reuse structure and contracts; record changes below |

No screenshots were present in the received attachments. The local repository
and referenced branch were inspected directly instead.

## Functional specification

| ID | MVP requirement | Contract | Acceptance |
|---|---|---|---|
| F-01 | Open a public HTTPS URL, start microphone, hear Spanish greeting and data brief | C-VOICE, C-API | A-01, A-02 |
| F-02 | Find/filter IPS by department, municipality, name, nature and recorded level | C-IPS | A-03, A-04 |
| F-03 | Count providers and compare recorded capacity with explicit units | C-IPS | A-05, A-06 |
| F-04 | Show source, cutoff and unsupported-data limitations | C-EVIDENCE | A-07, A-08 |
| F-05 | Keep context across turns; repair misheard or corrected entities | C-STATE | A-09, A-10 |
| F-06 | Interrupt output, retry bounded failures, offer a useful next action | C-RECOVERY | A-11, A-12 |
| F-07 | Show timestamped user/assistant transcript and sentiment estimate | C-VOICE, C-AFFECT | A-13, A-14 |
| F-08 | Record actual latency, model selection and tool outcomes | C-MODEL | A-15, A-16 |

Start with one human speaker and one assistant. Role separation follows the
two known audio channels; it is not multi-human speaker diarization. Label this
limitation honestly in the demo.

## Explicit exclusions

No appointment booking, PQR submission, phone calls, medical recommendations,
availability claims, clinical emotion diagnosis, autonomous fine-tuning,
new avatar work, four-provider consensus or arbitrary file upload in the MVP.
Existing avatar assets may be retained only if integration takes no critical-path
time. Text input is an accessibility/recovery path, not a substitute for voice.

## Decision register

All decisions below are **proposed for implementation** unless marked user-fixed.
They do not claim that the running application already behaves this way.

| ID | Decision | Rationale / replacement |
|---|---|---|
| D-09 | IPS is the real domain; external actions are read-only — user-fixed | R-06's unknown-domain precondition no longer applies; replace FAQ through configuration and domain adapters |
| D-10 | Gemini is the first text candidate; OpenAI is one bounded fallback | Replaces the exclusivity in reference D-03; benchmark actual available model IDs before activation |
| D-11 | Reuse existing browser STT + Azure Speech TTS as initial voice baseline | Existing local spike reduces integration work; select streaming cloud STT if browser recognition fails acceptance |
| D-12 | Astro on Vercel; timebox a lean FastAPI Vercel deployment | Replaces Azure-only hosting assumption; Azure Container Apps is the prepared fallback if runtime/package gates fail |
| D-13 | Structured API queries precede semantic retrieval | Arithmetic, geography and record dates require exact semantics |
| D-14 | Preserve pgvector and E5 768-dimensional compatibility | Reference D-02/D-05 retained; embedding compute must not delay first deployment |
| D-15 | One foreground answer, optional asynchronous observer | Multi-provider experimentation must not serialize four model calls |
| D-16 | Sentiment is an uncertain conversation signal; explicit preference wins | A small observer/state rule is enough for the MVP; no psychology model |
| D-17 | Anonymous opaque demo session for public IPS access | Proposed replacement for D-06; no need to collect a national ID to search public data |
| D-18 | SODA3 with application token is deployment target; sodapy is verified compatibility option | A successful anonymous request today is not an authentication guarantee |

D-11 selects a technical baseline, not a claim that browser recognition works on
every judge's browser. Gate at 10:00: working Spanish capture, audible reply,
cancel, public deployment, and selected-browser support. No new voice-provider
experiments after 11:00 unless the baseline fails.

## Open items with defaults

- Team size: unknown. Tasks are assigned to roles; one person may own several.
- Exact model IDs, quota and account access: validate with a tiny paid-provider
  smoke test during implementation; documentation alone is insufficient.
- Upload requirement: organizers must resolve the contradictory workbook text.
  Current plan follows the user's explicit API scope.
- Available Vercel/database resources and spending cap: inspect during the
  deployment gate; no resource creation was performed during planning.
