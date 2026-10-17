import fs from "node:fs";
import path from "node:path";
import { defineConfig, type Plugin } from "vitest/config";
import react from "@vitejs/plugin-react";

const base = process.env.VITE_BASE || "/";

// Installable app (manifest, service worker, icons) from pwa/: copied to the build root in every build, unlike public/,
// which only the static demo ships. Paths inside the manifest are relative, so it works under any base.
function pwa(): Plugin {
  const dir = path.resolve(__dirname, "pwa");
  const files = fs.readdirSync(dir);
  return {
    name: "pwa",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const name = req.url?.split("?")[0].slice(base.length);
        if (!name || !files.includes(name)) return next();
        res.setHeader("Content-Type", name.endsWith(".js") ? "text/javascript" : name.endsWith(".png") ? "image/png" : "application/manifest+json");
        res.end(fs.readFileSync(path.join(dir, name)));
      });
    },
    generateBundle() {
      for (const f of files) this.emitFile({ type: "asset", fileName: f, source: fs.readFileSync(path.join(dir, f)) });
    },
    transformIndexHtml: () => [
      { tag: "link", attrs: { rel: "manifest", href: `${base}manifest.webmanifest` }, injectTo: "head" },
      { tag: "link", attrs: { rel: "icon", type: "image/png", href: `${base}icon-192.png` }, injectTo: "head" },
      { tag: "link", attrs: { rel: "apple-touch-icon", href: `${base}apple-touch-icon.png` }, injectTo: "head" },
    ],
  };
}

export default defineConfig({
  base,
  // anything built for Pages (it has a base path) goes to its own folder so it can never overwrite the live app's dist/
  build: { outDir: process.env.VITE_BASE ? "dist-static" : "dist" },
  // the snapshot files are only needed by the API-less demo
  publicDir: process.env.VITE_STATIC === "1" && !process.env.VITE_API_URL ? "public" : false,
  plugins: [react(), pwa()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  test: { environment: "node" },
});
