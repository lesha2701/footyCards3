/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Rarely-changing libraries in their own long-cached chunks, so a
        // deploy that only touches app code doesn't re-download them.
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          query: ["@tanstack/react-query", "axios", "zustand"],
          motion: ["framer-motion"],
          // The 3D engine (~180 KB gzip) and its React renderer: loaded only
          // by the lazy 3D screens, never by the entry. Without their own
          // chunks Rollup folds them into a chunk named after (and hashed
          // with) app code — "textures-*.js" — so any edit to a 3D scene
          // made every player download three.js again.
          three: ["three"],
          r3f: ["@react-three/fiber"],
        },
      },
    },
  },
  server: {
    host: true,
    port: 5173,
    // Docker Desktop bind mounts on Windows/macOS don't deliver file-change
    // events into the container — poll instead (docker-compose.yml sets this).
    watch: process.env.VITE_WATCH_POLLING === "true" ? { usePolling: true, interval: 300 } : undefined,
    allowedHosts: [".lhr.life", ".ngrok-free.app", ".ngrok-free.dev", ".ngrok.io"],
    proxy: {
      "/api": {
        target: "http://backend:8000",
        changeOrigin: true,
      },
      "/static": {
        target: "http://backend:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: true,
    port: 5173,
    allowedHosts: [".lhr.life", ".ngrok-free.app", ".ngrok-free.dev", ".ngrok.io"],
    proxy: {
      "/api": {
        target: "http://backend:8000",
        changeOrigin: true,
      },
      "/static": {
        target: "http://backend:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
