import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync, rmSync } from "node:fs";

const TEST_DIR = "frontend/tests";
const SUFFIX = ".test.js";
const REPORT = "./.vitest-run.json";

function onDisk() {
  return readdirSync(TEST_DIR).filter((name) => name.endsWith(SUFFIX)).sort();
}

const expected = onDisk();
rmSync(REPORT, { force: true });

const run = spawnSync(
  process.execPath,
  [
    "node_modules/vitest/vitest.mjs",
    "run",
    "--reporter=default",
    "--reporter=json",
    `--outputFile.json=${REPORT}`,
    ...process.argv.slice(2),
  ],
  { stdio: "inherit" }
);

let executed = [];
let readable = true;
try {
  const parsed = JSON.parse(readFileSync(REPORT, "utf8"));
  executed = (parsed.testResults || []).map((entry) => entry.name.split(/[\\/]/).pop()).sort();
} catch (error) {
  console.error(`\ncould not read the run report at ${REPORT}: ${error.message}`);
  readable = false;
} finally {
  rmSync(REPORT, { force: true });
}
if (!readable) process.exit(1);

const missing = expected.filter((name) => !executed.includes(name));
if (missing.length) {
  console.error(
    `\n${missing.length} of ${expected.length} test files never ran, and the run still called ` +
      `itself green:\n  ${missing.join("\n  ")}\n` +
      "A run that quietly leaves files out is worse than a failing one, so this counts as a failure."
  );
  process.exit(1);
}

if (run.status !== 0) process.exit(run.status ?? 1);
console.log(`\nall ${expected.length} test files ran.`);
