// Unit tests of the command palette: Vitest with jsdom and Testing Library.
// One worker and no file parallelism: the suite is small, and this keeps its memory use low
// enough for a small server (docs/development.md, "Memory").
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  root: fileURLToPath(new URL("..", import.meta.url)),
  plugins: [react()],
  test: {
    environment: "jsdom",
    // The palette inlines its stylesheet (?inline): process it, so the tests see the real CSS.
    css: { include: [/palette\.css/u] },
    include: ["palette/test/**/*.test.{ts,tsx}", "gallery/test/**/*.test.{ts,tsx}"],
    pool: "forks",
    maxWorkers: 1,
    fileParallelism: false,
    restoreMocks: true,
    unstubGlobals: true,
  },
});
