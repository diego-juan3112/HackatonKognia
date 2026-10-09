# 04 — Socrata integration, exact queries and pgvector

## Verified source facts

Read-only calls on 2026-10-09 at approximately 09:17 America/Bogota are saved in
[evidence/socrata_probe.json](evidence/socrata_probe.json).

| Observation | Result |
|---|---|
| Dataset | `s2ru-bqt6`, source REPS |
| Capacity rows | 41,427 |
| Distinct `c_digo_prestador` | 9,320 |
| Distinct `c_digo_sede` | 10,921; not yet validated as physical-site identity |
| Distinct cutoff groups | One: `Fecha corte REPS: Nov  5 2022  1:37PM` |
| Nature categories | Privada, Pública, Mixta |
| SDK | sodapy 2.2.0: metadata, aggregate, filter, two pages succeeded |
| SODA3 anonymous POST | HTTP 200 in this probe; not a future access guarantee |

The observed aggregate took 323 ms and two tiny pages 184/195 ms from this
machine. These are single query observations, not p50/p95 or application voice
latency. No full ingestion, embedding generation or source uniqueness audit ran.

## Actual field mapping

| Canonical field | Socrata name | Rule |
|---|---|---|
| department / municipality | `departamento` / `municipio` | Preserve display spelling; normalized lookup separately |
| provider code / name | `c_digo_prestador` / `nombre_prestador` | Store identifier as string; don't treat as a quantity |
| tax ID / check digit | `nit_ips` / `num_digito_verificion` | Exclude from default voice/context unless needed |
| nature / recorded level | `naturaleza` / `num_nivel_atencion` | Nullable level; no inference from name |
| site code / site number / site name | `c_digo_sede` / `n_mero_sede` / `nom_sede_ips` | Preserve leading zero in site number |
| address / email / phone | `direcci_n` / `email` / `tel_fono` | Historical contact data; keep as strings |
| manager | `gerente` | Not needed for MVP retrieval/context |
| capacity group / type | `nom_grupo_capacidad` / `nom_descripcion_capacidad` | Required distinction for sums |
| quantity | `num_cantidad_capacidad_instalada` | Parse decimal; null is not zero |
| cutoff / provenance | `fecha_corte` / `fuente` | Keep original text alongside normalized date |

Metadata describes codes as numbers, but JSON encodes them as strings. Do not
round, infer missing leading zeros or change source identifiers. There are no
geographic coordinates, opening hours, live vacancies or appointment slots in
the inspected schema. “Nearest” needs geocoding not currently available.

## SDK and SODA versions

The portal's browser page is a dataset viewer. The application consumes its
API from the backend; it does not scrape the viewer or expose an application
token to browser code.

Verified SDK reproduction (isolated probe, not an added runtime dependency):

```python
from sodapy import Socrata

with Socrata("www.datos.gov.co", None, timeout=20) as client:
    counts = client.get(
        "s2ru-bqt6",
        select="count(*) as rows,count(distinct c_digo_prestador) as providers",
    )
    page = client.get("s2ru-bqt6", limit=2, offset=0, order=":id")
```

`sodapy` is a community Python SODA client, not a guarantee of native SODA3
support. Its verified `get` path uses `/resource/s2ru-bqt6.json`. In async
FastAPI, run this synchronous client in a bounded thread executor with SDK
timeout, or prefer the existing async HTTP client for SODA3. Cancelling the
await does not necessarily stop a blocking worker thread.

Preferred deployed SODA3 request:

```http
POST https://www.datos.gov.co/api/v3/views/s2ru-bqt6/query.json
X-App-Token: <server-side application token>
Content-Type: application/json

{"query":"SELECT count(*) AS rows","page":{"pageNumber":1,"pageSize":1}}
```

