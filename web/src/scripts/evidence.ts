/**
 * Markup for one tool call and its evidence (docs/09 §5): SoQL, time, rows,
 * source and cutoff, cache badge and «Reconsultar». Used by the «API en vivo»
 * section of the admin board; the conversation screen only shows `citeLine`.
 * Styles live in components/ApiPanel.astro.
 */
import { USING_MOCKS } from "../voice/api";
import type { ConsoleState, ToolEntry } from "../voice/store";
import type { CacheStatus, EvidenceEnvelope, ToolStatus, WarningCode } from "../voice/types";
import { dur, esc, icon, num } from "./dom";

const CACHE: Record<CacheStatus, { cls: string; label: string; title: string }> = {
  live: { cls: "tag-live", label: "en vivo", title: "Consulta recién hecha a la fuente" },
  fresh: { cls: "tag-fresh", label: "reciente", title: "Respuesta guardada hace menos de 60 segundos" },
  stale: { cls: "tag-stale", label: "respuesta anterior", title: "La fuente falló: se sirve una respuesta anterior" },
};

const STATUS: Record<ToolStatus, string> = {
  ok: "",
  empty: "No encontró registros",
  ambiguous: "Varias opciones: pidió aclarar",
  unavailable: "La fuente no respondió",
  invalid: "Pregunta mal armada: la rehízo",
};

/** What each tool does, in words a non-technical reader understands. */
export const TOOL_LABEL: Record<string, string> = {
  search_ips: "Buscar IPS",
  get_ips_details: "Ver el detalle de una IPS",
  aggregate_ips: "Contar o sumar",
  compare_ips: "Comparar IPS",
  correct_context: "Corregir lo entendido",
  verify_registration: "Verificar si una IPS está registrada",
  area_profile: "Resumir un departamento o municipio",
  compare_areas: "Comparar zonas",
  dataset_info: "Explicar qué contiene la fuente",
};

export const toolLabel = (name: string): string => TOOL_LABEL[name] ?? name;

const ARG_LABEL: Record<string, string> = {
  department: "Departamento",
  departamento: "Departamento",
  municipality: "Municipio",
  municipio: "Municipio",
  name: "Nombre",
  nature: "Naturaleza",
  naturaleza: "Naturaleza",
  level: "Nivel",
  capacity_group: "Grupo",
  capacity_type: "Tipo",
  site_key: "Sede",
  provider_code: "Código",
  topic: "Tema",
};

const METRIC: Record<string, string> = {
  provider_count: "Número de IPS",
  site_count: "Número de sedes",
  capacity_sum: "Suma de capacidad",
};

const WARNING: Record<WarningCode, string> = {
  CUTOFF_2022: "Datos con corte de 2022",
  ROWS_ARE_CAPACITY_CATEGORIES: "Las filas son categorías de capacidad",
  LEVEL_MISSING_MOSTLY: "Nivel vacío en el 89 % de las IPS",
  DISTRICT_AS_DEPARTMENT: "Cinco distritos figuran como departamentos",
  MIXED_TYPES: "Suma todos los tipos del grupo",
  SITE_CODES_NOT_PHYSICAL_SITES: "Códigos de sede, no sedes físicas",
  NOT_AVAILABILITY: "Capacidad instalada, no disponibilidad",
  NULL_NOT_ZERO: "Vacío no es cero",
  PARTIAL_RESULT: "Resultado parcial",
  STALE_CACHE: "Caché vencida",
  FILTER_NORMALIZED: "Filtro normalizado al léxico",
};

const KEYWORDS = /\b(SELECT|WHERE|GROUP BY|ORDER BY|LIMIT|DISTINCT|DESC|ASC|AND|AS)\b/g;

