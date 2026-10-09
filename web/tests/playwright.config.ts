import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

/**
 * Browser tests over the production build (docs/08 §13).
 *
 * - Uses the installed Edge (`channel: "msedge"`); no Playwright browser download.
 * - Builds into tests/.cache/dist and serves it with a tiny static server, so the
 *   run never touches web/dist nor the `astro preview` lock of someone else.
 * - PUBLIC_API_URL is forced empty: the suite runs on web/mocks and the scripted
 *   engine, without credentials, backend or microphone.
 */
const WEB = fileURLToPath(new URL("..", import.meta.url));
const PORT = Number(process.env.E2E_PORT ?? 4329);

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  timeout: 120_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 3,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "./artifacts/results.json" }]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    channel: "msedge",
    locale: "es-CO",
    viewport: { width: 1366, height: 768 },
    screenshot: "only-on-failure",
    launchOptions: {
      // A fake microphone, so nothing prompts if a real engine asks for one.
      args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
    },
  },
  webServer: {
    command: `npx astro build --outDir tests/.cache/dist && node tests/e2e/static-server.mjs tests/.cache/dist ${PORT}`,
    cwd: WEB,
    url: `http://127.0.0.1:${PORT}/consola`,
    env: { PUBLIC_API_URL: "", PUBLIC_VOICE_ENGINE: "fake" },
    reuseExistingServer: false,
    timeout: 240_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
