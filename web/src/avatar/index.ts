/**
 * Anime-style 3D avatar (VRM) for the voice console.
 *
 * Plain three.js + @pixiv/three-vrm, no UI framework. Everything the avatar
 * does is procedural (no animation clips): breathing, sway, blinking, gaze,
 * a greeting wave, per-state expressions and audio-driven lip-sync.
 *
 * Import it lazily so three.js stays out of the first paint:
 *
 *   const { mountAvatar } = await import("../avatar");
 *   const avatar = await mountAvatar(canvas, { onProgress });
 */
import {
  AmbientLight,
  DirectionalLight,
  MathUtils,
  Object3D,
  PerspectiveCamera,
  Scene,
  SRGBColorSpace,
  Vector3,
  WebGLRenderer,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils, type VRM, type VRMHumanBoneName } from "@pixiv/three-vrm";
import { LipSync, VISEMES } from "./lipsync";

export type AvatarState =
  | "idle"
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "renewing"
  | "error";

export interface AvatarDebugInfo {
  fps: number;
  frameMs: number;
  frames: number;
  triangles: number;
  drawCalls: number;
  state: AvatarState;
  mouth: Record<string, number>;
  expressions: string[];
  modelName: string;
  vrmVersion: string;
}

export interface AvatarHandle {
  setState(s: AvatarState): void;
  /** Mouth opening, 0..1. Must be pushed continuously; it decays on its own. */
  setMouthLevel(level: number): void;
  /** Drives the mouth from the spectrum of the audio being played. */
  attachAnalyser?(node: AnalyserNode): void;
  resetCamera(): void;
  dispose(): void;
  /** Extra: synthetic speech pattern to preview lip-sync without audio. */
  setDemoSpeech?(on: boolean): void;
  /** Extra: plays the greeting wave again. */
  wave?(): void;
  /** Extra: render statistics, for diagnostics. */
  getDebugInfo?(): AvatarDebugInfo;
}

export interface MountAvatarOptions {
  modelUrl?: string;
  onProgress?: (p: number) => void;
}

export type AvatarErrorCode = "webgl-unavailable" | "model-load-failed" | "invalid-model";

/** The single error type `mountAvatar` rejects with. */
export class AvatarError extends Error {
  readonly code: AvatarErrorCode;

  constructor(code: AvatarErrorCode, message: string, cause?: unknown) {
    super(message, cause === undefined ? undefined : { cause });
    this.name = "AvatarError";
    this.code = code;
  }
}

const DEFAULT_MODEL_FILE = "avatars/avatar-sample-a.vrm";
/** Size of the bundled model, used when the server sends no Content-Length. */
const DEFAULT_MODEL_BYTES = 15_096_320;

// --- Tuning -----------------------------------------------------------------

const CAMERA_FOV = 24;
/** Visible height of the bust framing, in metres. */
const FRAME_HEIGHT = 0.7;
/** Minimum visible width, so narrow canvases still show both shoulders. */
const FRAME_MIN_WIDTH = 0.56;
const ORBIT_YAW_LIMIT = 0.85;
const ORBIT_PITCH_LIMIT = 0.3;

/** Upper-arm roll (rad) that brings the T-pose arms down to the sides. */
const ARM_DOWN = 1.24;
const ELBOW_REST = 0.28;
const FINGER_CURL = 0.22;

const WAVE_IN = 0.55;
const WAVE_HOLD = 1.7;
const WAVE_OUT = 0.7;

interface Pose {
  pitch: number;
  yaw: number;
  roll: number;
  lean: number;
  gazeX: number;
  gazeY: number;
  /** How much the head and eyes follow the pointer, 0..1. */
  follow: number;
  expressions: Partial<Record<EmotionName, number>>;
}

const EMOTIONS = ["happy", "angry", "sad", "relaxed", "surprised"] as const;
type EmotionName = (typeof EMOTIONS)[number];

