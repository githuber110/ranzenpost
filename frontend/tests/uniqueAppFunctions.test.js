import { describe, expect, test } from "vitest";
import { appSources } from "./shippedSources.js";

const DECLARATION = /^(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(/gm;

export function repeatedFunctions(sources) {
  const seen = new Map();
  const repeated = [];
  for (const { name, source } of sources) {
    for (const match of source.matchAll(DECLARATION)) {
      const where = seen.get(match[1]);
      if (where) repeated.push(`${match[1]} (${where}, ${name})`);
      else seen.set(match[1], name);
    }
  }
  return repeated;
}

describe("the app scripts share one global scope", () => {
  test("no top-level function is declared twice, because the later one would silently win", () => {
    expect(repeatedFunctions(appSources())).toEqual([]);
  });

  test("the scanner names a second declaration across files and inside one file", () => {
    const sources = [
      { name: "a.js", source: "function one() {}\nasync function two() {}\n" },
      { name: "b.js", source: "function one() {}\n  function nested() {}\nfunction three() {}\nfunction three() {}\n" },
    ];
    expect(repeatedFunctions(sources)).toEqual(["one (a.js, b.js)", "three (b.js, b.js)"]);
  });
});
