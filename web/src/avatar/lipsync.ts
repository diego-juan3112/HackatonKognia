/**
 * Audio-driven lip-sync for VRM mouth expressions.
 *
 * Three sources, in priority order:
 *   1. An `AnalyserNode` (spectrum + volume) when it carries signal.
 *   2. A plain 0..1 level pushed by the caller (`setLevel`).
 *   3. An internal synthetic "speech" pattern (demo mode), to preview the mouth
 *      without a microphone or a voice provider.
 *
 * The output is a set of smoothed weights for the five VRM vowel presets. With
 * no audio every weight decays to zero, so the mouth closes on its own.
 */

export const VISEMES = ["aa", "ih", "ou", "ee", "oh"] as const;
export type Viseme = (typeof VISEMES)[number];
export type VisemeWeights = Record<Viseme, number>;

/** A pushed level older than this is considered stale and decays to silence. */
const LEVEL_TTL_MS = 220;
/** Volume below this is treated as silence (analyser noise floor). */
const NOISE_GATE = 0.035;
/** Response speeds (1/s) for the mouth opening and closing. */
const ATTACK = 30;
const RELEASE = 16;
/** Upper bound for the sum of all vowel weights; above it the mesh distorts. */
const MAX_TOTAL = 1;

const clamp01 = (v: number): number => (v < 0 ? 0 : v > 1 ? 1 : v);

function emptyWeights(): VisemeWeights {
  return { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 };
}

export class LipSync {
  /** Smoothed weights, ready to be written to the expression manager. */
  readonly weights: VisemeWeights = emptyWeights();
  /** Overall mouth openness (0..1), used by the body animation for emphasis. */
  openness = 0;
  demo = false;

  private readonly target: VisemeWeights = emptyWeights();
  private analyser: AnalyserNode | null = null;
  private timeData: Uint8Array<ArrayBuffer> = new Uint8Array(0);
  private freqData: Uint8Array<ArrayBuffer> = new Uint8Array(0);
  private level = 0;
  private levelStamp = -Infinity;
  private clock = 0;

  attachAnalyser(node: AnalyserNode | null): void {
    this.analyser = node;
    if (node) {
      this.timeData = new Uint8Array(node.fftSize);
      this.freqData = new Uint8Array(node.frequencyBinCount);
    }
  }

  setLevel(level: number, nowMs: number): void {
    this.level = Number.isFinite(level) ? clamp01(level) : 0;
    this.levelStamp = nowMs;
  }

  update(dt: number, nowMs: number): void {
    this.clock += dt;
    const target = this.target;
    for (const v of VISEMES) target[v] = 0;

    const fromAnalyser = this.readAnalyser(target);
    if (!fromAnalyser) {
      let level = nowMs - this.levelStamp < LEVEL_TTL_MS ? this.level : 0;
      if (this.demo) level = Math.max(level, this.demoLevel());
      if (level > 0.01) this.shapeFromLevel(level, target);
    }

    let total = 0;
    for (const v of VISEMES) total += target[v];
    const norm = total > MAX_TOTAL ? MAX_TOTAL / total : 1;

    let open = 0;
    for (const v of VISEMES) {
      const goal = target[v] * norm;
      const current = this.weights[v];
      const speed = goal > current ? ATTACK : RELEASE;
      const next = current + (goal - current) * (1 - Math.exp(-speed * dt));
      this.weights[v] = next < 0.002 ? 0 : next;
      open += this.weights[v];
    }
    this.openness = clamp01(open);
  }

  /** Fills `out` from the analyser. Returns false when there is no signal. */
  private readAnalyser(out: VisemeWeights): boolean {
    const node = this.analyser;
    if (!node) return false;

    node.getByteTimeDomainData(this.timeData);
    let sum = 0;
    for (let i = 0; i < this.timeData.length; i++) {
      const s = ((this.timeData[i] ?? 128) - 128) / 128;
      sum += s * s;
    }
    const rms = Math.sqrt(sum / Math.max(1, this.timeData.length));
    if (rms < NOISE_GATE) return false;
    // Speech RMS rarely exceeds ~0.3; map it to a perceptual 0..1 opening.
    const volume = clamp01(Math.pow((rms - NOISE_GATE) * 4.2, 0.7));

    node.getByteFrequencyData(this.freqData);
    const hzPerBin = node.context.sampleRate / node.fftSize;
    const low = this.band(180, 600, hzPerBin); // first formant of closed vowels (u, o)
    const mid = this.band(600, 1500, hzPerBin); // open vowels (a)
    const high = this.band(1700, 3600, hzPerBin); // second formant of front vowels (e, i)
    const all = low + mid + high;
    if (all < 1e-4) {
      out.aa = volume;
      return true;
    }
    const l = low / all;
    const m = mid / all;
    const h = high / all;

    out.aa = volume * clamp01(m * 1.9 + 0.08);
    out.oh = volume * clamp01(l * 1.3 - h * 0.6);
    out.ou = volume * clamp01(l * 1.1 - m * 0.9);
    out.ee = volume * clamp01(h * 2.8 - l * 0.4);
    out.ih = volume * clamp01(h * 1.3);
    return true;
  }

  /** Mean normalised magnitude of the spectrum between two frequencies. */
  private band(fromHz: number, toHz: number, hzPerBin: number): number {
    const start = Math.max(1, Math.floor(fromHz / hzPerBin));
    const end = Math.min(this.freqData.length - 1, Math.ceil(toHz / hzPerBin));
    if (end <= start) return 0;
    let sum = 0;
    for (let i = start; i <= end; i++) sum += this.freqData[i] ?? 0;
    return sum / ((end - start + 1) * 255);
  }

  /**
   * With only a volume there is no vowel information, so the shape drifts
   * between vowels on slow incommensurate waves: it reads as articulation
   * instead of a jaw flapping open and shut.
   */
  private shapeFromLevel(level: number, out: VisemeWeights): void {
    const t = this.clock;
    const a = 0.5 + 0.5 * Math.sin(t * 6.1);
    const b = 0.5 + 0.5 * Math.sin(t * 4.3 + 1.7);
    const c = 0.5 + 0.5 * Math.sin(t * 7.9 + 0.6);
    out.aa = level * (0.45 + 0.4 * a);
    out.oh = level * 0.38 * b * (1 - a * 0.5);
    out.ee = level * 0.34 * c * (1 - b * 0.6);
    out.ih = level * 0.2 * (1 - c);
    out.ou = level * 0.24 * (1 - a) * b;
  }

  /** Synthetic syllable envelope with phrase-level pauses. */
  private demoLevel(): number {
    const t = this.clock;
    const phrase = Math.sin(t * 1.7) > -0.8 ? 1 : 0; // short breaks between phrases
    const syllable = Math.pow(Math.abs(Math.sin(t * 8.4)), 0.8);
    const stress = 0.6 + 0.4 * Math.sin(t * 2.1 + 0.4);
    return phrase * syllable * stress * 0.95;
  }
}
