/**
 * The scripted session, played once in real time (≈ 40 s) on `/consola`, and what
 * it must leave on screen (docs/07 §7 and the 10-minute script of §10).
 */
import type { Page } from "@playwright/test";
import { countMicRequests, expect, micRequests, PICTOGRAPH, shot, test, watch, type Problems } from "./fixtures";

test.describe.configure({ mode: "serial" });

let page: Page;
let problems: Problems;

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
  problems = watch(page);
  await countMicRequests(page);
  await page.goto("/consola");
  await page.waitForLoadState("networkidle");
});

test.afterAll(async () => {
  await page.close();
});

const rgb = (color: string): [number, number, number] => (color.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number) as [number, number, number];

test("estado inicial: tema claro y dos tarjetas, avatar a la izquierda y chat a la derecha", async () => {
  await shot(page, "consola-inicial-1366x768");
  const [r, g, b] = rgb(await page.evaluate(() => getComputedStyle(document.body).backgroundColor));
  expect(Math.min(r, g, b)).toBeGreaterThan(225); // light theme

  const stage = (await page.locator("#stage").boundingBox())!;
  const chat = (await page.locator(".panel-card").boundingBox())!;
  expect(stage.x + stage.width).toBeLessThanOrEqual(chat.x);
  expect(Math.abs(stage.y - chat.y)).toBeLessThan(4);
  expect(chat.y + chat.height).toBeLessThanOrEqual(768);
  for (const card of ["#stage", ".panel-card"]) {
    const bg = rgb(await page.locator(card).evaluate((el) => getComputedStyle(el).backgroundColor));
    expect(bg).toEqual([255, 255, 255]);
  }
  // The console fits the viewport: the page itself does not scroll.
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight)).toBe(true);
});

test("controles del objetivo de diseño: verde «Activar micrófono», «Silenciar», entrada de texto y azul «Enviar»", async () => {
  const toggle = page.locator("#btn-toggle");
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveText(/Activar micrófono/);
  const [tr, tg, tb] = rgb(await toggle.evaluate((el) => getComputedStyle(el).backgroundColor));
  expect(tg).toBeGreaterThan(tr + 60);
  expect(tg).toBeGreaterThan(tb + 60);

  const mute = page.locator("#btn-mute");
  await expect(mute).toBeVisible();
  await expect(mute).toHaveText(/Silenciar/);
  await expect(mute).toBeDisabled();

  await expect(page.locator("#ask-input")).toBeVisible();
  await expect(page.locator("#ask-input")).toHaveAttribute("placeholder", /Escribe tu pregunta/);
  const send = page.locator("#ask-form button[type=submit]");
  await expect(send).toHaveText(/Enviar/);
  const [sr, sg, sb] = rgb(await send.evaluate((el) => getComputedStyle(el).backgroundColor));
  expect(sb).toBeGreaterThan(sr + 100);
  expect(sb).toBeGreaterThan(sg + 60);

  // The toggle sits in the left card, the composer in the right one.
  const stage = (await page.locator("#stage").boundingBox())!;
  const t = (await toggle.boundingBox())!;
  const s = (await send.boundingBox())!;
  expect(t.x + t.width).toBeLessThanOrEqual(stage.x + stage.width);
  expect(s.x).toBeGreaterThan(stage.x + stage.width);
});

test("antes de iniciar: aviso de IA en el chat, preguntas sugeridas y ningún permiso pedido (A-01, A-02)", async () => {
  await expect(page.locator("#chat-empty")).toContainText("Soy un asistente de inteligencia artificial");
  const chips = await page.locator("#chips button").count();
  expect(chips).toBeGreaterThanOrEqual(3);
  expect(chips).toBeLessThanOrEqual(5);
  await expect(page.locator("#state-badge")).toHaveText("En línea");
  expect(await micRequests(page)).toBe(0);
});

test("al iniciar: el agente habla el brief, se puede silenciar y hay subtítulos", async () => {
  await page.locator("#btn-toggle").click();
  await expect(page.locator("#btn-toggle")).toHaveText(/Detener/);
  await expect(page.locator("#state-badge")).toHaveText("Hablando", { timeout: 5_000 });
  await expect(page.locator("#btn-mute")).toBeEnabled();
  await expect(page.locator("html")).toHaveAttribute("data-status", "speaking");
  await expect(page.locator("#subtitle")).toBeVisible();
  await expect(page.locator("#subtitle")).toContainText("Asistente");
  const first = page.locator("#msgs .msg.from-agent").first();
  await expect(first.locator(".typing")).toContainText("Escribiendo");
  await expect(first.locator(".msg-meta")).toContainText("resumen inicial");
  await expect(page.locator("#status-sub")).toContainText("Motor simulado");
  await shot(page, "consola-brief-hablando");
});

