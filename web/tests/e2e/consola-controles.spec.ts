/**
 * Controls of `/consola` one by one (docs/08 §10; F-12, A-11, A-14, A-22, A-25),
 * each on a fresh page, plus keyboard use, small screens and the avatar fallback.
 */
import type { Page } from "@playwright/test";
import { contrastOf, expect, overflowX, shot, test } from "./fixtures";

const lastAnswer = (page: Page) => page.locator("#msgs .msg.from-agent:not(.is-evidence):not(.is-ack) .text").last();

/** Sends a question by text and waits for the scripted engine to finish answering it. */
async function ask(page: Page, question: string, expected: string | RegExp): Promise<void> {
  await page.locator("#ask-input").fill(question);
  await page.locator("#ask-input").press("Enter");
  await expect(lastAnswer(page)).toContainText(expected, { timeout: 40_000 });
  await expect(page.locator("#state-badge")).toHaveText("Te escucho", { timeout: 20_000 });
}

test.describe("modo texto (F-12)", () => {
  test("enviar una pregunta: burbuja «por texto», respuesta con cifra y evidencia", async ({ page, problems }) => {
    await page.goto("/consola");
    await page.locator("#ask-input").fill("¿Cuántas camas hay en total?");
    await page.locator("#ask-form button[type=submit]").click();
    await expect(page.locator("#ask-input")).toHaveValue("");
    const user = page.locator("#msgs .msg.from-user");
    await expect(user.locator(".text")).toHaveText("¿Cuántas camas hay en total?", { timeout: 30_000 });
    await expect(user.locator(".msg-meta")).toContainText("por texto");
    await expect(page.locator("#msgs .msg.is-ack .text")).toContainText("Déjame verificarlo en datos.gov.co", { timeout: 20_000 });
    await expect(lastAnswer(page)).toContainText("97.036 camas instaladas", { timeout: 30_000 });
    await expect(lastAnswer(page)).toContainText("corte a noviembre de 2022");
    const card = page.locator("#msgs details.evidence");
    await expect(card).toHaveCount(1);
    await expect(card.locator("summary")).toContainText("1 fila");
    expect(problems.pageErrors).toEqual([]);
    expect(problems.consoleErrors).toEqual([]);
    await shot(page, "consola-modo-texto");
  });

  test("la pregunta escrita aparece en el chat enseguida, no después del resumen inicial", async ({ page }) => {
    await page.goto("/consola");
    await page.locator("#ask-input").fill("¿Cuántas camas hay en total?");
    await page.locator("#ask-input").press("Enter");
    // Whoever types a question must see it echoed at once (≤ 2 s), even if the brief plays first.
    await expect(page.locator("#msgs .msg.from-user .text")).toHaveText("¿Cuántas camas hay en total?", { timeout: 2_000 });
  });

  test("un envío vacío no hace nada", async ({ page }) => {
    await page.goto("/consola");
    await page.locator("#ask-input").fill("   ");
    await page.locator("#ask-input").press("Enter");
    await page.waitForTimeout(500);
    await expect(page.locator("#btn-toggle")).toHaveAttribute("data-running", "false");
    await expect(page.locator("#msgs > li")).toHaveCount(0);
  });

  test("una pregunta sugerida del chat se envía al pulsarla", async ({ page }) => {
    await page.goto("/consola");
    await page.locator("#chips button", { hasText: "¿Cuántas IPS hay en Bogotá?" }).click();
    await expect(lastAnswer(page)).toContainText("1.270", { timeout: 40_000 });
    await expect(page.locator("#chat-empty")).toBeHidden();
  });

  test("pregunta fuera de alcance: límite honesto de la fuente, sin consulta (A-08)", async ({ page }) => {
    await page.goto("/consola");
    await ask(page, "¿Hay cama disponible hoy?", "no tiene disponibilidad en tiempo real");
    await expect(page.locator("#msgs details.evidence")).toHaveCount(0);
    await expect(page.locator("#api-count")).toBeHidden();
  });

  test("el texto del usuario se escapa: no se interpreta como HTML", async ({ page, problems }) => {
    await page.goto("/consola");
    await page.locator("#ask-input").fill('<img src=x onerror="window.__xss=1"> gracias');
    await page.locator("#ask-input").press("Enter");
    await expect(page.locator("#msgs .msg.from-user .text")).toContainText("<img src=x", { timeout: 30_000 });
    await expect(page.locator("#msgs img")).toHaveCount(0);
    expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
    expect(problems.failedRequests.filter((r) => !/.vrm .*ERR_ABORTED/.test(r))).toEqual([]);
  });
});

