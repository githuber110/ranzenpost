import { defineConfig } from "vitest/config";

process.env.TZ = "UTC";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["tests/card/**/*.test.js"],
  },
});
