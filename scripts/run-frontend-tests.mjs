import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync, rmSync } from "node:fs";

const TEST_DIR = "frontend/tests";
const SUFFIX = ".test.js";
const REPORT = "./.vitest-run.json";
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
      "--reporter=default",
      "--reporter=json",
      `--outputFile.json=${REPORT}`,
      ...args,
    ],
    { stdio: "inherit" }
  );
  let ran = null;
  try {
    const parsed = JSON.parse(readFileSync(REPORT, "utf8"));
    ran = (parsed.testResults || []).map((entry) => entry.name.split(/[\\/]/).pop());
  } catch (error) {
    console.error(`\ncould not read the run report at ${REPORT}: ${error.message}`);
    if (run.error) console.error(`the test runner did not start: ${run.error.message}`);
  } finally {
    rmSync(REPORT, { force: true });
  }
  return { status: run.status ?? 1, ran };
}

const expected = onDisk();
const passthrough = process.argv.slice(2);
const done = new Set();
let status = 0;

for (let round = 1; round <= MAX_ROUNDS; round += 1) {
  const outstanding = expected.filter((name) => !done.has(name));
  if (!outstanding.length) break;
  if (round > 1) {
    console.error(
      `\nthe runner left ${outstanding.length} file(s) out; running them again:\n  ` +
        outstanding.join("\n  ")
    );
  }
  const args = round === 1 ? passthrough : [...passthrough, ...outstanding.map((name) => `${TEST_DIR}/${name}`)];
  const result = vitest(args);
  if (result.ran === null) process.exit(1);
  for (const name of result.ran) done.add(name);
  status = result.status;
  if (status !== 0) break;
}

const missing = expected.filter((name) => !done.has(name));
if (missing.length) {
  console.error(
    `\n${missing.length} of ${expected.length} test files never ran, even after ${MAX_ROUNDS} ` +
      `attempts:\n  ${missing.join("\n  ")}\n` +
      "A run that quietly leaves files out is worse than a failing one, so this counts as a failure."
  );
  process.exit(1);
}

if (status !== 0) process.exit(status);
console.log(`\nall ${expected.length} test files ran.`);