test.describe("interrumpir, repetir y corregir", () => {
  test("«Silenciar» corta al agente: lo no escuchado queda atenuado y se vuelve a escuchar (A-11)", async ({ page }) => {
    await page.goto("/consola");
    await page.locator("#btn-toggle").click();
    await expect(page.locator("#btn-mute")).toBeEnabled({ timeout: 5_000 });
    await page.waitForTimeout(1_500);
    const t0 = Date.now();
    await page.locator("#btn-mute").click();
    await expect(page.locator("#state-badge")).not.toHaveText("Hablando", { timeout: 1_000 });
    expect(Date.now() - t0).toBeLessThan(1_000);
    const cut = page.locator("#msgs .msg.from-agent").first();
    await expect(cut.locator(".unheard")).toBeVisible();
    await expect(cut.locator(".msg-meta")).toContainText("interrumpido");
    await expect(page.locator("#btn-mute")).toBeDisabled();
    // Nothing more is said for that generation.
    const text = await cut.locator(".text").innerText();
    await page.waitForTimeout(1_500);
    expect(await cut.locator(".text").innerText()).toBe(text);
    await shot(page, "consola-interrumpido");
  });

  test("la tecla Esc también interrumpe", async ({ page }) => {
    await page.goto("/consola");
    await page.locator("#btn-toggle").click();
    await expect(page.locator("#state-badge")).toHaveText("Hablando", { timeout: 5_000 });
    await page.waitForTimeout(1_200);
    await page.keyboard.press("Escape");
    await expect(page.locator("#msgs .msg.from-agent .unheard")).toBeVisible();
    await expect(page.locator("#btn-toggle")).toHaveAttribute("data-running", "true");
  });

  test("«Detener» termina la sesión y conserva la transcripción", async ({ page }) => {
    await page.goto("/consola");
    await page.locator("#btn-toggle").click();
    await expect(page.locator("#msgs .msg.from-agent")).toHaveCount(1, { timeout: 5_000 });
    await page.waitForTimeout(1_000);
    await page.locator("#btn-toggle").click();
    await expect(page.locator("#btn-toggle")).toHaveText(/Activar micrófono/);
    await expect(page.locator("#status-label")).toHaveText("Conversación detenida");
    await expect(page.locator("#msgs .msg.from-agent")).toHaveCount(1);
    // A stopped answer must not stay "typing" for ever.
    await expect(page.locator("#msgs .typing")).toHaveCount(0);
  });

  test("«Repetir» vuelve a decir la última respuesta sin otra consulta", async ({ page }) => {
    await page.goto("/consola");
    await expect(page.locator("#btn-repeat")).toBeDisabled();
    await ask(page, "¿Cuántas IPS hay en Bogotá?", "1.270");
    const first = await lastAnswer(page).innerText();
    await expect(page.locator("#btn-repeat")).toBeEnabled();
    await page.locator("#btn-repeat").click();
    await expect(page.locator("#msgs .msg.from-user")).toHaveCount(2, { timeout: 10_000 });
    await expect(page.locator("#state-badge")).toHaveText("Te escucho", { timeout: 30_000 });
    expect(await lastAnswer(page).innerText()).toBe(first);
    await expect(page.locator("#msgs details.evidence")).toHaveCount(1);
  });

  test("«Corregir lo que dije»: original → corregido, evidencia invalidada y nueva consulta (A-09)", async ({ page }) => {
    await page.goto("/consola");
    await expect(page.locator("#btn-correct")).toBeDisabled();
    await ask(page, "¿Cuántas camas hay en Medellín?", "6.280");
    await page.locator("#btn-correct").click();
    const input = page.locator("#fix-input");
    await expect(input).toBeVisible();
    await expect(input).toBeFocused();
    await expect(input).toHaveValue("¿Cuántas camas hay en Medellín?");
    await input.fill("¿Cuántas camas hay en Melgar?");
    await input.press("Enter");
    await expect(page.locator("#fix-form")).toBeHidden();
    const original = page.locator("#msgs .msg.from-user").first();
    await expect(original.locator("s.orig")).toHaveText("¿Cuántas camas hay en Medellín?");
    await expect(original.locator(".fixed")).toHaveText("¿Cuántas camas hay en Melgar?");
    await expect(page.locator("#msgs details.evidence.invalidated")).toHaveCount(1);
    await expect(lastAnswer(page)).toContainText("En Melgar, Tolima hay 9 camas", { timeout: 30_000 });
    await expect(page.locator("#msgs details.evidence")).toHaveCount(2);
    await shot(page, "consola-corregir");
  });

  test("«Cancelar» cierra el formulario de corrección sin cambiar nada", async ({ page }) => {
    await page.goto("/consola");
    await ask(page, "¿Cuántas camas hay en Medellín?", "6.280");
    await page.locator("#btn-correct").click();
    await page.locator("#fix-cancel").click();
    await expect(page.locator("#fix-form")).toBeHidden();
    await expect(page.locator("#msgs s.orig")).toHaveCount(0);
    await expect(page.locator("#msgs details.evidence.invalidated")).toHaveCount(0);
  });
});

