const fs = require("fs");
const path = require("path");
const { defineConfig, devices } = require("@playwright/test");

const PORT = process.env.E2E_PORT || "8199";
const BASE_URL = `http://127.0.0.1:${PORT}`;

function resolvePython() {
  const winVenv = path.join(process.cwd(), ".venv", "Scripts", "python.exe");
  const posixVenv = path.join(process.cwd(), ".venv", "bin", "python");
  if (fs.existsSync(winVenv)) return winVenv;
  if (fs.existsSync(posixVenv)) return posixVenv;
  return process.platform === "win32" ? "python" : "python3";
}

module.exports = defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  workers: 4,
  timeout: 45000,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    locale: "de-DE",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    {
      name: "webkit-iphone",
      use: { ...devices["iPhone SE"] },
      testMatch: [/responsive-guard-webkit\.spec\.js/, /file-viewer\.spec\.js/],
    },
  ],
  webServer: {
    command: `"${resolvePython()}" -m uvicorn tests.e2e_fixture_app:app --host 127.0.0.1 --port ${PORT}`,
    cwd: "./backend",
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
    env: { ISERV_E2E_DATA_DIR: path.join(process.cwd(), "data-e2e") },
  },
});
