/**
 * Cover page `/` (A-01, A-02, NF-06, NF-08) and the view transition into `/consola`.
 */
import { countMicRequests, expect, micRequests, overflowX, PICTOGRAPH, shot, test } from "./fixtures";

test.describe("portada", () => {
  test("carga sin errores de consola ni peticiones fallidas, y sin pedir el micrófono (A-01)", async ({ page, problems }) => {
    await countMicRequests(page);
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    expect(problems.pageErrors).toEqual([]);
    expect(problems.consoleErrors).toEqual([]);
    expect(problems.failedRequests).toEqual([]);
    expect(await micRequests(page)).toBe(0);
    await shot(page, "portada-1366x768");
    await shot(page, "portada-1366-completa", true);
  });

  test("muestra el aviso de IA antes de cualquier interacción (A-02, A-25)", async ({ page }) => {
    await page.goto("/");
    const notice = page.locator(".notice");
    await expect(notice).toBeVisible();
    await expect(notice).toContainText("inteligencia artificial, no con una persona");
    await expect(notice).toContainText("el audio no se guarda");
    await expect(page.locator(".site-header .brand")).toContainText("Asistente de IA");
    await expect(page.locator(".site-header .brand")).toContainText("corte 5-nov-2022");
  });

  test("muestra las cifras del brief: 41.427 filas, 9.320 = 8.308 + 998 + 14, 10.921 sedes (A-02, A-05)", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-brief="rows"]')).toHaveText("41.427");
    await expect(page.locator('[data-brief="providers"]')).toHaveText("9.320");
    await expect(page.locator('[data-brief="site_codes"]')).toHaveText("10.921");
    const legend = page.locator(".legend li");
    await expect(legend).toHaveCount(3);
    await expect(legend.nth(0)).toContainText("Privada");
    await expect(legend.nth(0)).toContainText("8.308");
    await expect(legend.nth(1)).toContainText("998");
    await expect(legend.nth(2)).toContainText("14");
    // The row count is described as rows, never as providers.
    await expect(page.locator(".grain")).toContainText(/41\.427\s+filas/);
  });

  test("declara fuente, licencia y corte, y que es una muestra grabada cuando no hay backend (NF-08)", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".source")).toContainText("MinSalud — REPS");
    await expect(page.locator(".source")).toContainText("CC BY-SA 4.0");
    await expect(page.locator(".source")).toContainText("2022-11-05");
    await expect(page.locator("#brief-origin")).toContainText("Muestra grabada");
    const footer = page.locator(".site-footer");
    await expect(footer).toContainText("Ministerio de Salud y Protección Social — REPS");
    await expect(footer).toContainText("CC BY-SA 4.0");
    await expect(footer).toContainText("corte 2022-11-05");
    await expect(page.locator(".limits li").first()).toContainText("no disponibilidad");
  });

  test("ofrece entre 3 y 5 preguntas sugeridas que llevan a la consola (A-02)", async ({ page }) => {
    await page.goto("/");
    const questions = page.locator(".questions a");
    const count = await questions.count();
    expect(count).toBeGreaterThanOrEqual(3);
    expect(count).toBeLessThanOrEqual(5);
    for (const a of await questions.all()) {
      await expect(a).toBeVisible();
      expect(await a.getAttribute("href")).toMatch(/^\/consola\?q=/);
    }
  });

  test("estructura accesible: idioma, un h1, landmarks y enlace de salto (NF-06)", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("lang", "es-CO");
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.getByRole("main")).toHaveCount(1);
    await expect(page.getByRole("banner")).toHaveCount(1);
    await expect(page.getByRole("contentinfo")).toHaveCount(1);
    await expect(page.getByRole("navigation", { name: "Secciones de la consola" })).toBeVisible();
    await page.keyboard.press("Tab");
    const skip = page.locator("a.skip");
    await expect(skip).toBeFocused();
    await expect(skip).toBeInViewport();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/#contenido$/);
  });

  test("no usa emojis como iconos", async ({ page }) => {
    await page.goto("/");
    const html = await page.locator("body").innerHTML();
    expect(html.match(PICTOGRAPH) ?? []).toEqual([]);
    expect(await page.locator("svg.lucide").count()).toBeGreaterThan(5);
  });

  test("a 390 px no hay desborde horizontal y la llamada a la acción se ve", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await shot(page, "portada-390", true);
    expect(await overflowX(page)).toBe(0);
    await expect(page.getByRole("link", { name: "Iniciar conversación" })).toBeVisible();
    await expect(page.locator(".notice")).toBeVisible();
  });
});

