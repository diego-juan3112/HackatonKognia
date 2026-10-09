// Minimal static file server for the built site (tests only).
// `astro preview` keeps a lock file per project, so it cannot run next to another
// preview; this serves a build directory of its own on a port of its own.
// Usage: node tests/e2e/static-server.mjs <dir> <port>
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";

const root = resolve(process.argv[2] ?? "dist");
const port = Number(process.argv[3] ?? 4329);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".md": "text/markdown; charset=utf-8",
  ".vrm": "model/gltf-binary",
  ".wasm": "application/wasm",
};

function resolveFile(urlPath) {
  const clean = normalize(decodeURIComponent(urlPath)).replace(/^([/\\])+/, "");
  const target = resolve(join(root, clean));
  if (target !== root && !target.startsWith(root + sep)) return null;
  if (existsSync(target) && statSync(target).isFile()) return target;
  const index = join(target, "index.html");
  if (existsSync(index)) return index;
  return null;
}

createServer((req, res) => {
  const { pathname } = new URL(req.url ?? "/", "http://localhost");
  const file = resolveFile(pathname);
  if (!file) {
    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("404");
    return;
  }
  res.writeHead(200, {
    "Content-Type": MIME[extname(file)] ?? "application/octet-stream",
    "Content-Length": statSync(file).size,
    "Cache-Control": "no-store",
  });
  if (req.method === "HEAD") res.end();
  else createReadStream(file).pipe(res);
}).listen(port, "127.0.0.1", () => {
  console.log(`static-server: ${root} -> http://127.0.0.1:${port}`);
});