test("el guion termina con el aviso de «Sesión renovada» y el motor cambiado (A-23)", async () => {
  test.setTimeout(150_000);
  // A partial user utterance shows that it is being heard.
  await expect(page.locator("#msgs .msg.from-user.partial .typing")).toContainText("Escuchando", { timeout: 30_000 });
  await expect(page.locator("#msgs details.evidence").first()).toBeVisible({ timeout: 40_000 });
  await shot(page, "consola-guion-primera-respuesta");
  const notice = page.locator("#msgs .msg.system-session");
  await expect(notice).toBeVisible({ timeout: 110_000 });
  await expect(notice).toContainText("Sesión renovada");
  await expect(notice).toContainText("motor cambiado a Gemini Live");
  await expect(notice).toContainText("No se repitió ninguna consulta");
  await expect(page.locator("#state-badge")).toHaveText("Te escucho");
  await expect(page.locator("#engine-select")).toHaveValue("gemini");
  await expect(page.locator("#msgs .msg.system-error")).toContainText("corte simulado");
  await shot(page, "consola-guion-final-1366x768");
});

test("cada burbuja lleva rol y hora de la sesión (A-13)", async () => {
  const bubbles = page.locator("#msgs .msg .bubble");
  const count = await bubbles.count();
  expect(count).toBeGreaterThanOrEqual(10);
  for (const b of await bubbles.all()) {
    await expect(b.locator("time")).toHaveText(/^\d{2}:\d{2}$/);
    expect(await b.locator("time").getAttribute("title")).toMatch(/^\d{2}:\d{2}\.\d{3}$/);
    await expect(b.locator(".sr-only").first()).toHaveText(/^(Asistente|Tú):$/);
  }
  // Three spoken utterances; the correction is shown inside the one it corrects.
  await expect(page.locator("#msgs .msg.from-user")).toHaveCount(3);
  expect(await page.locator("#msgs .msg.from-agent:not(.is-evidence)").count()).toBeGreaterThanOrEqual(7);
  await expect(page.locator("#msgs .typing")).toHaveCount(0);
  // User on the right, agent on the left.
  const user = (await page.locator("#msgs .msg.from-user").first().boundingBox())!;
  const agent = (await page.locator("#msgs .msg.from-agent").first().boundingBox())!;
  expect(user.x).toBeGreaterThan(agent.x);
  // The times grow down the transcript.
  const times = await page.locator("#msgs .msg .bubble time").evaluateAll((els) => els.map((e) => e.getAttribute("title") ?? ""));
  expect([...times].sort()).toEqual(times);
});

test("tarjeta de evidencia con SoQL, ms, filas, fuente y corte (A-24)", async () => {
  const cards = page.locator("#msgs details.evidence");
  await expect(cards).toHaveCount(4);
  const card = cards.first();
  await expect(card.locator("summary")).toContainText("Evidencia");
  await expect(card.locator("summary")).toContainText("aggregate_ips");
  await expect(card.locator("summary")).toContainText(/\d+ ms/);
  await expect(card.locator("summary")).toContainText("3 filas");
  await card.locator("summary").click();
  await expect(card.locator("pre.soql")).toContainText("SELECT municipio, departamento, sum(num_cantidad_capacidad_instalada)");
  await expect(card.locator("pre.soql")).toContainText("LIMIT 3");
  await expect(card.locator(".meta")).toContainText(/\d+ ms/);
  await expect(card.locator(".meta")).toContainText("3 filas");
  await expect(card.locator(".src")).toContainText("Fuente: datos.gov.co, conjunto s2ru-bqt6");
  await expect(card.locator(".src")).toContainText("Corte: Nov 5 2022");
  await expect(card.locator(".groups li")).toHaveCount(3);
  await expect(card.locator(".groups")).toContainText("16.193");
  await expect(card.locator(".warnings")).toContainText("Capacidad instalada, no disponibilidad");
  // Without a backend the badge must not pass for a live call.
  await expect(card.locator(".meta .tag")).toContainText("muestra grabada");
  await shot(page, "consola-evidencia-abierta");
});

test("«Reconsultar» repite la llamada y el resultado coincide (A-24)", async () => {
  const card = page.locator("#msgs details.evidence").first();
  const button = card.getByRole("button", { name: "Reconsultar" });
  await expect(button).toBeVisible();
  await button.click();
  await expect(card.locator(".requery.ok")).toContainText("el resultado coincide", { timeout: 10_000 });
  // The card stays open through the re-render and no new query is listed.
  await expect(card).toHaveAttribute("open", "");
  await expect(page.locator("#msgs details.evidence")).toHaveCount(4);
});