test.describe("afecto y estilo (A-14, A-22)", () => {
  test("«Más directo»: preferencia explícita visible con motivo; la respuesta siguiente es más breve", async ({ page }) => {
    await page.goto("/consola");
    await ask(page, "¿Cuántas camas hay en total?", "97.036");
    const long = await lastAnswer(page).innerText();
    await page.locator("#btn-direct").click();
    await expect(page.locator("#btn-direct")).toHaveAttribute("aria-pressed", "true");
    await page.locator("#ask-input").fill("¿Cuántas camas hay en total?");
    await page.locator("#ask-input").press("Enter");
    await expect(page.locator("#msgs details.evidence")).toHaveCount(2, { timeout: 30_000 });
    await expect(page.locator("#state-badge")).toHaveText("Te escucho", { timeout: 20_000 });
    const short = await lastAnswer(page).innerText();
    expect(short.length).toBeLessThan(long.length / 2);
    expect(short).toContain("97.036");
    await page.locator("#tab-analisis").click();
    const style = page.locator("#affect .style");
    await expect(style.locator(".style-name")).toContainText("Directo");
    await expect(style.locator(".style-name")).toContainText("preferencia explícita");
    await expect(style.locator(".why")).toContainText("Lo pediste");
    await shot(page, "consola-estilo-directo");
  });

  test("«me estás confundiendo, sé más directo»: se estima frustración y la siguiente respuesta es más breve (A-14)", async ({ page }) => {
    await page.goto("/consola");
    await ask(page, "¿Cuántas camas hay en total?", "97.036");
    const long = await lastAnswer(page).innerText();
    await ask(page, "Me estás confundiendo, sé más directo", "Entendido");
    await page.locator("#tab-analisis").click();
    const reading = page.locator("#affect .reading");
    await expect(reading.locator(".facts")).toContainText("frustración", { timeout: 5_000 });
    await expect(reading.locator(".facts")).toContainText("negativo");
    await expect(reading.locator(".facts")).toContainText("estimación del texto");
    await page.locator("#tab-conversacion").click();
    await page.locator("#ask-input").fill("¿Cuántas camas hay en total?");
    await page.locator("#ask-input").press("Enter");
    await expect(page.locator("#msgs details.evidence")).toHaveCount(2, { timeout: 30_000 });
    await expect(page.locator("#state-badge")).toHaveText("Te escucho", { timeout: 20_000 });
    const next = await lastAnswer(page).innerText();
    // The agent just promised «desde ahora respondo más breve»: the next answer has to be.
    expect(next).toContain("97.036");
    expect(next.length, `siguiente respuesta: «${next}»`).toBeLessThan(long.length);
  });

  test("dos señales seguidas de frustración cambian el estilo con motivo visible (A-22)", async ({ page }) => {
    await page.goto("/consola");
    await ask(page, "Me estás confundiendo", /./);
    await page.locator("#tab-analisis").click();
    await expect(page.locator("#affect .signal")).toContainText("1 de 2 señales seguidas de frustración", { timeout: 5_000 });
    await expect(page.locator("#affect .style-name")).toContainText("Neutro");
    await page.locator("#tab-conversacion").click();
    await ask(page, "Sé más breve, me confundes", /./);
    await page.locator("#tab-analisis").click();
    await expect(page.locator("#affect .style-name")).toContainText("Directo", { timeout: 5_000 });
    await expect(page.locator("#affect .style-name")).toContainText("inferido");
    await expect(page.locator("#affect .style .why")).toContainText("Parece frustrado");
    await expect(page.locator("#affect .style .why")).toContainText(/Aplica desde el turno \d/);
  });
});