const POSES: Record<AvatarState, Pose> = {
  idle: { pitch: 0, yaw: 0, roll: 0, lean: 0, gazeX: 0, gazeY: 0, follow: 1, expressions: { happy: 0.14 } },
  connecting: { pitch: 0.03, yaw: 0, roll: 0.02, lean: 0, gazeX: 0, gazeY: 0, follow: 0.5, expressions: {} },
  // Attentive: leans in, tilts the head, eyes a touch wider.
  listening: {
    pitch: 0.035,
    yaw: 0,
    roll: 0.055,
    lean: 0.035,
    gazeX: 0,
    gazeY: 0,
    follow: 1,
    expressions: { surprised: 0.2, happy: 0.1 },
  },
  // Looks up and to the side with a slight frown.
  thinking: {
    pitch: -0.06,
    yaw: 0.16,
    roll: -0.05,
    lean: -0.01,
    gazeX: 0.75,
    gazeY: 0.42,
    follow: 0,
    expressions: { angry: 0.2 },
  },
  speaking: { pitch: 0, yaw: 0, roll: 0, lean: 0.01, gazeX: 0, gazeY: 0, follow: 1, expressions: { happy: 0.34 } },
  renewing: { pitch: 0.02, yaw: -0.07, roll: 0.03, lean: 0, gazeX: -0.3, gazeY: 0.1, follow: 0.3, expressions: {} },
  error: { pitch: 0.1, yaw: 0, roll: 0.045, lean: 0.02, gazeX: 0, gazeY: -0.28, follow: 0.35, expressions: { sad: 0.6 } },
};

const FINGERS = ["Index", "Middle", "Ring", "Little"] as const;
const PHALANGES = ["Proximal", "Intermediate", "Distal"] as const;

// --- Helpers ----------------------------------------------------------------

const damp = MathUtils.damp;
const clamp = MathUtils.clamp;
const smooth = (t: number): number => t * t * (3 - 2 * t);

function resolveModelUrl(explicit?: string): string {
  if (explicit) return explicit;
  const env = import.meta.env as Record<string, string | undefined> | undefined;
  const fromEnv = env?.PUBLIC_AVATAR_URL;
  if (fromEnv) return fromEnv;
  const base = env?.BASE_URL ?? "/";
  return `${base.endsWith("/") ? base : `${base}/`}${DEFAULT_MODEL_FILE}`;
}

function createRenderer(canvas: HTMLCanvasElement): WebGLRenderer {
  try {
    const renderer = new WebGLRenderer({
      canvas,
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.setClearColor(0x000000, 0);
    return renderer;
  } catch (cause) {
    throw new AvatarError(
      "webgl-unavailable",
      "WebGL is not available in this browser, so the 3D avatar cannot be rendered.",
      cause,
    );
  }
}

async function loadVrm(url: string, onProgress?: (p: number) => void): Promise<VRM> {
  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));
  let gltf;
  try {
    gltf = await loader.loadAsync(url, (event) => {
      const total = event.total > 0 ? event.total : DEFAULT_MODEL_BYTES;
      // Parsing still has to happen after the download, so stop short of 1.
      onProgress?.(clamp(event.loaded / total, 0, 1) * 0.92);
    });
  } catch (cause) {
    throw new AvatarError("model-load-failed", `The avatar model could not be loaded from "${url}".`, cause);
  }
  const vrm = gltf.userData.vrm as VRM | undefined;
  if (!vrm) {
    throw new AvatarError("invalid-model", `The file at "${url}" is not a VRM model.`);
  }
  return vrm;
}

// --- Avatar -----------------------------------------------------------------

class Avatar implements AvatarHandle {
  private readonly scene = new Scene();
  private readonly camera = new PerspectiveCamera(CAMERA_FOV, 1, 0.1, 20);
  private readonly lookTarget = new Object3D();
  private readonly lipSync = new LipSync();
  private lastFrame = 0;
  private readonly cleanups: Array<() => void> = [];
  private readonly bones = new Map<VRMHumanBoneName, Object3D>();
  /** Lower-cased name -> name as authored (some models ship "Surprised"). */
  private readonly expressionNames = new Map<string, string>();
  private readonly emotionWeights: Record<EmotionName, number> = {
    happy: 0,
    angry: 0,
    sad: 0,
    relaxed: 0,
    surprised: 0,
  };
  /** -1 for VRM 0.x, whose normalised bones are mirrored on X and Z. */
  private readonly axisSign: number;
  private readonly focus = new Vector3();
  private readonly eyeHeight: number;

