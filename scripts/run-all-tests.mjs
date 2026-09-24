import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const windows = process.platform === "win32";
const venvPython = [path.join(root, ".venv", "Scripts", "python.exe"), path.join(root, ".venv", "bin", "python")].find(
  (candidate) => existsSync(candidate)
);

function homeAssistantStep() {
  const command = process.env.RANZENPOST_HA_TEST_COMMAND;
  if (command) return { name: "home assistant", command, args: [], shell: true };
  if (process.platform === "linux") {
    const python = process.env.RANZENPOST_HA_PYTHON || venvPython;
    return {
      name: "home assistant",
      command: python,
      args: ["-m", "pytest", "tests/components/ranzenpost", "-q", "-p", "no:cacheprovider"],
    };
  }
  return {
    name: "home assistant",
    missing: "runs only under Linux; set RANZENPOST_HA_TEST_COMMAND to a command that runs tests/components/ranzenpost there",
  };
}

function plan() {
  const backend = venvPython
    ? { name: "backend", command: venvPython, args: ["-m", "pytest", "-q"], cwd: "backend" }
    : { name: "backend", missing: "no .venv with python found in the repository root" };
  return [
    { name: "frontend", command: "npm", args: ["test"], shell: windows },
    { name: "card", command: "npm", args: ["run", "test:card"], shell: windows },
    backend,
    homeAssistantStep(),
    { name: "browser", command: "npx", args: ["playwright", "test"], shell: windows },
  ];
}

function run(step) {
  if (step.missing) return { name: step.name, result: "missing", note: step.missing };
  console.log(`\n=== ${step.name}: ${[step.command, ...step.args].join(" ")}`);
  const outcome = spawnSync(step.command, step.args, {
    cwd: step.cwd ? path.join(root, step.cwd) : root,
    stdio: "inherit",
    shell: Boolean(step.shell),
  });
  if (outcome.error) return { name: step.name, result: "failed", note: outcome.error.message };
  return { name: step.name, result: outcome.status === 0 ? "passed" : "failed", note: `exit ${outcome.status}` };
}

const steps = plan();
if (process.argv.includes("--list")) {
  for (const step of steps) console.log(step.missing ? `${step.name}: missing (${step.missing})` : `${step.name}: ${[step.command, ...step.args].join(" ")}`);
  process.exit(0);
}

const results = steps.map(run);
console.log("\n=== summary");
for (const entry of results) console.log(`${entry.result.padEnd(7)} ${entry.name}${entry.note ? ` (${entry.note})` : ""}`);
const complete = results.every((entry) => entry.result === "passed");
console.log(complete ? "\nall parts passed" : "\nnot complete: every part must pass, a missing part counts as a failure");
process.exit(complete ? 0 : 1);
