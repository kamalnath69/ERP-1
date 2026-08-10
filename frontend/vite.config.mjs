import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

const ROOT_DIR = path.dirname(fileURLToPath(import.meta.url));

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${Math.round((bytes / (1024 ** unitIndex)) * 100) / 100} ${units[unitIndex]}`;
}

function formatDuration(milliseconds) {
  const seconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  if (hours) return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
  if (minutes) return `${minutes}m ${seconds % 60}s`;
  return `${seconds}s`;
}

function viteHealthPlugin() {
  const startedAt = Date.now();
  const status = {
    state: "starting",
    errors: [],
    lastCompileTime: null,
    lastSuccessTime: null,
    totalCompiles: 0,
  };

  const send = (response, statusCode, body, contentType = "application/json") => {
    response.statusCode = statusCode;
    response.setHeader("Content-Type", `${contentType}; charset=utf-8`);
    response.end(contentType === "application/json" ? JSON.stringify(body) : body);
  };

  return {
    name: "edvatiq-health",
    apply: "serve",
    configureServer(server) {
      server.watcher.on("change", () => {
        status.lastCompileTime = Date.now();
        status.totalCompiles += 1;
      });
      server.watcher.on("error", (error) => {
        status.state = "failed";
        status.errors = [{ message: error.message, stack: error.stack }];
      });

      server.middlewares.use((request, response, next) => {
        const pathname = new URL(request.url || "/", "http://localhost").pathname;
        const ready = status.state === "ready";
        const uptime = Date.now() - startedAt;

        if (pathname === "/health/live") {
          send(response, 200, { alive: true, timestamp: new Date().toISOString() });
          return;
        }
        if (pathname === "/health/simple") {
          send(response, ready ? 200 : 503, ready ? "OK" : "ERROR", "text/plain");
          return;
        }
        if (pathname === "/health/ready") {
          send(response, ready ? 200 : 503, { ready, state: status.state });
          return;
        }
        if (pathname === "/health/errors") {
          send(response, 200, {
            errorCount: status.errors.length,
            warningCount: 0,
            errors: status.errors,
            warnings: [],
            state: status.state,
          });
          return;
        }
        if (pathname === "/health/stats") {
          send(response, 200, {
            totalCompiles: status.totalCompiles,
            lastCompileTime: status.lastCompileTime
              ? new Date(status.lastCompileTime).toISOString()
              : null,
            lastSuccessTime: status.lastSuccessTime
              ? new Date(status.lastSuccessTime).toISOString()
              : null,
            serverUptime: formatDuration(uptime),
          });
          return;
        }
        if (pathname === "/health") {
          const memory = process.memoryUsage();
          send(response, ready ? 200 : 503, {
            status: ready ? "healthy" : "unhealthy",
            timestamp: new Date().toISOString(),
            uptime: { seconds: Math.floor(uptime / 1000), formatted: formatDuration(uptime) },
            vite: {
              state: status.state,
              isHealthy: ready,
              errors: status.errors.length,
              warnings: 0,
              lastCompileTime: status.lastCompileTime
                ? new Date(status.lastCompileTime).toISOString()
                : null,
              lastSuccessTime: status.lastSuccessTime
                ? new Date(status.lastSuccessTime).toISOString()
                : null,
              totalCompiles: status.totalCompiles,
            },
            server: {
              nodeVersion: process.version,
              platform: os.platform(),
              arch: os.arch(),
              memory: {
                heapUsed: formatBytes(memory.heapUsed),
                heapTotal: formatBytes(memory.heapTotal),
                rss: formatBytes(memory.rss),
              },
            },
            environment: "development",
          });
          return;
        }

        next();
      });

      return () => {
        status.state = "ready";
        status.lastSuccessTime = Date.now();
        status.totalCompiles += 1;
      };
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ROOT_DIR, "");
  const healthChecksEnabled = env.ENABLE_HEALTH_CHECK === "true";

  return {
    plugins: [react(), healthChecksEnabled && viteHealthPlugin()].filter(Boolean),
    resolve: {
      alias: {
        "@": path.resolve(ROOT_DIR, "src"),
      },
    },
    envPrefix: ["VITE_", "REACT_APP_"],
    server: {
      host: "0.0.0.0",
      port: 3000,
      headers: {
        "Cross-Origin-Resource-Policy": "same-origin",
      },
    },
    preview: {
      host: "0.0.0.0",
      headers: {
        "Cross-Origin-Resource-Policy": "same-origin",
      },
    },
    build: {
      outDir: "build",
      emptyOutDir: true,
      sourcemap: env.GENERATE_SOURCEMAP !== "false",
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: "./src/setupTests.js",
      clearMocks: true,
      css: true,
      maxWorkers: 4,
    },
  };
});
