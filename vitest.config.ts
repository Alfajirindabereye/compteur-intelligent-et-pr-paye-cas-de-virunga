import { defineConfig } from "vitest/config";
import path from "path";

const templateRoot = path.resolve(import.meta.dirname);

export default defineConfig({
  root: templateRoot,
  resolve: {
    alias: {
      "@": path.resolve(templateRoot, "client", "src"),
      "@shared": path.resolve(templateRoot, "shared"),
      "@assets": path.resolve(templateRoot, "attached_assets"),
    },
  },
  test: {
    environment: "node",
    // Le premier rendu jsdom de la page d'accueil dépasse 5 s sur une machine modeste.
    testTimeout: 20000,
    include: ["server/**/*.test.ts", "server/**/*.spec.ts", "client/**/*.test.ts", "client/**/*.spec.ts", "client/**/*.test.tsx", "client/**/*.spec.tsx"],
    environmentMatchGlobs: [["client/**/*.test.{ts,tsx}", "jsdom"]],
    server: {
      deps: {
        inline: ["streamdown"],
      },
    },
  },
});
