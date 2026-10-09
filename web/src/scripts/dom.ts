/**
 * Small DOM helpers shared by the console panels.
 *
 * Panels are plain Astro components with a `<script>`. Because the client router
 * swaps the document without reloading modules, each panel is set up on
 * `astro:page-load` and torn down on `astro:before-swap`.
 */
import { getState, subscribe, type ConsoleState, type Slice } from "../voice/store";

/** Runs `setup` every time a page containing `#id` is shown; its return value is the cleanup. */
export function panel(id: string, setup: (root: HTMLElement) => (() => void) | void): void {
  document.addEventListener("astro:page-load", () => {
    const root = document.getElementById(id);
    if (!root) return;
    const cleanup = setup(root);
    if (cleanup) document.addEventListener("astro:before-swap", cleanup, { once: true });
  });
}

/** Renders now and whenever one of `slices` changes. Returns the unsubscribe function. */
export function bind(slices: Slice[], render: (state: ConsoleState) => void): () => void {
  render(getState());
  return subscribe((state, changed) => {
    if (changed.has("reset") || slices.some((s) => changed.has(s))) render(state);
  });
}

const ESCAPES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };

/** Escapes text for use inside innerHTML. Everything from the source or the model goes through this. */
export function esc(value: unknown): string {
  return String(value ?? "").replace(/[&<>"]/g, (ch) => ESCAPES[ch] ?? ch);
}

/** `mm:ss.mmm` on the session clock (docs/08 §8). */
export function clock(ms: number): string {
  const total = Math.max(0, Math.round(ms));
  const m = Math.floor(total / 60000);
  const s = Math.floor((total % 60000) / 1000);
  const rest = total % 1000;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(rest).padStart(3, "0")}`;
}

const nf = new Intl.NumberFormat("es-CO");
export const num = (n: number): string => nf.format(n);

/** Milliseconds as a short duration: `538 ms` or `1,84 s`. */
export function dur(ms: number | null): string {
  if (ms === null) return "—";
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2).replace(".", ",")} s`;
}

/** Markup of a Lucide icon pre-rendered by IconBank.astro. */
export function icon(name: string): string {
  const tpl = document.getElementById(`icon-${name}`);
  return tpl instanceof HTMLTemplateElement ? tpl.innerHTML : "";
}

const rendered = new WeakMap<HTMLElement, string>();

export interface KeyedItem {
  key: string;
  cls: string;
  html: string;
}

/**
 * Keyed list update: only items whose markup changed are touched. A full
 * innerHTML swap on every partial would close open <details> and swallow
 * clicks on buttons inside older messages.
 */
export function reconcile(list: HTMLElement, items: KeyedItem[], tag = "li"): void {
  const existing = new Map<string, HTMLElement>();
  for (const child of Array.from(list.children) as HTMLElement[]) {
    const key = child.dataset.key;
    if (key !== undefined) existing.set(key, child);
    else child.remove();
  }
  let cursor: Element | null = list.firstElementChild;
  for (const item of items) {
    let el = existing.get(item.key);
    if (el) existing.delete(item.key);
    else {
      el = document.createElement(tag);
      el.dataset.key = item.key;
    }
    if (el.className !== item.cls) el.className = item.cls;
    if (rendered.get(el) !== item.html) {
      rendered.set(el, item.html);
      // Callers build `html` with esc() around every dynamic value.
      el.innerHTML = item.html;
    }
    if (el !== cursor) list.insertBefore(el, cursor);
    else cursor = cursor.nextElementSibling;
  }
  for (const stale of existing.values()) stale.remove();
}

export function byId<T extends HTMLElement = HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}
