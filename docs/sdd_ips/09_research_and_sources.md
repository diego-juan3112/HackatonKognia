# 09 — Research record and sources

Prepared on 2026-10-09, America/Bogota. External documentation was consulted
for capabilities; local code and measured source responses determine what is
actually available here. No paid model API was called during this planning task.

## Inspected project and user inputs

| Source | Inspection / limitation |
|---|---|
| Local `spike/demo-voz-avatar`, `ff7c2c6` | AGENTS, README, architecture, ports, graph/state, LLM factory, changelog, voice spike and prior voice measurements |
| `origin/docs/contratos`, `aef1196b5a4319985758424cca145d52da2fd083` | Fetched without checkout; inspected AGENTS and the 00–06 documentation structure/contracts |
| `C:/Users/danna/Downloads/V2.xlsx` | Read-only XML extraction; one sheet `01 RETO`; no `02 CRITERIOS` sheet |
| `C:/Users/danna/Downloads/Audios/10-09-2026 08 (mp3cut.net) (1).txt` | Spoken challenge: public web voice agent, API, low latency, function first |
| `C:/Users/danna/Downloads/Audios/10-09-2026 08 (mp3cut.net).txt` | Organizational context; repeated transcription filler |
| `C:/Users/danna/Downloads/Audios/10-09-2026 08.13.txt` | Business motivation, practical understanding, international use cases; noisy transcription |
| Screenshots mentioned in request | Not attached in this conversation; no visual inspection claimed |

Source priority: latest user request/clarification, then the matching challenge
evidence, then repository baseline and historical measurements. Do not treat
spoken examples of appointment booking as permission to implement booking.

## Live public API evidence

[socrata_probe.json](evidence/socrata_probe.json) contains the timestamp,
SDK version, metadata, field names, exact aggregate/filter/page parameters,
results, individual elapsed times and SODA3 status. Credential usage: none.

Observed: 41,427 rows; 9,320 distinct provider codes; 10,921 distinct site codes;
one cutoff group dated 2022-11-05. Nature row counts: 25,067 Privada, 16,174
Pública, 186 Mixta. These are counts of source capacity rows, not provider counts
by nature. A filtered site sample confirms repeated rows by capacity category.

The SDK was installed under the workspace's `.planning_tools/` outside the Git
repository; project dependencies were not changed. The network restriction
required approved read-only external requests. Successful anonymous SODA3 access
is recorded as observed behavior, not advice to bypass the documented token.

Not measured: all-page completeness, site-key uniqueness, actual voice latency,
provider ranking, hosted runtime limits, deployment uptime or vector recall.

## Documentary validation

Validated the 11 Markdown documents, 16 relative links (none broken), two fenced
JSON examples and the saved evidence JSON. `git diff --check` found no whitespace
errors in tracked changes. Application tests were not run because no application
code changed. Root README and AGENTS now point to the additive planning package;
CHANGELOG records its version and explicitly limited implementation status.

## Primary technical sources

| Topic | Source | Use in this plan |
|---|---|---|
| Dataset viewer | [datos.gov.co dataset](https://www.datos.gov.co/Salud-y-Protecci-n-Social/Relaci-n-de-IPS-p-blicas-y-privadas-seg-n-el-nivel/s2ru-bqt6/data_preview) | User-specified dataset; viewer failed in research browser, REST access succeeded |
| Metadata | [Socrata metadata endpoint](https://www.datos.gov.co/api/views/s2ru-bqt6.json) | Actual schema and update timestamp, read through direct HTTP |
| Read endpoint | [SODA resource](https://www.datos.gov.co/resource/s2ru-bqt6.json) | SDK-backed aggregate/filter/page verification |
| SODA3 | [Queries and pagination](https://dev.socrata.com/docs/queries/) | POST, token/auth and page semantics |
| Python SDK | [sodapy maintainer README](https://github.com/afeld/sodapy/blob/main/README.md) | Client/get/get_all/metadata behavior; community ownership |
| Vector search | [pgvector project documentation](https://github.com/pgvector/pgvector) | Exact/approximate retrieval and filtering considerations |
| Durable graph | [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | Checkpoints and conversation state; application still owns idempotency and validation |
| OpenAI voice | [Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations) | Native voice, tools, interruptions |
| Browser voice | [OpenAI WebRTC](https://developers.openai.com/api/docs/guides/voice-webrtc?voice-api=realtime) | Browser transport and temporary authorization pattern |
| Google models | [Gemini model catalog](https://ai.google.dev/gemini-api/docs/models) | Candidate capabilities; not account availability or local benchmark |
| Google voice | [Live capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities) | Model-specific affective dialogue and native audio possibilities |
| Claude tools | [Anthropic tool overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) | Client-side tool execution; separate protocol adapter |
| Grok tools | [xAI tools overview](https://docs.x.ai/developers/tools/overview) | Custom function calls; separate from Groq |
| Interaction patterns | [ElevenLabs conversation flow](https://elevenlabs.io/docs/eleven-agents/customization/conversation-flow) | Interruption, turn-taking and bounded soft timeout inspiration |
| Astro hosting | [Astro on Vercel](https://docs.astro.build/en/guides/deploy/vercel/) | Static frontend deployment |
| Backend hosting | [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [Python runtime](https://vercel.com/docs/functions/runtimes/python) | Entry point and function/runtime constraints |
| Realtime hosting | [Vercel WebSocket guide](https://vercel.com/kb/guide/do-vercel-serverless-functions-support-websocket-connections), [limits](https://vercel.com/docs/limits) | Conflicting documentation; require real deployment capability gate |
| Container fallback | [Azure ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview) | HTTP and WebSocket ingress |
| Later telephony | [Twilio Media Streams](https://www.twilio.com/docs/voice/media-streams) | Separate future channel |

The provider comparison, deadlines, retry limits, latency targets, cache TTLs,
retention defaults and task estimates are this plan's engineering proposals.
They are not vendor guarantees or measurements. No legal or clinical validation
is claimed, and the sentiment feature is not a diagnostic system.
