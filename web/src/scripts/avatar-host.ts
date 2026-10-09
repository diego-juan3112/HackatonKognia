/**
 * Mounts the 3D avatar into `#avatar-canvas` and keeps it in sync with the store.
 *
 * The avatar lives in `src/avatar/` and is built by another lane. This host
 * must work whether or not that module exists or loads: `import.meta.glob`
 * resolves to nothing when the file is absent (a plain dynamic import of a
 * missing file would break the build), and any failure leaves the orb as the
 * visual fallback.
 *
 * Expected module shape (src/avatar/index.ts):
 *   mountAvatar(canvas, opts) => Promise<AvatarHandle>
 *   AvatarHandle: setState(state), setMouthLevel(0..1), resetCamera(), dispose()
 */
import { getState, subscribe } from "../voice/store";
import type { EngineStatus } from "../voice/types";

export interface AvatarHandle {
  setState(state: EngineStatus): void;
  setMouthLevel(level: number): void;
  resetCamera(): void;
  dispose(): void;
}

interface AvatarModule {
  mountAvatar(canvas: HTMLCanvasElement, opts?: Record<string, unknown>): Promise<AvatarHandle>;
}

const loaders = import.meta.glob("../avatar/index.ts") as Record<string, () => Promise<unknown>>;

export interface AvatarHost {
  /** Resolves to true when the avatar is on screen, false when the orb stays. */
  ready: Promise<boolean>;
  resetCamera(): void;
  dispose(): void;
}

export function hostAvatar(stage: HTMLElement, canvas: HTMLCanvasElement): AvatarHost {
  let handle: AvatarHandle | null = null;
  let disposed = false;
  let mouthTimer: ReturnType<typeof setInterval> | undefined;
  let pulse = 0;

  const safely = (fn: () => void): void => {
    try {
      fn();
    } catch (err) {
      console.warn("[avatar] call failed", err);
    }
  };

  // No audio yet (the engine is a double): the mouth follows the transcript cadence.
  const mouth = (speaking: boolean): void => {
    clearInterval(mouthTimer);
    mouthTimer = undefined;
    if (!handle) return;
    if (!speaking) {
      safely(() => handle?.setMouthLevel(0));
      return;
    }
    mouthTimer = setInterval(() => {
      pulse = Math.max(0, pulse - 0.18);
      const t = performance.now() / 1000;
      const level = 0.25 + 0.3 * Math.abs(Math.sin(t * 9)) + 0.25 * Math.abs(Math.sin(t * 5.3)) + pulse * 0.2;
      safely(() => handle?.setMouthLevel(Math.min(1, level)));
    }, 60);
  };

  const unsubscribe = subscribe((state, slices) => {
    if (!handle) return;
    if (slices.has("transcript")) pulse = 1;
    if (slices.has("status") || slices.has("reset")) {
      safely(() => handle?.setState(state.status));
      mouth(state.status === "speaking");
    }
  });

  const ready = (async (): Promise<boolean> => {
    const load = loaders["../avatar/index.ts"];
    if (!load) {
      stage.dataset.avatar = "absent";
      return false;
    }
    stage.dataset.avatar = "loading";
    try {
      const mod = (await load()) as Partial<AvatarModule>;
      if (typeof mod.mountAvatar !== "function") throw new Error("src/avatar/index.ts does not export mountAvatar");
      const mounted = await mod.mountAvatar(canvas, {});
      if (disposed) {
        mounted.dispose();
        return false;
      }
      handle = mounted;
      stage.dataset.avatar = "ready";
      const status = getState().status;
      safely(() => handle?.setState(status));
      mouth(status === "speaking");
      return true;
    } catch (err) {
      console.warn("[avatar] not available, keeping the orb", err);
      stage.dataset.avatar = "failed";
      return false;
    }
  })();

  return {
    ready,
    resetCamera: () => safely(() => handle?.resetCamera()),
    dispose: () => {
      disposed = true;
      unsubscribe();
      clearInterval(mouthTimer);
      safely(() => handle?.dispose());
      handle = null;
    },
  };
}
