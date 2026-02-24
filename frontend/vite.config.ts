import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
      },
    },
    server: {
      port: 5173,
      proxy: {
        // Proxy all /api/* and /ws/* requests to the backend during development.
        "/api": {
          target: env.VITE_API_BASE_URL || "http://localhost:8000",
          changeOrigin: true,
          ws: true,
          secure: false,
        },
        "/ws": {
          target: env.VITE_API_BASE_URL || "http://localhost:8000",
          changeOrigin: true,
          ws: true,
          secure: false,
        },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: true,
      rollupOptions: {
        output: {
          manualChunks: {
            react: ["react", "react-dom", "react-router-dom"],
            monaco: ["monaco-editor", "@monaco-editor/react"],
            query: ["@tanstack/react-query"],
            ui: ["lucide-react", "clsx", "tailwind-merge"],
          },
        },
      },
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["src/__tests__/setup.ts"],
      coverage: {
        reporter: ["text", "html"],
        exclude: ["src/__tests__/**", "src/main.tsx"],
      },
    },
  };
});
