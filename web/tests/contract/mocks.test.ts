/**
 * Golden figures of the source (docs/07 §7 A-05, docs/09): the recorded mocks must
 * agree with them and with each other, because every number the UI shows comes from here.
 */
import { describe, expect, it } from "vitest";
import affect from "../../mocks/affect.json";
import brief from "../../mocks/brief.json";
import tools from "../../mocks/tool-results.json";

const GOLDEN = {
  rows: 41_427,
  providers: 9_320,
  privada: 8_308,
  publica: 998,
  mixta: 14,
  site_codes: 10_921,
  beds: 97_036,
  cutoff: "2022-11-05",
};

const envelopes = Object.entries(tools).filter(([k]) => k !== "_note") as [string, (typeof tools)["beds_total"]][];
const nature = (rows: { key: string; value: number }[], key: string): number | undefined => rows.find((g) => g.key === key)?.value;

describe("mocks/brief.json — cifras doradas", () => {
  it("41.427 filas, 9.320 prestadores, 10.921 códigos de sede", () => {
    expect(brief.stats.rows).toBe(GOLDEN.rows);
    expect(brief.stats.providers).toBe(GOLDEN.providers);
    expect(brief.stats.site_codes).toBe(GOLDEN.site_codes);
  });

  it("9.320 = 8.308 privadas + 998 públicas + 14 mixtas", () => {
    expect(nature(brief.by_nature, "Privada")).toBe(GOLDEN.privada);
    expect(nature(brief.by_nature, "Pública")).toBe(GOLDEN.publica);
    expect(nature(brief.by_nature, "Mixta")).toBe(GOLDEN.mixta);
    expect(brief.by_nature.reduce((s, g) => s + g.value, 0)).toBe(brief.stats.providers);
  });

  it("corte 2022-11-05 y licencia CC BY-SA 4.0 (NF-08)", () => {
    expect(brief.source.cutoff_date).toBe(GOLDEN.cutoff);
    expect(brief.source.cutoff_raw).toMatch(/Nov\s+5 2022/);
    expect(brief.source.license).toBe("CC BY-SA 4.0");
  });

  it("3–5 preguntas sugeridas (A-02)", () => {
    expect(brief.suggested_questions.length).toBeGreaterThanOrEqual(3);
    expect(brief.suggested_questions.length).toBeLessThanOrEqual(5);
    expect(new Set(brief.suggested_questions).size).toBe(brief.suggested_questions.length);
  });

  it("el brief hablado declara que es una IA y dice las mismas cifras y el corte (A-02, A-25)", () => {
    expect(brief.spoken_brief).toMatch(/inteligencia artificial/i);
    expect(brief.spoken_brief).toContain("9.320");
    expect(brief.spoken_brief).toContain("10.921");
    expect(brief.spoken_brief).toMatch(/noviembre de 2022/);
    // A-05: the row count must never be presented as a number of providers.
    expect(brief.spoken_brief).not.toMatch(/41\.427 (prestadores|IPS)/i);
  });

  it("el brief hablado cabe en 20 s a ritmo de habla normal (A-02)", () => {
    const words = brief.spoken_brief.split(/\s+/).length;
    expect(words / 2.5).toBeLessThanOrEqual(20); // 150 palabras por minuto
  });
});

describe("mocks/tool-results.json — sobres de evidencia", () => {
  it("total de prestadores, por naturaleza y camas coinciden con las doradas", () => {
    expect(tools.providers_total.data.value).toBe(GOLDEN.providers);
    expect(nature(tools.providers_by_nature.data.groups, "Privada")).toBe(GOLDEN.privada);
    expect(nature(tools.providers_by_nature.data.groups, "Pública")).toBe(GOLDEN.publica);
    expect(nature(tools.providers_by_nature.data.groups, "Mixta")).toBe(GOLDEN.mixta);
    expect(tools.beds_total.data.value).toBe(GOLDEN.beds);
  });

  it("las cifras repetidas en varios sobres no se contradicen", () => {
    const medellin = tools.top_beds_by_municipality.data.groups.find((g) => g.key.startsWith("MEDELLÍN"));
    expect(medellin?.value).toBe(tools.beds_medellin.data.value);
    expect(brief.top_departments.find((d) => d.key === "Bogotá D.C")?.value).toBe(tools.providers_bogota.data.value);
    expect(tools.providers_by_nature.data.groups).toEqual(brief.by_nature);
    const top = tools.top_beds_by_municipality.data.groups.reduce((s, g) => s + g.value, 0);
    expect(top).toBeLessThan(GOLDEN.beds);
  });

  it.each(envelopes)("%s tiene el sobre completo, con SoQL, ms, filas, fuente y corte", (_key, env) => {
    expect(env.schema_version).toBe("1");
    expect(env.status).toBe("ok");
    expect(env.error).toBeNull();
    expect(env.trace.soql).toMatch(/^SELECT /);
    expect(env.trace.ms).toBeGreaterThan(0);
    expect(env.trace.rows).toBeGreaterThanOrEqual(1);
    expect(env.evidence.dataset_id).toBe("s2ru-bqt6");
    expect(env.evidence.source_url).toBe("https://www.datos.gov.co/resource/s2ru-bqt6.json");
    expect(env.evidence.cutoff_raw).toMatch(/Nov\s+5 2022/);
    expect(env.evidence.query_fingerprint).toMatch(/^sha256:/);
    expect(env.evidence.unit).not.toBe("");
  });

  it("cada sobre tiene una huella de consulta distinta", () => {
    const fps = envelopes.map(([, e]) => e.evidence.query_fingerprint);
    expect(new Set(fps).size).toBe(fps.length);
  });

  it("los agregados de capacidad advierten que no es disponibilidad (A-08)", () => {
    for (const key of ["beds_total", "beds_medellin", "beds_melgar", "top_beds_by_municipality"] as const) {
      expect(tools[key].evidence.warnings).toContain("NOT_AVAILABILITY");
    }
  });
});

describe("mocks/affect.json — lecturas del analista", () => {
  const readings = Object.entries(affect).filter(([k]) => k !== "_note") as [string, (typeof affect)["default"]][];

  it.each(readings)("%s usa solo etiquetas del contrato (docs/10 §6)", (_key, r) => {
    for (const channel of [r.text, r.voice]) {
      expect(["positive", "neutral", "negative", "uncertain"]).toContain(channel.sentiment);
      expect(["alegría", "tristeza", "enojo", "miedo", "sorpresa", "asco", "neutral", "incierta"]).toContain(channel.emotion);
      expect(["frustración", "confusión", "satisfacción", "prisa", "interés", "desconocido"]).toContain(channel.state_hint);
    }
    expect(r.analysis_ms).toBeGreaterThan(0);
  });

  it("hay al menos una lectura en la que voz y texto discrepan (A-21)", () => {
    expect(readings.some(([, r]) => r.text.sentiment !== r.voice.sentiment)).toBe(true);
  });
});
