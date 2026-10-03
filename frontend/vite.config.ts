import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: process.env.VITE_BASE || "/",
  // anything built for Pages (it has a base path) goes to its own folder so it can never overwrite the live app's dist/
  build: { outDir: process.env.VITE_BASE ? "dist-static" : "dist" },
  // the snapshot files are only needed by the API-less demo
  publicDir: process.env.VITE_STATIC === "1" && !process.env.VITE_API_URL ? "public" : false,
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  test: { environment: "node" },
});
