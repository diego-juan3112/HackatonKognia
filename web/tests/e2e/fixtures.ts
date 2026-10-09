/**
 * Shared fixtures: every page records console errors, uncaught exceptions,
 * failed requests and microphone requests, so each test can assert on them.
 */
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test as base, expect, type Page } from "@playwright/test";

export const ARTIFACTS = fileURLToPath(new URL("../artifacts/", import.meta.url));
mkdirSync(ARTIFACTS, { recursive: true });

export interface Problems {
  consoleErrors: string[];
  pageErrors: string[];
  failedRequests: string[];
}

/** Starts recording problems on a page. Call before the first navigation. */
export function watch(page: Page): Problems {
  const problems: Problems = { consoleErrors: [], pageErrors: [], failedRequests: [] };
  page.on("console", (msg) => {
    if (msg.type() === "error") problems.consoleErrors.push(`${msg.text()} @ ${msg.location().url}`);
  });
  page.on("pageerror", (err) => problems.pageErrors.push(String(err)));
  page.on("response", (res) => {
    if (res.status() >= 400) problems.failedRequests.push(`${res.status()} ${res.url()}`);
  });
  page.on("requestfailed", (req) => problems.failedRequests.push(`FAILED ${req.url()} ${req.failure()?.errorText ?? ""}`));
  return problems;
}

/** Counts getUserMedia calls without granting or denying anything. */
export async function countMicRequests(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const w = window as unknown as { __micRequests: number };
    w.__micRequests = 0;
    const md = navigator.mediaDevices;
    if (!md?.getUserMedia) return;
    const original = md.getUserMedia.bind(md);
    md.getUserMedia = (constraints) => {
      w.__micRequests++;
      return original(constraints);
    };
  });
}

export const micRequests = (page: Page): Promise<number> =>
  page.evaluate(() => (window as unknown as { __micRequests: number }).__micRequests);

export const shot = (page: Page, name: string, fullPage = false): Promise<Buffer> =>
  page.screenshot({ path: `${ARTIFACTS}${name}.png`, fullPage, animations: "disabled" });

/** Emoji and pictographs: icons must be Lucide SVGs, never characters. */
export const PICTOGRAPH = /\p{Extended_Pictographic}/gu;

/** Horizontal overflow of the document, in px (0 when the page fits). */
export const overflowX = (page: Page): Promise<number> =>
  page.evaluate(() => Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth));

export interface Contrast {
  ratio: number;
  fg: string;
  bg: string;
  px: number;
}

/**
 * WCAG contrast ratio between the text colour of the first match of `selector`
 * and the nearest opaque background behind it.
 */
export function contrastOf(page: Page, selector: string): Promise<Contrast | null> {
  return page.evaluate((sel) => {
    const el = document.querySelector<HTMLElement>(sel);
    if (!el) return null;
    const ctx = document.createElement("canvas").getContext("2d", { willReadFrequently: true })!;
    type RGBA = [number, number, number, number];
    type RGB = [number, number, number];
    const rgba = (color: string): RGBA => {
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = "#000";
      ctx.fillStyle = color;
      ctx.fillRect(0, 0, 1, 1);
      const d = ctx.getImageData(0, 0, 1, 1).data;
      const a = d[3]! / 255;
      // getImageData is not premultiplied, but a transparent fill reads back as 0,0,0,0.
      return [d[0]!, d[1]!, d[2]!, a];
    };
    const over = (top: RGBA, under: RGB): RGB => [0, 1, 2].map((i) => top[i]! * top[3] + under[i]! * (1 - top[3])) as RGB;
    const layers: RGBA[] = [];
    let opacity = 1;
    for (let node: HTMLElement | null = el; node; node = node.parentElement) {
      const cs = getComputedStyle(node);
      opacity *= Number(cs.opacity);
      const bg = rgba(cs.backgroundColor);
      if (bg[3] > 0) layers.push(bg);
      if (bg[3] === 1) break;
    }
    let bg: RGB = [255, 255, 255];
    for (const layer of layers.reverse()) bg = over(layer, bg);
    const cs = getComputedStyle(el);
    const text = rgba(cs.color);
    const fg = over([text[0], text[1], text[2], text[3] * opacity], bg);
    const lum = (c: RGB): number => {
      const [r, g, b] = c.map((v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      }) as RGB;
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a) as [number, number];
    const fmt = (c: number[]): string => `rgb(${c.map((v) => Math.round(v)).join(",")})`;
    return { ratio: Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100, fg: fmt(fg), bg: fmt(bg), px: parseFloat(cs.fontSize) };
  }, selector);
}

export const test = base.extend<{ problems: Problems }>({
  problems: async ({ page }, use) => {
    await use(watch(page));
  },
});

export { expect };
