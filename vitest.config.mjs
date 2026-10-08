import { defineConfig } from "vitest/config";

process.env.TZ = "UTC";

export default defineConfig({
  test: {
    environment: "node",
    include: ["frontend/tests/**/*.test.js"],
  },
});
