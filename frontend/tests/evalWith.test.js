import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const testsDir = path.dirname(fileURLToPath(import.meta.url));
const JSON_IN_TEXT = [/\$\{\s*JSON\.stringify\(/, /\+\s*JSON\.stringify\(/, /JSON\.stringify\([^()]*\)\s*\+/];

describe("test code passes values to the app window as data", () => {
  test("no test builds code or text from JSON.stringify output", () => {
    const offenders = [];
    for (const name of fs.readdirSync(testsDir).filter((entry) => entry.endsWith(".js"))) {
      const lines = fs.readFileSync(path.join(testsDir, name), "utf8").split("\n");
      lines.forEach((line, index) => {
        if (JSON_IN_TEXT.some((pattern) => pattern.test(line))) offenders.push(`${name}:${index + 1}`);
      });
    }
    expect(offenders).toEqual([]);
  });

  test("values arrive as objects of the app window", () => {
    const { window } = loadApp();
    const copy = evalWith(window, "testArgs[0]", { list: [1, 2] });
    expect(copy.list instanceof window.Array).toBe(true);
    expect(evalWith(window, "testArgs[0] === undefined && testArgs[1] === null", undefined, null)).toBe(true);
  });

  test("a function made by one call keeps its own values after the next call", () => {
    const { window } = loadApp();
    const first = evalWith(window, "() => testArgs[0]", "first");
    evalWith(window, "testArgs[0]", "second");
    expect(first()).toBe("first");
    expect(window.testArgs).toBeUndefined();
  });

  test("the code still reaches the app's own global state", () => {
    const { window } = loadApp();
    evalWith(window, "state.view = testArgs[0]", "settings");
    expect(window.eval("state.view")).toBe("settings");
  });
});