test("corrección visible original → corregido, con la evidencia anterior invalidada (A-09)", async () => {
  const fixed = page.locator("#msgs .msg.from-user", { has: page.locator("s.orig") });
  await expect(fixed).toHaveCount(1);
  await expect(fixed.locator("s.orig")).toHaveText("¿Cuántas camas hay en Medellín?");
  await expect(fixed.locator(".fixed")).toHaveText("¿Cuántas camas hay en Melgar?");
  await expect(fixed.locator(".fix-arrow svg")).toHaveCount(1);
  await expect(fixed.locator(".fix-arrow .sr-only")).toHaveText("corregido a");
  await expect(fixed.locator(".msg-meta")).toContainText("corregido");
  expect(await fixed.locator("s.orig").evaluate((el) => getComputedStyle(el).textDecorationLine)).toContain("line-through");

  const invalidated = page.locator("#msgs details.evidence.invalidated");
  await expect(invalidated).toHaveCount(1);
  await expect(invalidated.locator("summary")).toContainText("invalidada");
  await invalidated.locator("summary").click();
  await expect(invalidated.locator(".void")).toContainText("Evidencia invalidada por una corrección");
  await expect(invalidated.locator("pre.soql")).toContainText("MEDELLÍN");
  await expect(invalidated.getByRole("button", { name: "Reconsultar" })).toHaveCount(0);
  // The new query uses the confirmed place.
  await expect(page.locator("#msgs .msg.from-agent .text").last()).toContainText("En Melgar, Tolima hay 9 camas instaladas");
});

test("texto no escuchado atenuado tras la interrupción (A-11)", async () => {
  const cut = page.locator("#msgs .msg.from-agent", { has: page.locator(".unheard") });
  await expect(cut).toHaveCount(1);
  const heard = await cut.locator(".text").evaluate((el) => el.firstChild?.textContent ?? "");
  const unheard = await cut.locator(".unheard").innerText();
  expect(heard.trim().split(/\s+/).length).toBeGreaterThanOrEqual(5);
  expect(unheard.trim().length).toBeGreaterThan(5);
  const style = await cut.locator(".unheard").evaluate((el) => {
    const cs = getComputedStyle(el);
    return { opacity: Number(cs.opacity), line: cs.textDecorationLine, color: cs.color, parent: getComputedStyle(el.parentElement!).color };
  });
  expect(style.opacity).toBeLessThan(1);
  expect(style.color).not.toBe(style.parent);
  await expect(cut.locator(".msg-meta")).toContainText("interrumpido");
  await expect(cut.locator(".unheard")).toHaveAttribute("title", /no llegó a oírse/);
  // An interrupted answer is not marked as delivered.
  await expect(cut.locator(".tick")).toHaveCount(0);
});

test("subtítulos: región aria-live con el último enunciado completo (NF-06)", async () => {
  const live = page.locator("#subtitle-live");
  await expect(live).toHaveAttribute("aria-live", "polite");
  await expect(live).toContainText(/^(Asistente|Tú): /);
  await expect(page.locator("#subtitle")).toHaveAttribute("aria-hidden", "true");
  await expect(page.locator(".live-badge")).toHaveAttribute("role", "status");
  // The transcript list itself must not announce every partial.
  await expect(page.locator("#msgs")).toHaveAttribute("aria-live", "off");
});

test("pestaña «API en vivo»: las cuatro consultas con su traza y el contador (A-24)", async () => {
  await expect(page.locator("#api-count")).toHaveText("4");
  await page.locator("#tab-api").click();
  await expect(page.locator("#pane-api")).toBeVisible();
  await expect(page.locator("#pane-conversacion")).toBeHidden();
  const items = page.locator("#api-list > li.api-item");
  await expect(items).toHaveCount(4);
  for (const item of await items.all()) {
    await expect(item.locator("pre.soql")).toContainText("SELECT");
    await expect(item.locator(".meta")).toContainText(/\d+ ms/);
    await expect(item.locator(".meta")).toContainText(/\d+ filas?/);
    await expect(item.locator(".src")).toContainText("Corte: Nov 5 2022");
  }
  await expect(page.locator("#api-list > li.invalidated")).toHaveCount(1);
  await expect(page.locator("#api-origin")).toContainText("respuestas grabadas");
  await expect(page.locator("#api-list")).toHaveAttribute("aria-live", "polite");
  await shot(page, "consola-api-en-vivo");
});