function soql(text: string): string {
  return esc(text)
    .replace(/'[^']*'/g, (m) => `<span class="str">${m}</span>`)
    .replace(KEYWORDS, '<span class="kw">$1</span>')
    .replace(/\b(count|sum)\(/g, '<span class="fn">$1</span>(');
}

function argsLine(entry: ToolEntry): string {
  const a = entry.args;
  const parts: string[] = [];
  if (a.metric) parts.push(METRIC[String(a.metric)] ?? String(a.metric));
  const flat = { ...a, ...((a.filters ?? {}) as Record<string, unknown>) } as Record<string, unknown>;
  for (const [k, v] of Object.entries(flat)) {
    if (ARG_LABEL[k] && (typeof v === "string" || typeof v === "number")) parts.push(`${ARG_LABEL[k]}: ${String(v)}`);
  }
  if (Array.isArray(a.areas)) {
    parts.push((a.areas as Record<string, unknown>[]).map((x) => String(x.municipality ?? x.department ?? "")).filter(Boolean).join(" frente a "));
  }
  if (Array.isArray(a.site_keys)) parts.push(`${a.site_keys.length} sedes`);
  if (a.group_by) parts.push(`agrupado por ${ARG_LABEL[String(a.group_by)]?.toLowerCase() ?? String(a.group_by)}`);
  if (a.top_n) parts.push(`los ${String(a.top_n)} primeros`);
  if (a.field) parts.push(`${ARG_LABEL[String(a.field)] ?? String(a.field)} → ${String(a.value)}`);
  return parts.join(" · ");
}

const FIELD_LABEL: Record<string, string> = {
  ...ARG_LABEL,
  items: "Registros",
  results: "Registros",
  candidates: "Opciones",
  sites: "Sedes",
  areas: "Zonas",
  total: "Total",
  count: "Cantidad",
  providers: "IPS",
  provider_count: "Número de IPS",
  site_count: "Número de sedes",
  capacity_sum: "Suma de capacidad",
  capacity: "Capacidad",
  quantity: "Cantidad",
  address: "Dirección",
  phone: "Teléfono",
  email: "Correo",
  registered: "Registrada",
  manager: "Gerente",
  key: "Grupo",
  value: "Valor",
};

/** Keys already drawn by the headline figure, the bars or the source line. */
const DRAWN = new Set(["value", "groups", "unit", "resolved", "complete"]);

const fieldLabel = (k: string): string => FIELD_LABEL[k] ?? k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function scalar(v: unknown): string {
  if (v === null || v === undefined || v === "") return "sin registrar";
  if (typeof v === "boolean") return v ? "sí" : "no";
  if (typeof v === "number") return num(v);
  return esc(v);
}

/** Generic view of any value of the envelope's `data`: nothing the source returned is hidden. */
function anyValue(v: unknown, depth = 0): string {
  if (v === null || typeof v !== "object") return scalar(v);
  if (Array.isArray(v)) {
    if (!v.length) return "ninguno";
    if (v.every((x) => x === null || typeof x !== "object")) return v.map(scalar).join(", ");
    return `<ol class="records">${v.map((x) => `<li>${anyValue(x, depth + 1)}</li>`).join("")}</ol>`;
  }
  const rows = Object.entries(v as Record<string, unknown>)
    .map(([k, x]) => `<div><dt>${esc(fieldLabel(k))}</dt><dd>${depth > 3 ? esc(JSON.stringify(x)) : anyValue(x, depth + 1)}</dd></div>`)
    .join("");
  return `<dl class="fields">${rows}</dl>`;
}

function rest(data: Record<string, unknown>): string {
  const left = Object.fromEntries(Object.entries(data).filter(([k]) => !DRAWN.has(k)));
  return Object.keys(left).length ? `<div class="all-data" data-testid="all-data">${anyValue(left)}</div>` : "";
}

function result(env: EvidenceEnvelope | undefined): string {
  return env?.data ? headline(env) + rest(env.data) : "";
}

function headline(env: EvidenceEnvelope | undefined): string {
  const data = env?.data;
  if (!env || !data) return "";
  if (typeof data.resolved === "string") {
    return `<p class="value">Ahora la consulta usa <strong>${esc(data.resolved)}</strong>.</p>`;
  }
  const unit = esc(data.unit ?? env.evidence.unit);
  if (typeof data.value === "number") return `<p class="value"><strong class="num">${num(data.value)}</strong> ${unit}</p>`;
  if (Array.isArray(data.groups)) {
    const max = Math.max(1, ...data.groups.map((g) => g.value));
    const rows = data.groups
      .map(
        (g) => `<li>
          <span class="k">${esc(g.key ?? "sin registrar")}</span>
          <span class="bar"><i style="width:${((g.value / max) * 100).toFixed(1)}%"></i></span>
          <span class="v num">${num(g.value)}</span>
        </li>`,
      )
      .join("");
    return `<ul class="groups" aria-label="Resultado en ${unit}">${rows}</ul><p class="unit">Unidad: ${unit}</p>`;
  }
  return "";
}

function requeryLine(entry: ToolEntry): string {
  const r = entry.requery;
  if (!r) return "";
  if (r.pending) return '<p class="requery">Reconsultando en vivo…</p>';
  const when = r.at ? new Date(r.at).toLocaleTimeString("es-CO") : "";
  return r.matches
    ? `<p class="requery ok">Reconsultado a las ${when} en ${dur(r.ms ?? null)}: el resultado coincide.</p>`
    : `<p class="requery bad">Reconsultado a las ${when}: el resultado no coincide o la fuente no respondió.</p>`;
}

/** Cache badge, or the failure status when the call did not succeed. */
export function badge(t: ToolEntry): string {
  if (!t.trace || !t.status) return '<span class="tag tag-note">consultando</span>';
  if (t.status !== "ok") return `<span class="tag tag-bad">${icon("triangle-alert")} ${STATUS[t.status]}</span>`;
  const cache = CACHE[t.trace.cache_status];
  // Without a backend the envelope is a recording: the badge must not pass for a live call.
  const sample = USING_MOCKS ? " · muestra grabada" : "";
  return `<span class="tag ${cache.cls}" title="${cache.title}">${cache.label}${sample}</span>`;
}

/** One-line summary used as the header of the collapsible card in the chat. */
export function summaryLine(t: ToolEntry): string {
  const facts = t.trace ? `<span class="num">${dur(t.trace.ms)}</span><span class="num">${num(t.trace.rows)} ${t.trace.rows === 1 ? "fila" : "filas"}</span>` : "";
  return `<code class="mono">${esc(t.name)}</code>${facts}${badge(t)}${t.invalidated ? '<span class="tag tag-accent">invalidada</span>' : ""}`;
}

/** Full body of an entry (everything but the outer list item). */
/** Backend methods that served the call, in order (envelope.pipeline, added 2026-10-09). */
function pipelineList(env: unknown): string {
  const raw = (env as { pipeline?: unknown } | undefined)?.pipeline;
  const steps = Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string") : [];
  if (!steps.length) return "";
  return `<p class="meta"><strong>Cómo se resolvió en el servidor</strong></p><ol class="pipeline mono" data-testid="pipeline">${steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>`;
}

export function evidenceBody(t: ToolEntry, s: ConsoleState): string {
  const env = t.evidence_ref ? s.evidence[t.evidence_ref] : undefined;
  const head = `<div class="head"><strong class="tool-name">${esc(toolLabel(t.name))}</strong><span class="args">${esc(argsLine(t))}</span></div>`;
  if (!t.trace || !t.status) return `${head}<p class="waiting">Consultando datos.gov.co…</p>`;
  const fetched = env ? new Date(env.evidence.fetched_at).toLocaleTimeString("es-CO") : "";
  const cutoff = env?.evidence.cutoff_raw.replace(/\s+/g, " ").replace(/^Fecha corte REPS:\s*/i, "") ?? "";
  const warnings = (env?.evidence.warnings ?? []).map((w) => `<li>${esc(WARNING[w] ?? w)}</li>`).join("");
  const error = env?.error ? `<p class="err">${esc(env.error.message)} No se inventa ningún resultado.</p>` : "";
  const canRequery = t.name !== "correct_context" && t.status === "ok" && !t.invalidated;
  return `${t.invalidated ? `<p class="void">${icon("split")} Evidencia invalidada por una corrección</p>` : ""}
    ${head}
    <p class="meta">
      ${badge(t)}
      <span class="num">tardó <strong>${dur(t.trace.ms)}</strong></span>
    </p>
    ${error}
    ${result(env)}
    <details class="tech">
      <summary>Detalle técnico</summary>
      <p class="meta"><code class="mono">${esc(t.name)}</code><span class="num"><strong>${num(t.trace.rows)}</strong> ${t.trace.rows === 1 ? "fila" : "filas"}</span></p>
      ${t.trace.soql ? `<pre class="mono soql" data-testid="soql" tabindex="0" aria-label="Consulta SoQL"><code>${soql(t.trace.soql)}</code></pre>` : ""}
      ${pipelineList(env)}
    </details>
    ${env && env.status === "ok" ? `<p class="src">Fuente: datos.gov.co, conjunto ${esc(env.evidence.dataset_id)} (MinSalud, REPS). Corte: ${esc(cutoff)}. Consultado a las ${fetched.replace(/\.\s*$/, "")}.</p>` : ""}
    ${warnings ? `<ul class="warnings">${warnings}</ul>` : ""}
    ${requeryLine(t)}
    ${canRequery ? `<button class="btn requery-btn" type="button" data-testid="requery-button" data-requery="${esc(t.tool_call_id)}" ${t.requery?.pending ? 'aria-disabled="true"' : ""}>${icon("refresh-cw")} Reconsultar</button>` : ""}`;
}

const MONTHS: Record<string, string> = {
  jan: "ene", feb: "feb", mar: "mar", apr: "abr", may: "may", jun: "jun",
  jul: "jul", aug: "ago", sep: "sep", oct: "oct", nov: "nov", dec: "dic",
};

/** «Nov  5 2022  1:37PM» → «5-nov-2022». Falls back to the raw text. */
export function shortCutoff(raw: string): string {
  const clean = raw.replace(/\s+/g, " ").replace(/^Fecha corte REPS:\s*/i, "").trim();
  const m = /^([A-Za-z]{3})[a-z]*\.? (\d{1,2}),? (\d{4})/.exec(clean);
  const month = m ? MONTHS[m[1]!.toLowerCase()] : undefined;
  return m && month ? `${Number(m[2])}-${month}-${m[3]}` : clean;
}

/**
 * The only trace of the source on the conversation screen: who publishes the
 * figure and its cutoff. Empty when the call failed or was superseded.
 */
export function citeLine(t: ToolEntry, s: ConsoleState): string {
  const env = t.evidence_ref ? s.evidence[t.evidence_ref] : undefined;
  if (!env || env.status !== "ok" || t.invalidated || t.name === "correct_context") return "";
  return `Fuente: REPS · MinSalud, corte ${esc(shortCutoff(env.evidence.cutoff_raw))}`;
}
