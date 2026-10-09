import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Contract tests (docs/08 §13): no browser, no network, no credentials.
export default defineConfig({
  root: fileURLToPath(new URL("..", import.meta.url)),
  test: {
    environment: "node",
    include: ["tests/contract/**/*.test.ts"],
    // Empty on purpose: the suite must run against web/mocks, never a backend.
    env: { PUBLIC_API_URL: "", PUBLIC_VOICE_ENGINE: "fake" },
    testTimeout: 15_000,
  },
});
