// @ts-check
import { defineConfig } from "astro/config";

// Static output: the browser talks to the FastAPI backend (PUBLIC_API_URL) and
// to the voice providers directly; nothing is rendered on the server.
export default defineConfig({
  output: "static",
  server: { port: 4321 },
});