test.describe("navegación con View Transitions", () => {
  test("ir de la portada a la consola no recarga el documento", async ({ page, problems }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.evaluate(() => {
      (window as unknown as { __sameDocument: boolean }).__sameDocument = true;
    });
    await page.getByRole("link", { name: "Ver la consola primero" }).click();
    await expect(page).toHaveURL(/\/consola$/);
    await expect(page.locator("#btn-toggle")).toBeVisible();
    expect(await page.evaluate(() => (window as unknown as { __sameDocument?: boolean }).__sameDocument)).toBe(true);
    await expect(page).toHaveTitle(/Consola/);
    // The console must be wired after a client-side navigation, not only on a full load.
    await page.locator("#btn-direct").click();
    await expect(page.locator("#btn-direct")).toHaveAttribute("aria-pressed", "true");
    expect(problems.pageErrors).toEqual([]);
    expect(problems.consoleErrors).toEqual([]);
  });

  test("«Iniciar conversación» abre la consola e inicia la sesión; el parámetro se consume", async ({ page, problems }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.getByRole("link", { name: "Iniciar conversación" }).click();
    await expect(page).toHaveURL(/\/consola$/);
    await expect(page.locator("#btn-toggle")).toHaveAttribute("data-running", "true");
    const first = page.locator("#msgs .msg.from-agent .text").first();
    await expect(first).toContainText("Soy un asistente de inteligencia artificial");
    expect(problems.pageErrors).toEqual([]);
  });

  test("una pregunta sugerida abre la consola, se envía y se responde con evidencia", async ({ page, problems }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator(".questions a", { hasText: "¿Cuántas camas hay en total?" }).click();
    await expect(page).toHaveURL(/\/consola$/);
    await expect(page.locator("#msgs .msg.from-user .text")).toHaveText("¿Cuántas camas hay en total?", { timeout: 30_000 });
    await expect(page.locator("#msgs .msg.from-agent .text").last()).toContainText("97.036", { timeout: 30_000 });
    await expect(page.locator("#msgs details.evidence")).toHaveCount(1);
    expect(problems.pageErrors).toEqual([]);
    expect(problems.consoleErrors).toEqual([]);
  });

  test("el estado de la conversación sobrevive a salir a la portada y volver", async ({ page, problems }) => {
    await page.goto("/consola");
    await page.locator("#ask-input").fill("¿Cuántas IPS hay en Bogotá?");
    await page.locator("#ask-input").press("Enter");
    await expect(page.locator("#msgs .msg.from-agent .text").last()).toContainText("1.270", { timeout: 40_000 });
    await expect(page.locator("#msgs .msg .typing")).toHaveCount(0);
    const before = await page.locator("#msgs > li").count();
    await page.evaluate(() => {
      (window as unknown as { __sameDocument: boolean }).__sameDocument = true;
    });

    await page.locator(".site-header .brand").click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator("h1")).toContainText("Pregúntale en voz alta");
    // The live status follows the session onto the cover page.
    await expect(page.locator("html")).toHaveAttribute("data-status", "listening");

    await page.locator('.site-header nav a[data-tab-link="conversacion"]').click();
    await expect(page).toHaveURL(/\/consola/);
    expect(await page.evaluate(() => (window as unknown as { __sameDocument?: boolean }).__sameDocument)).toBe(true);
    await expect(page.locator("#msgs > li")).toHaveCount(before);
    await expect(page.locator("#msgs .msg.from-agent .text").last()).toContainText("1.270");
    await expect(page.locator("#btn-toggle")).toHaveAttribute("data-running", "true");
    await expect(page.locator("#state-badge")).toHaveText("Te escucho");

    // And the session is still usable.
    await page.locator("#ask-input").fill("¿Cuántas camas hay en total?");
    await page.locator("#ask-input").press("Enter");
    await expect(page.locator("#msgs .msg.from-agent .text").last()).toContainText("97.036", { timeout: 30_000 });
    expect(problems.pageErrors).toEqual([]);
    expect(problems.consoleErrors).toEqual([]);
  });

  test("un enlace de la cabecera a una pestaña abre esa pestaña al llegar desde la portada", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator('.site-header nav a[data-tab-link="api"]').click();
    await expect(page).toHaveURL(/\/consola#api$/);
    await expect(page.locator("#pane-api")).toBeVisible();
    await expect(page.locator("#tab-api")).toHaveAttribute("aria-selected", "true");
    await expect(page.locator('.site-header nav a[data-tab-link="api"]')).toHaveAttribute("aria-current", "page");
  });
});
