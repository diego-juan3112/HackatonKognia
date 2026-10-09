/**
 * The orb: a canvas visualiser of the engine status.
 *
 * A ring of radial bars around a glowing core. Colour and motion change with the
 * status; every transcript event adds a small pulse, so it visibly reacts to
 * speech. With prefers-reduced-motion it draws one still frame per status.
 */
import { getState, subscribe } from "../voice/store";
import type { EngineStatus } from "../voice/types";

type RGB = [number, number, number];

interface Mood {
  a: RGB;
  b: RGB;
  /** Bar energy 0..1. */
  energy: number;
  /** Rotation speed of the pattern, radians per second. */
  spin: number;
  /** 0 = even ring, 1 = a comet sweeping around (waiting states). */
  sweep: number;
  /** How jittery the bars are. */
  jitter: number;
}

const BLUE: RGB = [37, 99, 235];
const SKY: RGB = [14, 165, 233];
const GREEN: RGB = [22, 163, 74];
const TEAL: RGB = [20, 184, 166];
const AMBER: RGB = [245, 158, 11];
const ORANGE: RGB = [249, 115, 22];
const VIOLET: RGB = [124, 92, 245];
const RED: RGB = [229, 72, 77];

const MOODS: Record<EngineStatus, Mood> = {
  idle: { a: VIOLET, b: SKY, energy: 0.1, spin: 0.12, sweep: 0, jitter: 0 },
  connecting: { a: SKY, b: BLUE, energy: 0.3, spin: 2.4, sweep: 1, jitter: 0 },
  listening: { a: GREEN, b: TEAL, energy: 0.34, spin: 0.3, sweep: 0, jitter: 0.9 },
  thinking: { a: AMBER, b: ORANGE, energy: 0.36, spin: 3.2, sweep: 1, jitter: 0.1 },
  speaking: { a: BLUE, b: VIOLET, energy: 0.85, spin: 0.5, sweep: 0, jitter: 0.35 },
  renewing: { a: VIOLET, b: TEAL, energy: 0.3, spin: -2.6, sweep: 1, jitter: 0 },
  error: { a: RED, b: ORANGE, energy: 0.04, spin: 0, sweep: 0, jitter: 0 },
};

const BARS = 72;
const lerp = (x: number, y: number, k: number): number => x + (y - x) * k;
const mix = (x: RGB, y: RGB, k: number): RGB => [lerp(x[0], y[0], k), lerp(x[1], y[1], k), lerp(x[2], y[2], k)];
const rgba = (c: RGB, alpha: number): string => `rgb(${c[0] | 0} ${c[1] | 0} ${c[2] | 0} / ${alpha})`;

