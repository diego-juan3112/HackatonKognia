/**
 * Markup for one tool call and its evidence (docs/09 §5): SoQL, time, rows,
 * source and cutoff, cache badge and «Reconsultar». Shared by the «API en vivo»
 * tab and by the collapsible evidence card under each answer in the chat.
 * Styles live in components/ApiPanel.astro.
 */
import { USING_MOCKS } from "../voice/api";
import type { ConsoleState, ToolEntry } from "../voice/store";
import type { CacheStatus, EvidenceEnvelope, ToolStatus, WarningCode } from "../voice/types";
import { dur, esc, icon, num } from "./dom";

const CACHE: Record<CacheStatus, { cls: string; label: string; title: string }> = {
  live: { cls: "tag-live", label: "live", title: "Consulta recién hecha a la fuente" },
  fresh: { cls: "tag-fresh", label: "fresh", title: "Respuesta en caché de menos de 60 segundos" },
  stale: { cls: "tag-stale", label: "stale", title: "La fuente falló: se sirve una respuesta anterior" },
};

const STATUS: Record<ToolStatus, string> = {
  ok: "",
  empty: "Sin resultados",
  ambiguous: "Ambiguo: hay que aclarar",
  unavailable: "No disponible",
  invalid: "Consulta inválida",
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
  const filters = (a.filters ?? {}) as Record<string, unknown>;
  const parts: string[] = [];
  if (a.metric) parts.push(String(a.metric));
  for (const [k, v] of Object.entries(filters)) parts.push(`${k} = ${String(v)}`);
  if (a.group_by) parts.push(`por ${String(a.group_by)}`);
  if (a.top_n) parts.push(`top ${String(a.top_n)}`);
  if (a.field) parts.push(`${String(a.field)} → ${String(a.value)}`);
  return parts.join(" · ");
}

function result(env: EvidenceEnvelope | undefined): string {
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
  if (!t.trace || !t.status) return '<span class="tag tag-warn">consultando</span>';
  if (t.status !== "ok") return `<span class="tag tag-bad">${icon("triangle-alert")} ${STATUS[t.status]}</span>`;
  const cache = CACHE[t.trace.cache_status];
  // Without a backend the envelope is a recording: the badge must not pass for a live call.
  const sample = USING_MOCKS ? " · muestra grabada" : "";
  return `<span class="tag ${cache.cls}" title="${cache.title}">${cache.label}${sample}</span>`;
}

/** One-line summary used as the header of the collapsible card in the chat. */
export function summaryLine(t: ToolEntry): string {
  const facts = t.trace ? `<span class="num">${dur(t.trace.ms)}</span><span class="num">${num(t.trace.rows)} ${t.trace.rows === 1 ? "fila" : "filas"}</span>` : "";
  return `<code class="mono">${esc(t.name)}</code>${facts}${badge(t)}${t.invalidated ? '<span class="tag tag-violet">invalidada</span>' : ""}`;
}

/** Full body of an entry (everything but the outer list item). */
export function evidenceBody(t: ToolEntry, s: ConsoleState): string {
  const env = t.evidence_ref ? s.evidence[t.evidence_ref] : undefined;
  const head = `<div class="head"><code class="mono">${esc(t.name)}</code><span class="args">${esc(argsLine(t))}</span></div>`;
  if (!t.trace || !t.status) return `${head}<p class="waiting">Consultando datos.gov.co…</p>`;
  const fetched = env ? new Date(env.evidence.fetched_at).toLocaleTimeString("es-CO") : "";
  const cutoff = env?.evidence.cutoff_raw.replace(/\s+/g, " ").replace(/^Fecha corte REPS:\s*/i, "") ?? "";
  const warnings = (env?.evidence.warnings ?? []).map((w) => `<li>${esc(WARNING[w] ?? w)}</li>`).join("");
  const error = env?.error ? `<p class="err">${esc(env.error.message)} No se inventa ningún resultado.</p>` : "";
  const canRequery = t.name !== "correct_context" && t.status === "ok" && !t.invalidated;
  return `${t.invalidated ? `<p class="void">${icon("split")} Evidencia invalidada por una corrección</p>` : ""}
    ${head}
    ${t.trace.soql ? `<pre class="mono soql" tabindex="0" aria-label="Consulta SoQL"><code>${soql(t.trace.soql)}</code></pre>` : ""}
    <p class="meta">
      ${badge(t)}
      <span class="num"><strong>${dur(t.trace.ms)}</strong></span>
      <span class="num"><strong>${num(t.trace.rows)}</strong> ${t.trace.rows === 1 ? "fila" : "filas"}</span>
    </p>
    ${error}
    ${result(env)}
    ${env && env.status === "ok" ? `<p class="src">Fuente: datos.gov.co, conjunto ${esc(env.evidence.dataset_id)} (MinSalud, REPS). Corte: ${esc(cutoff)}. Consultado a las ${fetched}.</p>` : ""}
    ${warnings ? `<ul class="warnings">${warnings}</ul>` : ""}
    ${requeryLine(t)}
    ${canRequery ? `<button class="btn btn-sm requery-btn" type="button" data-requery="${esc(t.tool_call_id)}" ${t.requery?.pending ? "disabled" : ""}>${icon("refresh-cw")} Reconsultar</button>` : ""}`;
}
