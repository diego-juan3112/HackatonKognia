/**
 * Responsive matrix: 390 px (phone), 820 px (tablet) and 1366 px (desktop).
 * Layout-agnostic on purpose (no texts, no class names), so it survives a redesign:
 * it only checks that pages load clean, do not overflow sideways and keep their
 * interactive controls inside the viewport width.
 */
import { expect, overflowX, shot, test } from "./fixtures";

const VIEWPORTS = [
  { name: "movil-390", width: 390, height: 844 },
  { name: "tableta-820", width: 820, height: 1180 },
  { name: "pc-1366", width: 1366, height: 768 },
];

for (const vp of VIEWPORTS) {
  for (const path of ["/", "/consola"]) {
    test(`${vp.name} ${path}: carga sin errores, sin desborde horizontal y con los controles dentro del ancho`, async ({ page, problems }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await shot(page, `responsive-${vp.name}${path === "/" ? "-portada" : "-consola"}`, true);
      expect(problems.pageErrors).toEqual([]);
      expect(await overflowX(page)).toBe(0);
      const outside = await page.evaluate(() =>
        Array.from(document.querySelectorAll<HTMLElement>("button, a[href], input, select, [role=tab], [role=switch]"))
          .filter((el) => {
            const r = el.getBoundingClientRect();
            const visible = r.width > 1 && r.height > 1 && getComputedStyle(el).visibility !== "hidden";
            return visible && (r.left < -1 || r.right > innerWidth + 1);
          })
          .map((el) => el.id || el.getAttribute("aria-label") || el.textContent?.trim().slice(0, 30) || el.tagName),
      );
      expect(outside).toEqual([]);
      await expect(page.getByRole("main")).toBeVisible();
    });
  }
}
