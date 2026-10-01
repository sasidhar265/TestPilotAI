import { cp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { build } from "esbuild";
import { buildSettings, capacitorConfig } from "./config.mjs";

export const root = fileURLToPath(new URL("../", import.meta.url));
export const pageRoutes = {
  "/login": "login.html",
  "/documentation": "documentation.html",
  "/user-guide": "user-guide.html",
  "/knowledge": "knowledge.html",
  "/logs": "logs.html",
  "/docs": "api-docs.html",
  "/admin/users": "users.html",
};

export async function buildMobile(settings) {
  const source = path.resolve(root, "../app/static");
  const destination = path.join(root, "dist");
  await mkdir(destination, { recursive: true });
  await cp(source, path.join(destination, "static"), { recursive: true });
  const pages = {};
  for (const filename of (await readdir(source)).filter((name) => name.endsWith(".html"))) {
    let html = await readFile(path.join(source, filename), "utf8");
    const scripts = [];
    html = html.replace(/<script\b[^>]*\bsrc="([^"]+)"[^>]*>\s*<\/script>/g, (_, src) => {
      scripts.push(src);
      return "";
    });
    pages[filename] = scripts;
    const csp = `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' ${settings.backend}; object-src 'none'; base-uri 'none'; form-action 'self'`;
    html = html
      .replace("<head>", `<head>\n    <meta http-equiv="Content-Security-Policy" content="${csp}">`)
      .replace(
        "width=device-width, initial-scale=1",
        "width=device-width, initial-scale=1, viewport-fit=cover",
      )
      .replace("</head>", '<link rel="stylesheet" href="/native.css"></head>')
      .replace("<body", `<body data-mobile-page="${filename}"`)
      .replace("</body>", '<script src="/mobile.js" defer></script></body>');
    await writeFile(path.join(destination, filename), html);
    // Existing links to /static/*.html must also receive the native bootstrap.
    await writeFile(path.join(destination, "static", filename), html);
  }
  await cp(path.join(root, "src/native.css"), path.join(destination, "native.css"));
  await build({
    entryPoints: [path.join(root, "src/bootstrap.js")],
    outfile: path.join(destination, "mobile.js"),
    bundle: true,
    format: "iife",
    target: "es2022",
    define: {
      __MOBILE_SETTINGS__: JSON.stringify(settings),
      __MOBILE_PAGES__: JSON.stringify(pages),
      __MOBILE_ROUTES__: JSON.stringify(pageRoutes),
    },
  });
  await writeFile(
    path.join(root, "capacitor.config.json"),
    JSON.stringify(capacitorConfig(settings), null, 2) + "\n",
  );
  await writeFile(
    path.join(destination, "build-info.json"),
    JSON.stringify(settings, null, 2) + "\n",
  );
  console.log(
    `Bundled mobile UI for ${settings.backend} (${settings.development ? "development" : "release"}).`,
  );
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await buildMobile(buildSettings(process.argv.slice(2)));
}
