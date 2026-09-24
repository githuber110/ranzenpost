import { describe, expect, test } from "vitest";
import fs from "node:fs";
import path from "node:path";

const APP = fs.readFileSync(path.resolve(__dirname, "..", "app.js"), "utf8");
const FULL_PAGE_RENDERERS = ["renderWizard", "renderReconnect", "renderNotice"];

function callsOf(name) {
  const pattern = new RegExp(`(?<!function )\\b${name}\\(((?:[^,()]|\\(\\))*)`, "g");
  return [...APP.matchAll(pattern)].map((match) => ({
    line: APP.slice(0, match.index).split("\n").length,
    target: match[1].trim(),
  }));
}

describe("full page flows take over the app shell", () => {
  test.each(FULL_PAGE_RENDERERS)("%s always renders into the detached root", (name) => {
    const calls = callsOf(name);
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.filter((call) => call.target !== "detachedRoot()")).toEqual([]);
  });

  test("the app does not detach without resetting the shell", () => {
    const assignments = [...APP.matchAll(/state\.detached = true;/g)];
    expect(assignments).toHaveLength(1);
    const helper = APP.match(/function detachedRoot\(\) \{([\s\S]*?)\n\}/);
    expect(helper && helper[1]).toContain('shellAttributes(app, "flow")');
  });
});
