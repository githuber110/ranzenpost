import fs from "node:fs";
import path from "node:path";
import { describe, expect, test } from "vitest";
import {
  FRONTEND,
  MARKUP_SUFFIXES,
  SCRIPT_SUFFIXES,
  STYLE_SUFFIXES,
  TEST_TREE_PATHS,
  VENDOR_EXEMPT_PATHS,
  isShipped,
  scriptNames,
} from "./shippedSources.js";

const backendSources = fs.readFileSync(path.join(FRONTEND, "..", "backend", "tests", "frontend_sources.py"), "utf8");

function pythonTuple(name) {
  const match = new RegExp(`^${name} = \\(([^)]*)\\)`, "m").exec(backendSources);
  if (!match) throw new Error(`${name} is missing from frontend_sources.py`);
  return [...match[1].matchAll(/"([^"]*)"/g)].map((item) => item[1]);
}

describe("the frontend source list matches the backend one", () => {
  test("both sides exempt the same folders", () => {
    expect(VENDOR_EXEMPT_PATHS.map((name) => `frontend/${name}`)).toEqual(pythonTuple("VENDOR_EXEMPT_PATHS"));
    expect(TEST_TREE_PATHS.map((name) => `frontend/${name}`)).toEqual(pythonTuple("TEST_TREE_PATHS"));
  });

  test("both sides guard the same suffixes", () => {
    expect(SCRIPT_SUFFIXES).toEqual(pythonTuple("SCRIPT_SUFFIXES"));
    expect(STYLE_SUFFIXES).toEqual(pythonTuple("STYLE_SUFFIXES"));
    expect(MARKUP_SUFFIXES).toEqual(pythonTuple("MARKUP_SUFFIXES"));
  });

  test("the walk reaches nested folders and leaves the exempt ones out", () => {
    expect(scriptNames()).toEqual(expect.arrayContaining(["app.js", "lib/i18n.js", "lib/globals.js"]));
    expect(scriptNames().filter((name) => !isShipped(name))).toEqual([]);
    expect(isShipped("vendor/pdfjs/pdf.mjs")).toBe(false);
    expect(isShipped("tests/loadApp.js")).toBe(false);
    expect(isShipped("vendored.js")).toBe(true);
  });
});