test.describe("consentimiento del análisis de voz (A-25) @pendiente-rediseno", () => {
  test("encenderlo pide consentimiento explícito; rechazar lo deja apagado", async ({ page }) => {
    await page.goto("/consola#ayuda");
    const sw = page.getByRole("switch", { name: "Análisis de voz" });
    await expect(sw).toHaveAttribute("aria-checked", "false");
    await expect(page.locator("#help .ai-notice")).toContainText("inteligencia artificial, no con una persona");
    await sw.click();
    const dialog = page.getByRole("dialog", { name: "¿Analizar también tu tono de voz?" });
    await expect(dialog).toBeVisible();
    expect(await page.locator("#consent-dialog").evaluate((d: HTMLDialogElement) => d.matches(":modal"))).toBe(true);
    await expect(dialog).toContainText("No se guarda audio");
    await expect(dialog).toContainText("estimación incierta, nunca un diagnóstico");
    await shot(page, "consola-consentimiento");
    await dialog.getByRole("button", { name: "No, solo el texto" }).click();
    await expect(dialog).toBeHidden();
    await expect(sw).toHaveAttribute("aria-checked", "false");
    await expect(sw).toBeFocused();
    await expect(page.locator("#voice-help")).toContainText("solo del texto");
  });

  test("Esc cierra el diálogo sin dar el consentimiento", async ({ page }) => {
    await page.goto("/consola#ayuda");
    const sw = page.getByRole("switch", { name: "Análisis de voz" });
    await sw.click();
    await expect(page.locator("#consent-dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator("#consent-dialog")).toBeHidden();
    await expect(sw).toHaveAttribute("aria-checked", "false");
  });

  test("aceptar lo enciende, el panel lo rotula como estimación combinada y se puede apagar sin diálogo", async ({ page }) => {
    await page.goto("/consola#ayuda");
    const sw = page.getByRole("switch", { name: "Análisis de voz" });
    await sw.click();
    await page.getByRole("button", { name: "Sí, analizar mi voz" }).click();
    await expect(sw).toHaveAttribute("aria-checked", "true");
    await expect(page.locator("#voice-help")).toContainText("El audio no se guarda");

    await page.locator("#tab-conversacion").click();
    await ask(page, "No, dije Melgar.", /./);
    await page.locator("#tab-analisis").click();
    const reading = page.locator("#affect .reading");
    await expect(reading.locator(".facts")).toContainText("estimación combinada (texto y voz)", { timeout: 5_000 });
    // Voice and text disagree for this utterance: the panel says so (A-21).
    await expect(reading.locator(".split")).toContainText("texto y voz no coinciden");
    await expect(reading.locator(".split")).toContainText("Por la voz");
    await shot(page, "consola-afecto-discrepancia");

    await page.locator("#tab-ayuda").click();
    await sw.click();
    await expect(page.locator("#consent-dialog")).toBeHidden();
    await expect(sw).toHaveAttribute("aria-checked", "false");
  });

  test("«Reiniciar» retira el consentimiento", async ({ page }) => {
    await page.goto("/consola#ayuda");
    const sw = page.getByRole("switch", { name: "Análisis de voz" });
    await sw.click();
    await page.getByRole("button", { name: "Sí, analizar mi voz" }).click();
    await expect(sw).toHaveAttribute("aria-checked", "true");
    await page.locator("#tab-conversacion").click();
    await page.locator("#btn-restart").click();
    await page.locator("#tab-ayuda").click();
    await expect(sw).toHaveAttribute("aria-checked", "false");
  });
});

test.describe("selector de motor y voz (F-10)", () => {
  test("elegir Gemini con la sesión detenida actualiza el HUD y desactiva la voz clonada", async ({ page }) => {
    await page.goto("/consola#analisis");
    await expect(page.locator("#hud-engine")).toContainText("OpenAI Realtime");
    await page.locator("#engine-select").selectOption("gemini");
    await expect(page.locator("#hud-engine")).toContainText("Gemini Live");
    await expect(page.locator('#voice-select option[value="cloned"]')).toHaveAttribute("disabled", "");
    await expect(page.locator('#voice-select option[value="cloned"]')).toHaveText("Voz clonada (solo con OpenAI)");
    await expect(page.locator("#voice-select")).toHaveValue("engine");
  });

  test("cambiar de motor en plena sesión conserva la conversación y avisa (guion §10, min 8)", async ({ page }) => {
    await page.goto("/consola");
    await ask(page, "¿Cuántas IPS hay en Bogotá?", "1.270");
    const before = await page.locator("#msgs > li").count();
    await page.locator("#engine-select").selectOption("gemini");
    const notice = page.locator("#msgs .msg.system-session");
    await expect(notice).toContainText("motor cambiado a Gemini Live", { timeout: 10_000 });
    await expect(notice).toContainText("elegido en el selector");
    await expect(page.locator("#msgs > li")).toHaveCount(before + 1);
    await ask(page, "¿Cuántas IPS hay en Bogotá?", "1.270");
    await page.locator("#tab-analisis").click();
    const rows = page.locator("#hud-table tbody tr");
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0).locator("td").nth(1)).toHaveText("Gemini Live");
    await expect(rows.nth(1).locator("td").nth(1)).toHaveText("OpenAI Realtime");
    await shot(page, "consola-hud-dos-motores");
  });
});

