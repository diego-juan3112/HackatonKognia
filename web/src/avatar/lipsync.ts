/**
 * Audio-driven lip-sync for VRM mouth expressions.
 *
 * Three sources, in priority order:
 *   1. An `AnalyserNode` (spectrum + volume) when it carries signal. The gain
 *      adapts to the loudness of the voice and the vowel is picked from which
 *      band of the spectrum stands out (low -> ou/oh, mid -> aa, high -> ee/ih).
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
/** RMS below this is treated as silence (analyser noise floor). */
const NOISE_GATE = 0.012;
/**
 * Adaptive gain: the loudest recent RMS is tracked and mapped to a fully open
 * mouth, so a quiet synthetic voice opens the mouth as much as a loud one.
 * The floor stops near-silent noise from being amplified into speech.
 */
const PEAK_FLOOR = 0.045;
const PEAK_INITIAL = 0.08;
/** Seconds for the tracked peak to halve once the voice gets quieter. */
const PEAK_HALF_LIFE = 3;
/** Speed (1/s) of the per-band running mean used to whiten the spectrum. */
const BAND_ADAPT = 0.9;
/** Exponent that sharpens the vowel scores so one shape leads at a time. */
const VOWEL_SHARPNESS = 2.2;
/** Response speeds (1/s) for the mouth opening and closing. */
const ATTACK = 38;
const RELEASE = 13;
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
  private peak = PEAK_INITIAL;
  private readonly bandMean = { low: 0, mid: 0, high: 0 };
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

    const fromAnalyser = this.readAnalyser(target, dt);
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
    // While one vowel fades and the next rises the sum can overshoot.
    if (open > MAX_TOTAL) {
      for (const v of VISEMES) this.weights[v] *= MAX_TOTAL / open;
    }
    this.openness = clamp01(open);
  }

  /** Fills `out` from the analyser. Returns false when there is no signal. */
  private readAnalyser(out: VisemeWeights, dt: number): boolean {
    const node = this.analyser;
    if (!node) return false;

    node.getByteTimeDomainData(this.timeData);
    let sum = 0;
    for (let i = 0; i < this.timeData.length; i++) {
      const s = ((this.timeData[i] ?? 128) - 128) / 128;
      sum += s * s;
    }
    const rms = Math.sqrt(sum / Math.max(1, this.timeData.length));

    // Peak follower: jumps up at once, falls slowly.
    this.peak = Math.max(PEAK_FLOOR, rms, this.peak * Math.pow(0.5, dt / PEAK_HALF_LIFE));
    if (rms < NOISE_GATE) return false;
    // A syllable at ~80 % of the recent peak already opens the mouth fully.
    const span = Math.max(1e-4, this.peak * 0.8 - NOISE_GATE);
    const volume = clamp01(Math.pow((rms - NOISE_GATE) / span, 0.75));
    if (volume < 0.02) return false;

    node.getByteFrequencyData(this.freqData);
    const hzPerBin = node.context.sampleRate / node.fftSize;
    const low = this.band(150, 550, hzPerBin); // first formant of closed vowels (u, o)
    const mid = this.band(600, 1400, hzPerBin); // first formant of open vowels (a)
    const high = this.band(1700, 3600, hzPerBin); // second formant of front vowels (e, i)
    if (low + mid + high < 1e-5) {
      out.aa = volume;
      return true;
    }

    // Speech always carries more energy in the low band, so raw ratios would
    // pick the same vowel forever. Each band is compared with its own running
    // mean instead: what matters is which band stands out right now.
    const mean = this.bandMean;
    if (mean.low + mean.mid + mean.high === 0) {
      mean.low = low;
      mean.mid = mid;
      mean.high = high;
    } else {
      const k = 1 - Math.exp(-BAND_ADAPT * dt);
      mean.low += (low - mean.low) * k;
      mean.mid += (mid - mean.mid) * k;
      mean.high += (high - mean.high) * k;
    }
    const l = low / Math.max(1e-5, mean.low);
    const m = mid / Math.max(1e-5, mean.mid);
    const h = high / Math.max(1e-5, mean.high);

    const score: VisemeWeights = {
      aa: Math.max(0, m * 1.2 - 0.15 * h),
      oh: Math.max(0, 0.65 * l + 0.45 * m - 0.55 * h),
      ou: Math.max(0, 1.1 * l - 0.6 * m - 0.3 * h),
      ee: Math.max(0, 0.7 * h + 0.5 * m - 0.5 * l),
      ih: Math.max(0, 0.85 * h - 0.6 * m - 0.3 * l),
    };
    let total = 0;
    for (const v of VISEMES) {
      score[v] = Math.pow(score[v], VOWEL_SHARPNESS);
      total += score[v];
    }
    if (total < 1e-6) {
      out.aa = volume;
      return true;
    }
    for (const v of VISEMES) out[v] = (volume * score[v]) / total;
    return true;
  }

  /** Mean normalised magnitude of the spectrum between two frequencies. */
  private band(fromHz: number, toHz: number, hzPerBin: number): number {
    const start = Math.max(1, Math.floor(fromHz / hzPerBin));
    const end = Math.min(this.freqData.length - 1, Math.ceil(toHz / hzPerBin));
    if (end <= start) return 0;
    let sum = 0;
    // The analyser reports decibels; squaring expands them back towards energy
    // so the formant peaks are not flattened.
    for (let i = start; i <= end; i++) {
      const v = (this.freqData[i] ?? 0) / 255;
      sum += v * v;
    }
    return sum / (end - start + 1);
  }

  /**
   * With only a volume there is no vowel information, so the shape drifts
   * between vowels on slow incommensurate waves: it reads as articulation
   * instead of a jaw flapping open and shut.
   */
  private shapeFromLevel(level: number, out: VisemeWeights): void {
    // Five slow waves, one per vowel; sharpening lets a different one lead
    // every few syllables. `aa` gets a head start: it is the most readable.
    const t = this.clock;
    const score: VisemeWeights = {
      aa: 0.62 + 0.5 * Math.sin(t * 5.3),
      oh: 0.5 + 0.5 * Math.sin(t * 4.1 + 1.7),
      ee: 0.5 + 0.5 * Math.sin(t * 6.7 + 0.6),
      ih: 0.42 + 0.5 * Math.sin(t * 3.7 + 3.9),
      ou: 0.42 + 0.5 * Math.sin(t * 4.7 + 2.8),
    };
    let total = 0;
    for (const v of VISEMES) {
      score[v] = Math.pow(Math.max(0, score[v]), VOWEL_SHARPNESS);
      total += score[v];
    }
    if (total < 1e-6) {
      out.aa = level;
      return;
    }
    for (const v of VISEMES) out[v] = (level * score[v]) / total;
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
