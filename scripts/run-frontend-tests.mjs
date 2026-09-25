import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync, rmSync } from "node:fs";

const SUITES = {
  frontend: { dir: "frontend/tests", config: [] },
  card: { dir: "tests/card", config: ["--config", "vitest.card.config.mjs"] },
};
const SUITE_FLAG = "--suite=";
const suiteName = (process.argv.find((arg) => arg.startsWith(SUITE_FLAG)) || `${SUITE_FLAG}frontend`).slice(SUITE_FLAG.length);
const SUITE = SUITES[suiteName];
if (!SUITE) {
  console.error(`unknown suite "${suiteName}", expected one of: ${Object.keys(SUITES).join(", ")}`);
  process.exit(1);
}
const TEST_DIR = SUITE.dir;
const SUFFIX = ".test.js";
const REPORT = `./.vitest-run-${suiteName}.json`;
const MAX_ROUNDS = 3;

function onDisk() {
  return readdirSync(TEST_DIR).filter((name) => name.endsWith(SUFFIX)).sort();
}

function vitest(args) {
  rmSync(REPORT, { force: true });
  const run = spawnSync(
    process.execPath,
    [
      "node_modules/vitest/vitest.mjs",
      "run",
      ...SUITE.config,
      "--reporter=default",
      "--reporter=json",
      `--outputFile.json=${REPORT}`,
      ...args,
    ],
    { stdio: "inherit" }
  );
  let ran = null;
  let failed = 0;
  try {
    const parsed = JSON.parse(readFileSync(REPORT, "utf8"));
    ran = (parsed.testResults || []).map((entry) => entry.name.split(/[\\/]/).pop());
    failed = (parsed.numFailedTests || 0) + (parsed.numFailedTestSuites || 0);
  } catch (error) {
    console.error(`\ncould not read the run report at ${REPORT}: ${error.message}`);
    if (run.error) console.error(`the test runner did not start: ${run.error.message}`);
  } finally {
    rmSync(REPORT, { force: true });
  }
  return { status: run.status ?? 1, ran, failed };
}

const expected = onDisk();
const passthrough = process.argv.slice(2).filter((arg) => !arg.startsWith(SUITE_FLAG));
const done = new Set();
let status = 0;
let rounds = 0;

for (let round = 1; round <= MAX_ROUNDS; round += 1) {
  const outstanding = expected.filter((name) => !done.has(name));
  if (!outstanding.length) break;
  if (round > 1) {
    console.error(
      `\nthe runner left ${outstanding.length} file(s) out; running them again:\n  ` +
        outstanding.join("\n  ")
    );
  }
  rounds = round;
  const args = round === 1 ? passthrough : [...passthrough, ...outstanding.map((name) => `${TEST_DIR}/${name}`)];
  const result = vitest(args);
  if (result.ran === null) process.exit(1);
  for (const name of result.ran) done.add(name);
  const leftOut = outstanding.filter((name) => !done.has(name));
  if (result.failed > 0 || (result.status !== 0 && !leftOut.length)) {
    status = result.status || 1;
    break;
  }
  if (result.status !== 0) {
    console.error(`\nthe runner stopped with an error but no test failed; ${leftOut.length} file(s) did not run and get another round`);
  }
  status = 0;
}

const missing = expected.filter((name) => !done.has(name));
if (missing.length) {
  console.error(
    `\n${missing.length} of ${expected.length} test files never ran, after ${rounds} ` +
      `attempt(s)${status !== 0 ? " (the runner stopped with an error)" : ""}:\n  ${missing.join("\n  ")}`
  );
  process.exit(1);
}

if (status !== 0) process.exit(status);
console.log(`\nall ${expected.length} test files ran.`);