[Socrata's query documentation](https://dev.socrata.com/docs/queries/) requires
authenticated requests or a valid application token and describes POST plus
one-based page numbers. Follow that documented contract despite this host's
successful anonymous probe. Do not claim that anonymous SODA2/SODA3 access is
universally guaranteed. Never ask users to put account passwords in frontend code.

## Direct queries and pagination

MVP tool calls query the source directly with narrow filters/projections and
server-side aggregates. Always make real source calls during the demonstration;
cached results disclose their origin and fetch time. A database snapshot alone
must not be represented as a live API query.

For ingestion, fetch batches (initial target 1,000), ordered by source `:id`,
until a short page. In SODA3 use `page`; in SDK/SODA2 use limit/offset. Persist
source row ID, raw row, fetch time, cutoff and a content hash. Verify metadata
version/count before and after pagination; if changed, restart or report an
inconsistent snapshot. Checkpoint completed pages, bounded backoff on 429/5xx,
and atomically promote only a fully reconciled snapshot. Delete missing records
only after successful complete reconciliation, never after a partial download.

Probe demonstrated distinct rows across two tiny pages, not production-scale
pagination completeness. Add that integration acceptance before full snapshot use.

## Data grain and counting

A source row describes a capacity category for a provider/site/cutoff. The
sample hospital appears on several rows for Adultos and TPR beds. Therefore:

- Count providers with distinct `c_digo_prestador` after selected filters.
- Candidate site identity: provider code + site code + site number. Validate
  functional consistency of name/address/municipality before materializing sites.
  If duplicates conflict, expose the ambiguity instead of merging blindly.
- Store raw capacity rows by source row ID. Do not deduplicate equal quantities
  across categories. Check candidate natural key `(site_key, group, type, cutoff)`
  for duplicates before summing; reconcile or report unknown if ambiguous.
- Sum only one named compatible capacity unit/type and cutoff. Never equate
  installed capacity with availability today.
- Exact national totals cannot be computed from a top-k retrieval result or a
  paginated first page. Use source aggregate or a verified complete snapshot.

## Minimal storage and cache

Proposed migration adds `source_snapshots`, `ips_capacity_rows` (JSONB + typed
filter columns), `query_cache`, `turn_events` and `feedback_events`; reuse
existing conversation/checkpointer tables. A later migration can materialize
`ips_sites` after key validation. Parameterized SQL only.

Cache key: dataset + normalized validated filters + operation + selected fields
+ page/cursor + source snapshot version. Store data and evidence together.
Proposed fresh TTL: 15 minutes; explicit stale fallback up to 24 hours, solely
for historical directory queries. Fetch age and source cutoff are different.
Failed/partial/ambiguous results are not reusable successful responses.

## Vectorization strategy and decision gate

**P0:** structured API queries plus PostgreSQL cache and a small exact vocabulary
of municipalities, provider/site names and capacity labels. Normalization and
lexical matching resolve most transcription errors cheaply.

**P1 after the public loop works:** one concise document per validated site,
containing name, locality, nature and recorded capacity labels, with row IDs and
cutoff in metadata. Batch E5 `passage:` embeddings outside request handling;
use matching `query:` embeddings and keep 768 dimensions. Avoid embedding each
repeated phone/address/capacity row independently or indexing personal dialogue.

Combine exact geographic filters with lexical candidates and optional vector
candidates. Fetch candidate details from the source/cache and enforce the same
constraints again. Start with a small evaluated corpus, then expand; surface
partial corpus coverage. Vector similarity suggests a candidate, not truth.

[pgvector](https://github.com/pgvector/pgvector) supports exact and approximate
search and explains filtered approximate-index tradeoffs. Proposed policy:
measure exact search first; introduce HNSW only if latency/recall justify it.
If filters eliminate ANN candidates, widen the search or fall back to exact
filtered lookup, rather than reporting a false absence.

Local E5 inference has substantial package/model weight. With FastAPI on Vercel,
keep semantic retrieval disabled until a compatible remote embedding adapter
or a container worker is available. Precomputing documents still leaves query
embedding compute to solve. Changing to an API embedding model requires a new
versioned column/index, matching query model and complete re-embedding, even if
its dimension also happens to be 768. Never mix embedding spaces.
