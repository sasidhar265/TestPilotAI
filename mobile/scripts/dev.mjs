import http from "node:http";
import https from "node:https";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { buildMobile, root, pageRoutes } from "./build.mjs";
import { buildSettings } from "./config.mjs";

const settings = buildSettings(["--development", ...process.argv.slice(2)]);
await buildMobile(settings);
const mime = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".json": "application/json",
};
const backend = new URL(settings.backend);
const port = Number(process.env.MOBILE_DEV_PORT || 5173);

// Loopback-only preview: keep cookies same-origin without weakening production CORS.
http
  .createServer(async (request, response) => {
    const url = new URL(request.url, "http://localhost");
    if (url.pathname.startsWith("/api/") || url.pathname === "/openapi.json") {
      const transport = backend.protocol === "https:" ? https : http;
      const upstream = transport.request(
        new URL(url.pathname + url.search, backend),
        {
          method: request.method,
          headers: { ...request.headers, host: backend.host },
        },
        (remote) => {
          response.writeHead(remote.statusCode, { ...remote.headers, "cache-control": "no-store" });
          remote.pipe(response);
        },
      );
      upstream.on("error", () => {
        if (!response.headersSent) response.writeHead(502, { "content-type": "application/json" });
        response.end('{"detail":"Local backend is unavailable. Start FastAPI and retry."}');
      });
      request.on("aborted", () => upstream.destroy());
      request.pipe(upstream);
      return;
    }
    try {
      const pathname = decodeURIComponent(url.pathname);
      const file =
        pageRoutes[pathname] ||
        (["/", "/project-dashboard", "/progress", "/quality-lifecycle"].includes(pathname)
          ? "index.html"
          : pathname.replace(/^\/+/, ""));
      const target = path.resolve(root, "dist", file);
      if (!target.startsWith(path.join(root, "dist") + path.sep) || !(await stat(target)).isFile())
        throw new Error("Not found");
      response.writeHead(200, {
        "content-type": mime[path.extname(target)] || "application/octet-stream",
        "cache-control": "no-store",
      });
      response.end(await readFile(target));
    } catch {
      response.writeHead(404);
      response.end("Not found");
    }
  })
  .listen(port, "127.0.0.1", () =>
    console.log(`Mobile browser preview: http://127.0.0.1:${port} (backend ${settings.backend})`),
  );