export function mountOrb(): void {
  const host = document.getElementById("orb");
  if (!host || host.dataset.ready === "1") return;
  const canvas = host.querySelector("canvas");
  const ctx = canvas?.getContext("2d");
  if (!canvas || !ctx) return;
  host.dataset.ready = "1";

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const current: Mood = { ...MOODS[getState().status] };
  let target: Mood = MOODS[getState().status];
  let pulse = 0;
  let phase = 0;
  let last = performance.now();
  let frame = 0;
  let size = 0;
  const seeds = Array.from({ length: BARS }, (_, i) => Math.sin(i * 12.9898) * 43758.5453 - Math.floor(Math.sin(i * 12.9898) * 43758.5453));

  function resize(): void {
    const rect = host!.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    size = Math.max(40, Math.min(rect.width, rect.height));
    canvas!.width = Math.round(size * dpr);
    canvas!.height = Math.round(size * dpr);
    ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (reduced.matches) draw(0);
  }

  function draw(dt: number): void {
    const k = reduced.matches ? 1 : Math.min(1, dt * 5);
    current.a = mix(current.a, target.a, k);
    current.b = mix(current.b, target.b, k);
    current.energy = lerp(current.energy, target.energy, k);
    current.sweep = lerp(current.sweep, target.sweep, k);
    current.jitter = lerp(current.jitter, target.jitter, k);
    current.spin = lerp(current.spin, target.spin, k);
    phase += current.spin * dt;
    pulse = Math.max(0, pulse - dt * 2.4);
    const time = performance.now() / 1000;

    const c = size / 2;
    ctx!.clearRect(0, 0, size, size);

    // Halo
    const halo = ctx!.createRadialGradient(c, c, size * 0.08, c, c, size * 0.5);
    halo.addColorStop(0, rgba(current.a, 0.28));
    halo.addColorStop(0.55, rgba(current.b, 0.1));
    halo.addColorStop(1, rgba(current.b, 0));
    ctx!.fillStyle = halo;
    ctx!.fillRect(0, 0, size, size);

    // Core: two offset lobes give it a liquid, non-circular feel
    const breathe = 1 + 0.035 * Math.sin(time * 1.3) + pulse * 0.05;
    const coreR = size * 0.19 * breathe;
    for (let i = 0; i < 2; i++) {
      const ang = time * (0.5 + i * 0.3) + i * Math.PI;
      const ox = Math.cos(ang) * coreR * 0.2;
      const oy = Math.sin(ang) * coreR * 0.2;
      const g = ctx!.createRadialGradient(c + ox - coreR * 0.3, c + oy - coreR * 0.35, coreR * 0.05, c + ox, c + oy, coreR * 1.15);
      const from = i === 0 ? current.a : current.b;
      const to = i === 0 ? current.b : current.a;
      g.addColorStop(0, rgba(mix(from, [255, 255, 255], 0.55), 0.95));
      g.addColorStop(0.45, rgba(from, 0.82));
      g.addColorStop(1, rgba(to, 0));
      ctx!.fillStyle = g;
      ctx!.beginPath();
      ctx!.arc(c + ox, c + oy, coreR * 1.15, 0, Math.PI * 2);
      ctx!.fill();
    }

    // Ring of bars
    const inner = size * 0.285;
    const maxLen = size * 0.17;
    ctx!.lineCap = "round";
    ctx!.lineWidth = Math.max(1.5, size * 0.011);
    for (let i = 0; i < BARS; i++) {
      const theta = (i / BARS) * Math.PI * 2 - Math.PI / 2;
      const wave =
        0.5 +
        0.28 * Math.sin(theta * 3 + time * 2.6) +
        0.22 * Math.sin(theta * 7 - time * 4.1) +
        current.jitter * 0.35 * Math.sin(time * (9 + (seeds[i] ?? 0) * 14) + i);
      let level = Math.max(0.04, wave) * (current.energy + pulse * 0.3);
      let alpha = 0.9;
      if (current.sweep > 0.01) {
        // Comet: brightness falls off behind a rotating head
        const d = (((theta - phase) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
        const tail = Math.max(0, 1 - d / (Math.PI * 1.25));
        level = lerp(level, 0.1 + tail * 0.5, current.sweep);
        alpha = lerp(alpha, 0.16 + tail * 0.84, current.sweep);
      }
      const len = size * 0.012 + level * maxLen;
      const cos = Math.cos(theta);
      const sin = Math.sin(theta);
      const tone = 0.5 + 0.5 * Math.sin(theta * 2 + phase * 0.6);
      ctx!.strokeStyle = rgba(mix(current.a, current.b, tone), alpha);
      ctx!.beginPath();
      ctx!.moveTo(c + cos * inner, c + sin * inner);
      ctx!.lineTo(c + cos * (inner + len), c + sin * (inner + len));
      ctx!.stroke();
    }
  }

  function loop(t: number): void {
    const dt = Math.min(0.05, (t - last) / 1000);
    last = t;
    draw(dt);
    frame = requestAnimationFrame(loop);
  }

  function run(): void {
    cancelAnimationFrame(frame);
    if (reduced.matches) draw(0);
    else {
      last = performance.now();
      frame = requestAnimationFrame(loop);
    }
  }

  subscribe((state, slices) => {
    target = MOODS[state.status];
    if (slices.has("transcript")) pulse = 1;
    if (reduced.matches) draw(0);
  });

  new ResizeObserver(resize).observe(host);
  reduced.addEventListener("change", run);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) cancelAnimationFrame(frame);
    else run();
  });
  resize();
  run();
}