test.describe("teclado y accesibilidad básica (NF-06)", () => {
  test("pestañas: roles ARIA, flechas, Inicio/Fin y un solo panel visible", async ({ page }) => {
    await page.goto("/consola");
    const tablist = page.getByRole("tablist", { name: "Paneles" });
    await expect(tablist.getByRole("tab")).toHaveCount(4);
    for (const tab of await tablist.getByRole("tab").all()) {
      const controls = await tab.getAttribute("aria-controls");
      await expect(page.locator(`#${controls}`)).toHaveAttribute("role", "tabpanel");
      await expect(page.locator(`#${controls}`)).toHaveAttribute("aria-labelledby", (await tab.getAttribute("id"))!);
      expect((await tab.innerText()).trim().length).toBeGreaterThan(0);
    }
    await page.locator("#tab-conversacion").focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.locator("#tab-api")).toBeFocused();
    await expect(page.locator("#tab-api")).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("#pane-api")).toBeVisible();
    await expect(page.locator("#pane-conversacion")).toBeHidden();
    await expect(page).toHaveURL(/#api$/);
    await page.keyboard.press("End");
    await expect(page.locator("#tab-ayuda")).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect(page.locator("#tab-conversacion")).toBeFocused();
    await page.keyboard.press("ArrowLeft");
    await expect(page.locator("#tab-ayuda")).toBeFocused();
    await page.keyboard.press("Home");
    await expect(page.locator("#tab-conversacion")).toHaveAttribute("aria-selected", "true");
    expect(await page.locator('[role="tabpanel"]:visible').count()).toBe(1);
    // Roving tabindex: only the selected tab is in the tab order.
    expect(await page.locator('[role="tab"][tabindex="0"]').count()).toBe(1);
  });

  test("los enlaces de la cabecera cambian de pestaña sin navegar", async ({ page }) => {
    await page.goto("/consola");
    await page.evaluate(() => {
      (window as unknown as { __sameDocument: boolean }).__sameDocument = true;
    });
    await page.locator('.site-header nav a[data-tab-link="analisis"]').click();
    await expect(page.locator("#pane-analisis")).toBeVisible();
    await expect(page.locator('.site-header nav a[data-tab-link="analisis"]')).toHaveAttribute("aria-current", "page");
    await expect(page.locator('.site-header nav a[aria-current="page"]')).toHaveCount(1);
    expect(await page.evaluate(() => (window as unknown as { __sameDocument?: boolean }).__sameDocument)).toBe(true);
  });

  test("todo control tiene nombre accesible y todo campo tiene etiqueta", async ({ page }) => {
    await page.goto("/consola");
    const unnamed = await page.evaluate(() => {
      const name = (el: Element): string => {
        const labelled = el.getAttribute("aria-labelledby");
        const fromIds = labelled ? labelled.split(/\s+/).map((id) => document.getElementById(id)?.textContent ?? "").join(" ") : "";
        const label = el instanceof HTMLInputElement || el instanceof HTMLSelectElement ? Array.from(el.labels ?? []).map((l) => l.textContent).join(" ") : "";
        return (el.getAttribute("aria-label") || fromIds || label || el.textContent || "").trim();
      };
      return Array.from(document.querySelectorAll("button, a[href], input, select, [role=tab], [role=switch]"))
        .filter((el) => name(el) === "")
        .map((el) => el.outerHTML.slice(0, 120));
    });
    expect(unnamed).toEqual([]);
    // Decorative icons are hidden from assistive technology.
    const exposed = await page.locator("svg.lucide:not([aria-hidden=true])").count();
    expect(exposed).toBe(0);
    await expect(page.locator("canvas#avatar-canvas")).toHaveAttribute("aria-hidden", "true");
    await expect(page.locator("h1")).toHaveCount(1);
  });

  test("recorrido con Tab: el foco siempre es visible y llega a los controles principales", async ({ page }) => {
    await page.goto("/consola");
    await page.waitForLoadState("networkidle");
    const seen: string[] = [];
    const invisible: string[] = [];
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press("Tab");
      const info = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return null;
        const cs = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return {
          id: el.id || el.getAttribute("data-tab-link") || el.className || el.tagName,
          outline: cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 2,
          shadow: cs.boxShadow !== "none",
          onScreen: r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth,
        };
      });
      if (!info) continue;
      seen.push(String(info.id));
      if (!info.outline || !info.onScreen) invisible.push(`${info.id} outline=${info.outline} onScreen=${info.onScreen}`);
    }
    expect(invisible).toEqual([]);
    for (const id of ["engine-select", "btn-toggle", "tab-conversacion", "btn-direct", "btn-restart", "ask-input", "btn-mic"]) {
      expect(seen, `orden de foco: ${seen.join(" > ")}`).toContain(id);
    }
    // Disabled controls are skipped, never focus traps.
    expect(seen).not.toContain("btn-mute");
  });

  test("se puede conversar solo con el teclado", async ({ page }) => {
    await page.goto("/consola");
    await page.locator("#ask-input").focus();
    await page.keyboard.type("¿Cuántas IPS hay en Bogotá?");
    await page.keyboard.press("Enter");
    await expect(lastAnswer(page)).toContainText("1.270", { timeout: 40_000 });
    await expect(page.locator("#state-badge")).toHaveText("Te escucho", { timeout: 20_000 });
    await page.waitForTimeout(1_500); // let the analyst result land: no re-render after this
    const summary = page.locator("#msgs details.evidence summary");
    await summary.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator("#msgs details.evidence")).toHaveAttribute("open", "");
    await page.keyboard.press("Tab"); // the SoQL block is focusable so it can be scrolled
    await expect(page.locator("#msgs pre.soql")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Reconsultar" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("#msgs .requery.ok")).toContainText("coincide", { timeout: 10_000 });
  });

  test("el foco del teclado no se pierde cuando el chat se vuelve a pintar", async ({ page }) => {
    await page.goto("/consola");
    await page.locator("#ask-input").fill("¿Cuántas IPS hay en Bogotá?");
    await page.keyboard.press("Enter");
    // Open the evidence card with the keyboard while the answer is still being spoken.
    const summary = page.locator("#msgs details.evidence summary");
    await expect(summary).toBeVisible({ timeout: 40_000 });
    await summary.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator("#msgs details.evidence")).toHaveAttribute("open", "");
    await expect(page.locator("#state-badge")).toHaveText("Te escucho", { timeout: 30_000 });
    const lostAfterOpen = await page.evaluate(() => document.activeElement === document.body);
    // And again after «Reconsultar», which re-renders the card it lives in.
    const button = page.getByRole("button", { name: "Reconsultar" });
    await button.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator("#msgs .requery.ok")).toContainText("coincide", { timeout: 10_000 });
    const lostAfterRequery = await page.evaluate(() => document.activeElement === document.body);
    expect({ lostAfterOpen, lostAfterRequery }).toEqual({ lostAfterOpen: false, lostAfterRequery: false });
  });

  test("contraste AA (4,5:1) en los textos clave de la consola", async ({ page }) => {
    await page.goto("/consola");
    await ask(page, "¿Cuántas camas hay en total?", "97.036");
    const targets: Record<string, string> = {
      "botón verde «Activar micrófono/Detener»": "#btn-toggle",
      "botón azul «Enviar»": "#ask-form button[type=submit]",
      "texto de la burbuja del agente": "#msgs .msg.from-agent .text",
      "texto de la burbuja del usuario": "#msgs .msg.from-user .text",
      "hora de la burbuja": "#msgs .msg.from-user .msg-meta time",
      "aviso previo (ack)": "#msgs .msg.is-ack .text",
      "resumen de la evidencia": "#msgs details.evidence summary",
      "estado bajo el avatar": "#status-sub",
      "fuente en la cabecera del chat": ".chat-head .src",
      "placeholder/entrada": "#ask-input",
      "pie de página": ".site-footer .quiet",
      "subtítulo sobre el avatar": "#subtitle",
      "pestaña no seleccionada": "#tab-api",
    };
    const failures: string[] = [];
    for (const [label, selector] of Object.entries(targets)) {
      const c = await contrastOf(page, selector);
      if (!c) failures.push(`${label}: no existe ${selector}`);
      else if (c.ratio < 4.5) failures.push(`${label} (${selector}): ${c.ratio}:1, ${c.fg} sobre ${c.bg}, ${c.px}px`);
    }
    // The green button sits on white; with the session stopped it is the main call to action.
    await page.locator("#btn-restart").click();
    await expect(page.locator("#btn-toggle")).toHaveAttribute("data-running", "false");
    await page.mouse.move(700, 300);
    await page.waitForTimeout(500); // background-color transition
    const green = await contrastOf(page, "#btn-toggle");
    if (green && green.ratio < 4.5) failures.push(`botón verde «Activar micrófono» en reposo: ${green.ratio}:1, ${green.fg} sobre ${green.bg}, ${green.px}px`);
    expect(failures).toEqual([]);
  });
});

