/**
 * Backend access with a mock fallback.
 *
 * If PUBLIC_API_URL is set, every call goes to the FastAPI backend (docs/08 §1).
 * If it is empty, recorded envelopes from web/mocks/ are served and the UI labels
 * them as recorded samples. A failing backend is never papered over with a mock:
 * it yields `status: "unavailable"` (docs/09 §5, R-22).
 */
import briefMock from "../../mocks/brief.json";
import toolMocks from "../../mocks/tool-results.json";
import type { CacheStatus, DatasetBrief, EvidenceEnvelope, ToolCallPayload } from "./types";

export const API_URL: string = (import.meta.env.PUBLIC_API_URL ?? "").replace(/\/+$/, "");
export const USING_MOCKS: boolean = API_URL === "";

/** Foreground budget for a tool call (docs/08 §5.4, R-25). */
const TOOL_DEADLINE_MS = 6000;
const FRESH_WINDOW_MS = 60_000;

export interface ToolContext {
  conversation_id: string;
  turn_id: string;
  state_version: number;
}

export interface RunToolOptions {
  /** "Reconsultar" and the first query of a session always go live (docs/09 §6). */
  forceLive?: boolean;
}

let sessionToken: string | null = null;

async function ensureSession(): Promise<string | null> {
  if (USING_MOCKS) return null;
  if (sessionToken) return sessionToken;
  const res = await fetch(`${API_URL}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ locale: "es-CO" }),
  });
  if (!res.ok) throw new Error(`POST /sessions → ${res.status}`);
  const body = (await res.json()) as { token: string };
  sessionToken = body.token;
  return sessionToken;
}

async function apiFetch(path: string, init: RequestInit = {}, timeoutMs = TOOL_DEADLINE_MS): Promise<Response> {
  const token = await ensureSession();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("X-Session-Token", token);
  const res = await fetch(`${API_URL}${path}`, { ...init, headers, signal: AbortSignal.timeout(timeoutMs) });
  if (res.status === 401) sessionToken = null; // SESSION_EXPIRED: next call asks for a new token
  return res;
}

// ── Brief ────────────────────────────────────────────────────────────────────

export const MOCK_BRIEF = briefMock as DatasetBrief;

export async function fetchBrief(): Promise<{ brief: DatasetBrief; live: boolean }> {
  if (USING_MOCKS) return { brief: MOCK_BRIEF, live: false };
  try {
    const res = await apiFetch("/dataset/brief", { method: "GET" });
    if (!res.ok) throw new Error(String(res.status));
    return { brief: (await res.json()) as DatasetBrief, live: true };
  } catch {
    // The cover page still needs something to draw; it is labelled as a recorded sample.
    return { brief: MOCK_BRIEF, live: false };
  }
}

// ── Tools ────────────────────────────────────────────────────────────────────

type MockKey = Exclude<keyof typeof toolMocks, "_note">;

const fold = (v: unknown): string =>
  String(v ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

/** Maps a tool call to the recorded envelope that answers it, or null. */
function resolveMock(call: ToolCallPayload): MockKey | null {
  const args = call.args;
  const filters = (args.filters ?? {}) as Record<string, unknown>;
  if (call.name === "correct_context") return fold(args.value).includes("melgar") ? "correct_to_melgar" : null;
  if (call.name !== "aggregate_ips") return null;
  const where = fold(filters.municipality) || fold(filters.department);
  if (args.metric === "capacity_sum") {
    if (args.group_by === "municipality") return "top_beds_by_municipality";
    if (where.includes("melgar")) return "beds_melgar";
    if (where.includes("medellin")) return "beds_medellin";
    return where === "" ? "beds_total" : null;
  }
  if (args.metric === "provider_count") {
    if (args.group_by === "nature") return "providers_by_nature";
    if (where.includes("bogota")) return "providers_bogota";
    return where === "" ? "providers_total" : null;
  }
  return null;
}

const mockSeenAt = new Map<string, number>();

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

function unavailable(call: ToolCallPayload, ctx: ToolContext, code: string, message: string, ms: number): EvidenceEnvelope {
  return {
    schema_version: "1",
    tool_call_id: call.tool_call_id,
    turn_id: ctx.turn_id,
    state_version: ctx.state_version,
    status: "unavailable",
    data: null,
    evidence: {
      dataset_id: "s2ru-bqt6",
      source_url: "https://www.datos.gov.co/resource/s2ru-bqt6.json",
      query_fingerprint: `unavailable:${call.tool_call_id}`,
      cutoff_raw: "",
      fetched_at: new Date().toISOString(),
      cache_status: "live",
      complete: false,
      unit: "",
      filters: {},
      warnings: [],
    },
    trace: { engine: "soda3", soql: "", ms, rows: 0 },
    error: { code, message, retryable: true },
    next_cursor: null,
    context_patch: {},
  };
}

async function runMockTool(call: ToolCallPayload, ctx: ToolContext, opts: RunToolOptions): Promise<EvidenceEnvelope> {
  const key = resolveMock(call);
  if (!key) {
    await sleep(300);
    return unavailable(call, ctx, "TOOL_INVALID", "No hay una muestra grabada para esta consulta.", 300);
  }
  const recorded = structuredClone(toolMocks[key]) as unknown as EvidenceEnvelope;
  const fp = recorded.evidence.query_fingerprint;
  const seen = mockSeenAt.get(fp);
  const now = Date.now();
  const fresh = !opts.forceLive && seen !== undefined && now - seen < FRESH_WINDOW_MS;
  const cache: CacheStatus = fresh ? "fresh" : "live";
  // A cache hit answers in a few ms; a live query takes about what was recorded.
  const ms = fresh ? 4 + Math.round(Math.random() * 6) : Math.round(recorded.trace.ms * (0.9 + Math.random() * 0.25));
  await sleep(ms);
  if (!fresh) mockSeenAt.set(fp, now);
  recorded.tool_call_id = call.tool_call_id;
  recorded.turn_id = ctx.turn_id;
  recorded.state_version = call.name === "correct_context" ? ctx.state_version + 1 : ctx.state_version;
  recorded.evidence.cache_status = cache;
  recorded.evidence.fetched_at = new Date(fresh && seen ? seen : now).toISOString();
  recorded.trace.ms = ms;
  return recorded;
}

/**
 * Tool bridge (docs/08 §5): `POST /tools/{name}` with `{tool_call_id, args, context}`.
 * Never throws: a failure becomes an `unavailable` envelope.
 */
export async function runTool(call: ToolCallPayload, ctx: ToolContext, opts: RunToolOptions = {}): Promise<EvidenceEnvelope> {
  if (USING_MOCKS) return runMockTool(call, ctx, opts);
  const started = performance.now();
  try {
    const res = await apiFetch(`/tools/${call.name}`, {
      method: "POST",
      body: JSON.stringify({ tool_call_id: call.tool_call_id, args: call.args, context: ctx, force_live: opts.forceLive ?? false }),
    });
    if (!res.ok) {
      const ms = Math.round(performance.now() - started);
      return unavailable(call, ctx, res.status === 429 ? "RATE_LIMITED" : "TOOL_INVALID", `La API respondió ${res.status}.`, ms);
    }
    return (await res.json()) as EvidenceEnvelope;
  } catch (err) {
    const ms = Math.round(performance.now() - started);
    const timedOut = err instanceof DOMException && err.name === "TimeoutError";
    return unavailable(
      call,
      ctx,
      timedOut ? "TIMEOUT" : "TOOL_FAILURE",
      timedOut ? "La consulta superó el plazo de 6 s." : "No se pudo contactar la API.",
      ms,
    );
  }
}
