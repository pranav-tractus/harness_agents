import path from "path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    cssMinify: false,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