test.describe("vistas", () => {
  test("390 px: una columna, sin desborde horizontal y con los controles a la vista", async ({ page, problems }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/consola");
    await page.waitForLoadState("networkidle");
    await shot(page, "consola-390-inicial", true);
    expect(await overflowX(page)).toBe(0);
    const stage = (await page.locator("#stage").boundingBox())!;
    const chat = (await page.locator(".panel-card").boundingBox())!;
    expect(chat.y).toBeGreaterThanOrEqual(stage.y + stage.height);
    expect(stage.width).toBeLessThanOrEqual(390);
    await expect(page.locator("#btn-toggle")).toBeVisible();
    await expect(page.locator("#engine-select")).toBeVisible();

    await page.locator("#ask-input").scrollIntoViewIfNeeded();
    await page.locator("#ask-input").fill("¿Cuántas camas hay en total?");
    await page.locator("#ask-form button[type=submit]").click();
    await expect(lastAnswer(page)).toContainText("97.036", { timeout: 40_000 });
    await page.locator("#msgs details.evidence summary").click();
    await expect(page.locator("#msgs pre.soql")).toBeVisible();
    expect(await overflowX(page)).toBe(0);
    // Every control of the chat stays inside the viewport width.
    for (const sel of ["#ask-input", "#ask-form button[type=submit]", "#btn-mic", "#btn-restart", "#btn-correct"]) {
      const box = (await page.locator(sel).boundingBox())!;
      expect(box.x, sel).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width, sel).toBeLessThanOrEqual(390);
    }
    for (const tab of ["api", "analisis", "ayuda"]) {
      await page.locator(`#tab-${tab}`).click();
      await expect(page.locator(`#pane-${tab}`)).toBeVisible();
      expect(await overflowX(page), `pestaña ${tab}`).toBe(0);
      await shot(page, `consola-390-${tab}`, true);
    }
    await page.locator("#tab-conversacion").click();
    await shot(page, "consola-390-conversacion", true);
    expect(problems.pageErrors).toEqual([]);
  });

  test("390 px: objetivos táctiles de al menos 24 px (WCAG 2.5.8) y 44 px en las acciones principales", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/consola");
    const small: string[] = [];
    const check = async (sel: string, min: number): Promise<void> => {
      const box = (await page.locator(sel).boundingBox())!;
      if (box.height < min || box.width < min) small.push(`${sel}: ${Math.round(box.width)}×${Math.round(box.height)} (< ${min})`);
    };
    for (const sel of ["#btn-toggle", "#btn-mic", "#ask-form button[type=submit]", "#ask-input"]) await check(sel, 44);
    for (const sel of ["#btn-mute", "#tab-api", "#tab-analisis", "#btn-restart", "#btn-direct", "#btn-correct", "#btn-repeat", "#btn-zoom-in"]) await check(sel, 24);
    expect(small).toEqual([]);
  });

  test("1366×768: la consola cabe sin desplazar la página y el chat se desplaza dentro de su tarjeta", async ({ page }) => {
    await page.goto("/consola");
    await ask(page, "¿Cuántas camas hay en total?", "97.036");
    await ask(page, "¿Cuántas IPS hay en Bogotá?", "1.270");
    await ask(page, "¿Qué municipios tienen más camas?", "16.193");
    expect(await overflowX(page)).toBe(0);
    // The page itself cannot be scrolled away from the controls.
    await page.mouse.move(300, 300);
    await page.mouse.wheel(0, 800);
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    for (const sel of ["#btn-toggle", "#btn-mute", "#ask-input", "#ask-form button[type=submit]", "#btn-restart", ".site-footer"]) {
      await expect(page.locator(sel), sel).toBeInViewport({ ratio: 1 });
    }
    // The newest message is in view: the list follows the conversation.
    await expect(lastAnswer(page)).toBeInViewport();
    const scroll = await page.locator("#chat-scroll").evaluate((el) => ({ h: el.clientHeight, sh: el.scrollHeight }));
    expect(scroll.sh).toBeGreaterThan(scroll.h);
    expect(scroll.h).toBeGreaterThanOrEqual(180);
    // The four tabs fit in the header of the card without being clipped.
    const card = (await page.locator(".panel-card").boundingBox())!;
    for (const tab of await page.locator('[role="tab"]').all()) {
      const box = (await tab.boundingBox())!;
      expect(box.x + box.width).toBeLessThanOrEqual(card.x + card.width);
    }
    await shot(page, "consola-1366x768-conversacion");
  });
});