  private state: AvatarState = "idle";
  private pose = { pitch: 0, yaw: 0, roll: 0, lean: 0, gazeX: 0, gazeY: 0, follow: 1 };
  private time = 0;
  private rafId = 0;
  private running = false;
  private disposed = false;
  private pageVisible = true;
  private onScreen = true;
  private contextLost = false;

  private reducedMotion = false;
  private motion = 1;

  private pointerX = 0;
  private pointerY = 0;
  private pointerStamp = -Infinity;
  private followX = 0;
  private followY = 0;

  private orbitYaw = 0;
  private orbitPitch = 0;
  private orbitYawGoal = 0;
  private orbitPitchGoal = 0;
  private cameraDistance = 1.6;
  private intro = 1;

  private blinkIn = 1.5;
  private blinkPhase = -1;
  private blinkAgain = false;
  private blinkValue = 0;

  private waving = false;
  private waveTime = 0;
  private waveWeight = 0;
  private emphasis = 0;

  private frames = 0;
  private frameMs = 16.7;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly renderer: WebGLRenderer,
    private readonly vrm: VRM,
  ) {
    this.axisSign = vrm.meta.metaVersion === "0" ? -1 : 1;

    this.scene.add(vrm.scene);
    this.scene.add(this.lookTarget);
    this.setupLights();
    this.setupModel();

    const head = this.bones.get("head");
    const headY = head ? head.getWorldPosition(new Vector3()).y : 1.35;
    this.eyeHeight = headY + 0.07;
    this.focus.set(0, headY - 0.045, 0);
    this.lookTarget.position.set(0, this.eyeHeight, 2);

    this.setupObservers();
    this.resize();
    this.applyMotionPreference();
    if (!this.reducedMotion) {
      this.waving = true;
      this.waveTime = -0.45; // short pause, then greet
    }

    // Let hair and clothes settle before the first visible frame.
    this.animate(0);
    for (let i = 0; i < 30; i++) vrm.update(1 / 60);
    this.renderFrame();
    this.updateRunning();
  }

  // -- Public API --

  setState(s: AvatarState): void {
    if (!(s in POSES)) return;
    this.state = s;
  }

  setMouthLevel(level: number): void {
    this.lipSync.setLevel(level, performance.now());
  }

  attachAnalyser(node: AnalyserNode): void {
    this.lipSync.attachAnalyser(node ?? null);
  }

  setDemoSpeech(on: boolean): void {
    this.lipSync.demo = on;
  }

  wave(): void {
    if (this.reducedMotion || (this.waving && this.waveTime < WAVE_IN + WAVE_HOLD)) return;
    this.waving = true;
    this.waveTime = 0;
  }

  resetCamera(): void {
    this.orbitYawGoal = 0;
    this.orbitPitchGoal = 0;
  }

  getDebugInfo(): AvatarDebugInfo {
    const mouth: Record<string, number> = {};
    for (const v of VISEMES) mouth[v] = Number(this.lipSync.weights[v].toFixed(3));
    return {
      fps: Math.round(1000 / this.frameMs),
      frameMs: Number(this.frameMs.toFixed(2)),
      frames: this.frames,
      triangles: this.renderer.info.render.triangles,
      drawCalls: this.renderer.info.render.calls,
      state: this.state,
      mouth,
      expressions: this.vrm.expressionManager?.expressions.map((e) => e.expressionName) ?? [],
      modelName: this.vrm.meta.metaVersion === "1" ? this.vrm.meta.name : (this.vrm.meta.title ?? ""),
      vrmVersion: this.vrm.meta.metaVersion,
    };
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.running = false;
    cancelAnimationFrame(this.rafId);
    for (const cleanup of this.cleanups.splice(0)) cleanup();
    this.lipSync.attachAnalyser(null);
    this.scene.remove(this.vrm.scene);
    VRMUtils.deepDispose(this.vrm.scene);
    this.renderer.renderLists.dispose();
    this.renderer.dispose();
  }

  // -- Setup --

  private setupLights(): void {
    // Soft key from the upper front-left, a weak cool fill from the right and
    // enough ambient to keep the toon shadows gentle.
    const key = new DirectionalLight(0xfff4ea, Math.PI * 0.62);
    key.position.set(-0.8, 1.4, 2).normalize();
    const fill = new DirectionalLight(0xdfe8ff, Math.PI * 0.16);
    fill.position.set(1.4, 0.4, 1).normalize();
    const ambient = new AmbientLight(0xffffff, Math.PI * 0.34);
    this.scene.add(key, fill, ambient);
  }

  private setupModel(): void {
    const { vrm } = this;
    VRMUtils.removeUnnecessaryVertices(vrm.scene);
    VRMUtils.combineSkeletons(vrm.scene);
    if (vrm.meta.metaVersion === "0") VRMUtils.rotateVRM0(vrm);
    // Skinned meshes move outside their rest bounding box; culling them pops.
    vrm.scene.traverse((object) => {
      object.frustumCulled = false;
    });

    // Some models flag emotions as binary (on/off). Blend them instead, so a
    // state change is a transition and never a jump.
    for (const expression of vrm.expressionManager?.expressions ?? []) {
      expression.isBinary = false;
      this.expressionNames.set(expression.expressionName.toLowerCase(), expression.expressionName);
    }
    if (vrm.lookAt) vrm.lookAt.target = this.lookTarget;

    const names: VRMHumanBoneName[] = [
      "hips",
      "spine",
      "chest",
      "upperChest",
      "neck",
      "head",
      "leftShoulder",
      "rightShoulder",
      "leftUpperArm",
      "rightUpperArm",
      "leftLowerArm",
      "rightLowerArm",
      "leftHand",
      "rightHand",
    ];
    for (const side of ["left", "right"] as const) {
      for (const finger of FINGERS) {
        for (const phalanx of PHALANGES) names.push(`${side}${finger}${phalanx}`);
      }
    }
    for (const name of names) {
      const node = vrm.humanoid.getNormalizedBoneNode(name);
      if (node) this.bones.set(name, node);
    }
    // Twist first, then roll: lets the raised arm turn its palm to the camera.
    this.bones.get("leftUpperArm")?.rotation.reorder("ZYX");
    this.bones.get("rightUpperArm")?.rotation.reorder("ZYX");
  }

  private setupObservers(): void {
    const { canvas } = this;
    canvas.style.touchAction = "pan-y";

    const resizeObserver = new ResizeObserver(() => {
      this.resize();
      if (!this.running && !this.disposed && !this.contextLost) this.renderFrame();
    });
    resizeObserver.observe(canvas);
    this.cleanups.push(() => resizeObserver.disconnect());

    const intersection = new IntersectionObserver((entries) => {
      const entry = entries[entries.length - 1];
      if (!entry) return;
      this.onScreen = entry.isIntersecting;
      this.updateRunning();
    });
    intersection.observe(canvas);
    this.cleanups.push(() => intersection.disconnect());

    this.listen(document, "visibilitychange", () => {
      this.pageVisible = document.visibilityState !== "hidden";
      this.updateRunning();
    });
    this.pageVisible = document.visibilityState !== "hidden";

    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    this.reducedMotion = media.matches;
    this.listen(media, "change", () => {
      this.reducedMotion = media.matches;
      this.applyMotionPreference();
    });

    this.listen(window, "pointermove", (event) => {
      const e = event as PointerEvent;
      const rect = canvas.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height * 0.4;
      this.pointerX = clamp((e.clientX - cx) / Math.max(1, window.innerWidth * 0.5), -1, 1);
      this.pointerY = clamp((e.clientY - cy) / Math.max(1, window.innerHeight * 0.5), -1, 1);
      this.pointerStamp = this.time;
    });

    // Minimal drag-to-orbit; `resetCamera()` eases back to the bust framing.
    let dragId = -1;
    let lastX = 0;
    let lastY = 0;
    this.listen(canvas, "pointerdown", (event) => {
      const e = event as PointerEvent;
      if (e.button !== 0) return;
      dragId = e.pointerId;
      lastX = e.clientX;
      lastY = e.clientY;
      canvas.setPointerCapture?.(e.pointerId);
    });
    this.listen(canvas, "pointermove", (event) => {
      const e = event as PointerEvent;
      if (e.pointerId !== dragId) return;
      const scale = 2.4 / Math.max(1, canvas.clientWidth);
      this.orbitYawGoal = clamp(this.orbitYawGoal - (e.clientX - lastX) * scale, -ORBIT_YAW_LIMIT, ORBIT_YAW_LIMIT);
      this.orbitPitchGoal = clamp(
        this.orbitPitchGoal + (e.clientY - lastY) * scale,
        -ORBIT_PITCH_LIMIT,
        ORBIT_PITCH_LIMIT,
      );
      lastX = e.clientX;
      lastY = e.clientY;
    });
    const endDrag = (event: Event): void => {
      if ((event as PointerEvent).pointerId === dragId) dragId = -1;
    };
    this.listen(canvas, "pointerup", endDrag);
    this.listen(canvas, "pointercancel", endDrag);

    this.listen(canvas, "webglcontextlost", (event) => {
      event.preventDefault();
      this.contextLost = true;
      this.updateRunning();
    });
    this.listen(canvas, "webglcontextrestored", () => {
      this.contextLost = false;
      this.updateRunning();
    });
  }

  private listen(target: EventTarget, type: string, handler: (event: Event) => void): void {
    target.addEventListener(type, handler, { passive: type !== "webglcontextlost" });
    this.cleanups.push(() => target.removeEventListener(type, handler));
  }

  private applyMotionPreference(): void {
    if (this.reducedMotion) {
      this.waving = false;
      this.intro = 0;
    }
  }

  // -- Loop --

  private updateRunning(): void {
    const shouldRun = !this.disposed && this.pageVisible && this.onScreen && !this.contextLost;
    if (shouldRun === this.running) return;
    this.running = shouldRun;
    if (shouldRun) {
      this.lastFrame = performance.now(); // drop the time spent paused
      this.rafId = requestAnimationFrame(this.tick);
    } else {
      cancelAnimationFrame(this.rafId);
    }
  }

  private readonly tick = (now: number): void => {
    if (!this.running) return;
    this.rafId = requestAnimationFrame(this.tick);
    const raw = Math.max(0, (now - this.lastFrame) / 1000);
    this.lastFrame = now;
    // After a long stall, do not let the springs integrate one huge step.
    if (raw > 0.25) this.vrm.springBoneManager?.reset();
    const dt = Math.min(raw, 1 / 20);
    this.frameMs += (raw * 1000 - this.frameMs) * 0.05;
    this.animate(dt);
    this.vrm.update(dt);
    this.renderFrame();
  };

  private renderFrame(): void {
    this.renderer.render(this.scene, this.camera);
    this.frames++;
  }

  private resize(): void {
    const { canvas, renderer, camera } = this;
    const width = Math.max(1, canvas.clientWidth);
    const height = Math.max(1, canvas.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();

    const halfFov = Math.tan(MathUtils.degToRad(CAMERA_FOV) / 2);
    const forHeight = FRAME_HEIGHT / 2 / halfFov;
    const forWidth = FRAME_MIN_WIDTH / 2 / (halfFov * camera.aspect);
    this.cameraDistance = Math.max(forHeight, forWidth);
    this.placeCamera();
  }

  private placeCamera(): void {
    const distance = this.cameraDistance * (1 + 0.14 * smooth(this.intro));
    const cosPitch = Math.cos(this.orbitPitch);
    this.camera.position.set(
      this.focus.x + Math.sin(this.orbitYaw) * cosPitch * distance,
      this.focus.y + Math.sin(this.orbitPitch) * distance,
      this.focus.z + Math.cos(this.orbitYaw) * cosPitch * distance,
    );
    this.camera.lookAt(this.focus);
  }

  // -- Animation --

  private animate(dt: number): void {
    this.time += dt;
    const t = this.time;
    const target = POSES[this.state];
    const pose = this.pose;

    this.motion = damp(this.motion, this.reducedMotion ? 0.2 : 1, 4, dt);
    const m = this.motion;

    pose.pitch = damp(pose.pitch, target.pitch, 5, dt);
    pose.yaw = damp(pose.yaw, target.yaw, 5, dt);
    pose.roll = damp(pose.roll, target.roll, 5, dt);
    pose.lean = damp(pose.lean, target.lean, 4, dt);
    pose.gazeX = damp(pose.gazeX, target.gazeX, 6, dt);
    pose.gazeY = damp(pose.gazeY, target.gazeY, 6, dt);
    pose.follow = damp(pose.follow, this.reducedMotion ? 0 : target.follow, 4, dt);

    // Camera
    this.intro = Math.max(0, this.intro - dt / 1.4);
    this.orbitYaw = damp(this.orbitYaw, this.orbitYawGoal, 7, dt);
    this.orbitPitch = damp(this.orbitPitch, this.orbitPitchGoal, 7, dt);
    this.placeCamera();

    // Pointer follow, drifting back to the camera when the pointer goes quiet.
    const pointerFresh = t - this.pointerStamp < 5;
    this.followX = damp(this.followX, pointerFresh ? this.pointerX : 0, 5, dt);
    this.followY = damp(this.followY, pointerFresh ? this.pointerY : 0, 5, dt);
    const fx = this.followX * pose.follow;
    const fy = this.followY * pose.follow;

    this.lipSync.update(dt, performance.now());
    this.emphasis = damp(this.emphasis, this.lipSync.openness, 9, dt);

    this.animateBody(t, dt, m, fx, fy);
    this.animateFace(t, dt, target, fx, fy);
  }

  private animateBody(t: number, dt: number, m: number, fx: number, fy: number): void {
    const s = this.axisSign;
    const pose = this.pose;
    const bone = (name: VRMHumanBoneName): Object3D | undefined => this.bones.get(name);

    const breath = Math.sin(t * 1.55);
    const breathLag = Math.sin(t * 1.55 - 0.6);
    // Sums of incommensurate sines: cheap, smooth, never visibly loops.
    const driftA = Math.sin(t * 0.43) + 0.5 * Math.sin(t * 1.07 + 1.3);
    const driftB = Math.sin(t * 0.31 + 2.1) + 0.5 * Math.sin(t * 0.83 + 0.4);
    const driftC = Math.sin(t * 0.57 + 4.2) + 0.4 * Math.sin(t * 1.31);
    const talk = this.emphasis;

    bone("hips")?.rotation.set(0, 0.022 * driftB * m, s * 0.008 * driftA * m);
    bone("spine")?.rotation.set(
      s * (0.012 * breath * m + pose.lean),
      0.02 * driftA * m + fx * 0.06,
      s * 0.012 * driftC * m,
    );
    bone("chest")?.rotation.set(s * (0.018 * breathLag * m + pose.lean * 0.5), fx * 0.05, s * -0.008 * driftC * m);

    const nod = talk * 0.035 * Math.sin(t * 5.2) * m;
    const headPitch = pose.pitch + fy * 0.11 + 0.014 * driftB * m - 0.01 * breath * m + nod;
    const headYaw = pose.yaw + fx * 0.24 + 0.02 * driftC * m + talk * 0.02 * Math.sin(t * 2.3) * m;
    const headRoll = pose.roll + 0.014 * driftA * m - fx * 0.03;
    bone("neck")?.rotation.set(s * headPitch * 0.4, headYaw * 0.4, s * headRoll * 0.4);
    bone("head")?.rotation.set(s * headPitch * 0.6, headYaw * 0.6, s * headRoll * 0.6);

    bone("leftShoulder")?.rotation.set(0, 0, s * 0.02 * breathLag * m);
    bone("rightShoulder")?.rotation.set(0, 0, s * -0.02 * breathLag * m);

    // Greeting wave envelope (right arm).
    let waveGoal = 0;
    if (this.waving) {
      this.waveTime += dt;
      if (this.waveTime > WAVE_IN + WAVE_HOLD + WAVE_OUT) this.waving = false;
      else if (this.waveTime > 0 && this.waveTime < WAVE_IN + WAVE_HOLD) waveGoal = 1;
    }
    this.waveWeight = damp(this.waveWeight, waveGoal, waveGoal > this.waveWeight ? 7 : 5, dt);
    const w = smooth(clamp(this.waveWeight, 0, 1));

    const armSway = 0.02 * breath * m;
    const armDrift = 0.03 * driftA * m;
    bone("leftUpperArm")?.rotation.set(s * armDrift, 0, s * -(ARM_DOWN + armSway));
    bone("leftLowerArm")?.rotation.set(0, -(ELBOW_REST + 0.03 * driftB * m), 0);
    bone("leftHand")?.rotation.set(0, 0, s * -0.08);

    const flap = Math.sin(t * 11.5);
    bone("rightUpperArm")?.rotation.set(
      s * MathUtils.lerp(-armDrift, -Math.PI / 2, w),
      0,
      s * MathUtils.lerp(ARM_DOWN + armSway, 0.86, w),
    );
    bone("rightLowerArm")?.rotation.set(0, MathUtils.lerp(ELBOW_REST + 0.03 * driftC * m, 2.12 + 0.28 * flap, w), 0);
    bone("rightHand")?.rotation.set(0, 0, s * MathUtils.lerp(0.08, 0.22 * flap, w));

    for (const finger of FINGERS) {
      for (const phalanx of PHALANGES) {
        bone(`left${finger}${phalanx}`)?.rotation.set(0, 0, s * -FINGER_CURL);
        bone(`right${finger}${phalanx}`)?.rotation.set(0, 0, s * FINGER_CURL * (1 - w * 0.9));
      }
    }
  }

  private animateFace(t: number, dt: number, target: Pose, fx: number, fy: number): void {
    const manager = this.vrm.expressionManager;
    const pose = this.pose;

    // Gaze: eyes lead, the head (above) follows with less amplitude.
    const gx = pose.gazeX + fx * 0.9;
    const gy = pose.gazeY - fy * 0.55;
    const micro = this.reducedMotion ? 0 : 0.02 * Math.sin(t * 0.9) + 0.012 * Math.sin(t * 2.7 + 1);
    this.lookTarget.position.set(gx * 0.9 + micro, this.eyeHeight + gy * 0.7, 1.6);

    if (!manager) return;

    for (const name of EMOTIONS) {
      const goal = target.expressions[name] ?? 0;
      const next = damp(this.emotionWeights[name], goal, 5, dt);
      this.emotionWeights[name] = next < 0.001 && goal === 0 ? 0 : next;
      manager.setValue(this.expressionNames.get(name) ?? name, this.emotionWeights[name]);
    }

    for (const v of VISEMES) manager.setValue(v, this.lipSync.weights[v]);

    manager.setValue("blink", this.updateBlink(dt));
  }

  private updateBlink(dt: number): number {
    const CLOSE = 0.07;
    const OPEN = 0.13;
    if (this.blinkPhase < 0) {
      this.blinkIn -= dt;
      if (this.blinkIn <= 0) {
        this.blinkPhase = 0;
        this.blinkAgain = !this.blinkAgain && Math.random() < 0.18;
      }
      this.blinkValue = 0;
    } else {
      this.blinkPhase += dt;
      const p = this.blinkPhase;
      if (p < CLOSE) this.blinkValue = smooth(p / CLOSE);
      else if (p < CLOSE + OPEN) this.blinkValue = 1 - smooth((p - CLOSE) / OPEN);
      else {
        this.blinkValue = 0;
        this.blinkPhase = -1;
        // Blink a little less while listening closely, more while thinking.
        const base = this.state === "thinking" ? 1.6 : 2.4;
        this.blinkIn = this.blinkAgain ? 0.12 : base + Math.random() * 3.4;
      }
    }
    return this.blinkValue;
  }
}