test("panel de afecto: etiquetas rotuladas como estimación y estilo con motivo (A-14, A-22)", async () => {
  await page.locator("#tab-analisis").click();
  const affect = page.locator("#affect");
  await expect(affect).toBeVisible();
  await expect(affect.locator(".pane-head")).toContainText("Estimaciones");
  await expect(affect.locator(".pane-head")).toContainText("No son un diagnóstico");
  await expect(affect.locator(".reading .facts")).toContainText("Método");
  await expect(affect.locator(".reading .facts")).toContainText(/estimación del texto/);
  await expect(affect.locator(".reading .about")).toContainText("Intervención del turno");
  await expect(affect.locator("svg.valence")).toHaveAttribute("aria-label", /Línea de valencia/);
  const style = affect.locator(".style");
  await expect(style).toContainText("Estilo vigente");
  await expect(style.locator(".why")).toContainText(/Aplica desde el turno \d+/);
  expect((await style.locator(".why").innerText()).length).toBeGreaterThan(30);
  // No percentage that could read as a calibrated confidence.
  expect(await affect.innerText()).not.toMatch(/\d\s?%/);
  await expect(page.locator(".site-footer")).toContainText("Las emociones son estimaciones, no un diagnóstico");
  await shot(page, "consola-analisis");
});

test("HUD de latencia: motor y modelo activos, historial por turno e intentos (A-23, F-10)", async () => {
  const hud = page.locator("#hud");
  await expect(hud.locator("#hud-engine")).toContainText("Gemini Live");
  await expect(hud.locator("#hud-engine")).toContainText("modelo:");
  await expect(hud.locator("#hud-engine")).toContainText("tiempos simulados");
  await expect(hud.locator(".stats")).toContainText("Primer audio útil");
  await expect(hud.locator(".stats")).toContainText("Aviso previo");
  await expect(hud.locator(".stats")).toContainText("Intentos de motor");
  const rows = hud.locator("#hud-table tbody tr");
  await expect(rows).toHaveCount(3);
  // Every scripted turn ran on OpenAI; the switch counts as a second attempt on the last one.
  for (const row of await rows.all()) await expect(row.locator("td").nth(1)).toHaveText("OpenAI Realtime");
  await expect(rows.first().locator("td").last()).toHaveText("2");
  await expect(hud.locator("#hud-table")).toContainText("No, dije Melgar.");
});

test("todo el guion corre sin errores de JavaScript y sin pedir el micrófono (motor simulado)", async () => {
  expect(problems.pageErrors).toEqual([]);
  expect(problems.consoleErrors).toEqual([]);
  expect(problems.failedRequests.filter((r) => !/.vrm .*ERR_ABORTED/.test(r))).toEqual([]);
  expect(await micRequests(page)).toBe(0);
});

test("ningún emoji usado como icono tras renderizar todos los paneles", async () => {
  for (const tab of ["conversacion", "api", "analisis", "ayuda"]) {
    await page.locator(`#tab-${tab}`).click();
    const html = await page.locator("body").innerHTML();
    expect(html.match(PICTOGRAPH) ?? [], `pestaña ${tab}`).toEqual([]);
  }
  await shot(page, "consola-ayuda");
  await page.locator("#tab-conversacion").click();
});

test("«Reiniciar» borra la transcripción, las consultas y las estimaciones (A-25)", async () => {
  await page.locator("#btn-restart").click();
  await expect(page.locator("#msgs > li")).toHaveCount(0);
  await expect(page.locator("#chat-empty")).toBeVisible();
  await expect(page.locator("#api-count")).toBeHidden();
  await expect(page.locator("#btn-toggle")).toHaveText(/Activar micrófono/);
  await expect(page.locator("#state-badge")).toHaveText("En línea");
  await expect(page.locator("#status-label")).toHaveText("Listo para conversar");
  await expect(page.locator("#subtitle")).toBeHidden();
  await expect(page.locator("#btn-repeat")).toBeDisabled();
  await expect(page.locator("#btn-correct")).toBeDisabled();
  await page.locator("#tab-api").click();
  await expect(page.locator("#api-list > li.api-item")).toHaveCount(0);
  await page.locator("#tab-analisis").click();
  await expect(page.locator("#affect .reading")).toHaveCount(0);
  await expect(page.locator("#affect .affect-empty")).toBeVisible();
  await expect(page.locator("#hud .hud-empty")).toBeVisible();
  // Nothing was persisted in the browser either.
  const stored = await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length, cookies: document.cookie }));
  expect(stored).toEqual({ local: 0, session: 0, cookies: "" });
  // And no late event of the stopped session brings anything back.
  await page.locator("#tab-conversacion").click();
  await page.waitForTimeout(2_500);
  await expect(page.locator("#msgs > li")).toHaveCount(0);
});

test("tras «Reiniciar» no queda texto de la conversación en ninguna parte del DOM (A-25)", async () => {
  // The screen-reader live region is part of the transcript too.
  await expect(page.locator("#subtitle-live")).toBeEmpty();
  expect(await page.locator("body").innerText()).not.toContain("Melgar, Tolima hay 9 camas");
});