test.describe("pulido visual", () => {
  test("1366×768: el documento no crece por debajo de la ventana al llenarse el chat", async ({ page }) => {
    await page.goto("/consola");
    await ask(page, "¿Cuántas camas hay en total?", "97.036");
    await ask(page, "¿Cuántas IPS hay en Bogotá?", "1.270");
    await ask(page, "¿Qué municipios tienen más camas?", "16.193");
    const extra = await page.evaluate(() => {
      const beyond = Array.from(document.querySelectorAll<HTMLElement>("body *"))
        .filter((el) => getComputedStyle(el).position === "absolute" && el.getBoundingClientRect().bottom > innerHeight + 1)
        .map((el) => `${el.tagName.toLowerCase()}.${el.className}`);
      return { px: document.documentElement.scrollHeight - innerHeight, culprits: [...new Set(beyond)].slice(0, 5) };
    });
    // body.fill hides the overflow, but anything that scrolls it programmatically (focus, find-in-page,
    // scrollIntoView) would move the whole console out of place.
    expect(extra).toEqual({ px: 0, culprits: [] });
  });

  test("con la sesión en marcha, «Detener» no se pone verde al pasar el cursor", async ({ page }) => {
    await page.goto("/consola");
    const toggle = page.locator("#btn-toggle");
    await toggle.click();
    await expect(toggle).toHaveAttribute("data-running", "true");
    await page.mouse.move(700, 300);
    await page.waitForTimeout(400);
    const idle = await toggle.evaluate((el) => getComputedStyle(el).backgroundColor);
    await toggle.hover();
    await page.waitForTimeout(400);
    const hovered = await toggle.evaluate((el) => getComputedStyle(el).backgroundColor);
    // Green means «start»; a green «Detener» under the cursor reads as the opposite action.
    expect(hovered).toBe(idle);
  });
});