/**
 * Loads the VRM model and starts rendering it into `canvas`.
 *
 * The canvas must be sized by CSS; the drawing buffer follows it. Rejects with
 * an {@link AvatarError} when WebGL is unavailable or the model cannot be
 * loaded, so the caller can fall back to a 2D visual.
 */
export async function mountAvatar(
  canvas: HTMLCanvasElement,
  opts: MountAvatarOptions = {},
): Promise<AvatarHandle> {
  const report = (p: number): void => {
    try {
      opts.onProgress?.(p);
    } catch {
      // A faulty progress callback must not break the load.
    }
  };

  report(0);
  const renderer = createRenderer(canvas);
  let vrm: VRM;
  try {
    vrm = await loadVrm(resolveModelUrl(opts.modelUrl), report);
  } catch (error) {
    renderer.dispose();
    throw error;
  }

  try {
    const avatar = new Avatar(canvas, renderer, vrm);
    if (typeof location !== "undefined" && new URLSearchParams(location.search).has("avatarDemo")) {
      avatar.setDemoSpeech(true);
    }
    report(1);
    return avatar;
  } catch (cause) {
    VRMUtils.deepDispose(vrm.scene);
    renderer.dispose();
    throw new AvatarError("invalid-model", "The avatar model loaded but could not be set up.", cause);
  }
}