test.describe("avatar", () => {
  test("sin el modelo .vrm (404, como en el repo remoto) la página sigue funcionando con el orbe de respaldo", async ({ page, problems }) => {
    const requested: string[] = [];
    await page.route("**/*.vrm", (route) => {
      requested.push(route.request().url());
      return route.fulfill({ status: 404, contentType: "text/plain", body: "404" });
    });
    await page.goto("/consola");
    const stage = page.locator("#avatar-stage");
    await expect(stage).toHaveAttribute("data-avatar", /^(failed|absent)$/, { timeout: 30_000 });
    expect(requested.length).toBeGreaterThan(0);
    // The orb stays visible and the canvas stays hidden.
    await expect(stage.locator(".fallback")).toBeVisible();
    expect(await stage.locator(".fallback").evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
    expect(await page.locator("#avatar-canvas").evaluate((el) => getComputedStyle(el).opacity)).toBe("0");
    await shot(page, "consola-sin-vrm");
    // The console is fully usable.
    await page.locator("#ask-input").fill("¿Cuántas IPS hay en Bogotá?");
    await page.locator("#ask-input").press("Enter");
    await expect(lastAnswer(page)).toContainText("1.270", { timeout: 40_000 });
    await page.locator("#btn-camera").click();
    await page.locator("#btn-zoom-in").click();
    expect(problems.pageErrors).toEqual([]);
    // The only tolerated console error is the browser's own line for the missing file.
    const others = problems.consoleErrors.filter((e) => !/\.vrm/.test(e));
    expect(others).toEqual([]);
  });

  test("sin el modelo .vrm no queda ningún error en la consola del navegador (A-01)", async ({ page, problems }) => {
    await page.route("**/*.vrm", (route) => route.fulfill({ status: 404, contentType: "text/plain", body: "404" }));
    await page.goto("/consola");
    await expect(page.locator("#avatar-stage")).toHaveAttribute("data-avatar", /^(failed|absent)$/, { timeout: 30_000 });
    expect(problems.consoleErrors).toEqual([]);
  });

  test("si la descarga del modelo se corta, tampoco rompe la página", async ({ page, problems }) => {
    await page.route("**/*.vrm", (route) => route.abort("connectionreset"));
    await page.goto("/consola");
    await expect(page.locator("#avatar-stage")).toHaveAttribute("data-avatar", /^(failed|absent)$/, { timeout: 30_000 });
    await expect(page.locator("#avatar-stage .fallback")).toBeVisible();
    await page.locator("#btn-toggle").click();
    await expect(page.locator("#state-badge")).toHaveText("Hablando", { timeout: 5_000 });
    expect(problems.pageErrors).toEqual([]);
  });

  test("con un .vrm corrupto se queda el orbe", async ({ page, problems }) => {
    await page.route("**/*.vrm", (route) => route.fulfill({ status: 200, contentType: "model/gltf-binary", body: "esto no es un glb" }));
    await page.goto("/consola");
    await expect(page.locator("#avatar-stage")).toHaveAttribute("data-avatar", /^(failed|absent)$/, { timeout: 30_000 });
    await expect(page.locator("#avatar-stage .fallback")).toBeVisible();
    expect(problems.pageErrors).toEqual([]);
  });

  test("con el modelo presente el avatar termina cargado o cae al orbe, nunca se queda a medias", async ({ page, problems }) => {
    await page.goto("/consola");
    const stage = page.locator("#avatar-stage");
    await expect(stage).toHaveAttribute("data-avatar", /^(ready|failed|absent)$/, { timeout: 60_000 });
    const state = await stage.getAttribute("data-avatar");
    test.info().annotations.push({ type: "avatar", description: `data-avatar=${state}` });
    await page.waitForTimeout(1_500);
    await shot(page, `consola-avatar-${state}`);
    if (state === "ready") {
      expect(await page.locator("#avatar-canvas").evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
      await page.locator("#btn-toggle").click();
      await expect(page.locator("#state-badge")).toHaveText("Hablando", { timeout: 5_000 });
      await page.waitForTimeout(2_000);
      await shot(page, "consola-avatar-hablando");
    } else {
      await expect(stage.locator(".fallback")).toBeVisible();
    }
    expect(problems.pageErrors).toEqual([]);
  });
});
