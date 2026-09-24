import path from "node:path";
import { describe, expect, it } from "vitest";
import { readShipped, scriptNames } from "./shippedSources.js";

const indexHtml = readShipped("index.html");

const IMPORT_FROM = /\b(?:import|export)\s+(?:[\w$*{}\s,]+?\s+from\s+)?["']([^"'\n]+)["']/g;
const DYNAMIC_IMPORT = /\bimport\(\s*["']([^"'\n]+)["']\s*\)/g;

function importSpecifiers(source) {
  return [...source.matchAll(IMPORT_FROM), ...source.matchAll(DYNAMIC_IMPORT)]
    .sort((left, right) => left.index - right.index)
    .map((match) => match[1]);
}

function isRelative(specifier) {
  return specifier.startsWith("./") || specifier.startsWith("../");
}

function resolveSpecifier(fromName, specifier) {
  return path.posix.normalize(path.posix.join(path.posix.dirname(fromName), specifier));
}

function pageScripts(html) {
  return [...html.matchAll(/<script\b[^>]*\bsrc="\.\/([\w./-]+\.m?js)\?v=\d+"/g)].map((match) => match[1]);
}

function importGraph() {
  const shipped = new Set(scriptNames());
  const edges = [];
  for (const name of shipped) {
    for (const specifier of importSpecifiers(readShipped(name))) {
      edges.push({ from: name, specifier, target: isRelative(specifier) ? resolveSpecifier(name, specifier) : null });
    }
  }
  return { shipped, edges };
}

function reachableFromPage() {
  const { edges } = importGraph();
  const reached = new Set(pageScripts(indexHtml));
  const queue = [...reached];
  while (queue.length) {
    const name = queue.shift();
    for (const edge of edges) {
      if (edge.from !== name || !edge.target || reached.has(edge.target)) continue;
      reached.add(edge.target);
      queue.push(edge.target);
    }
  }
  return reached;
}

describe("asset versions in the page", () => {
  it("every local script and stylesheet carries the same version, so an update never mixes old and new code", () => {
    const local = [...indexHtml.matchAll(/(?:src|href)="\.\/([\w./-]+\.(?:js|css))(\?v=(\d+))?"/g)];
    expect(local.length).toBeGreaterThan(5);
    const missing = local.filter((match) => !match[3]).map((match) => match[1]);
    expect(missing).toEqual([]);
    expect(new Set(local.map((match) => match[3])).size).toBe(1);
  });

  it("every shipped script, in any folder, is loaded by the page with that version or imported by a script it loads", () => {
    const reached = reachableFromPage();
    expect(scriptNames().length).toBeGreaterThan(5);
    expect(scriptNames().filter((name) => !reached.has(name))).toEqual([]);
  });

  it("every relative import points at a shipped script that exists", () => {
    const { shipped, edges } = importGraph();
    const broken = edges.filter((edge) => edge.target && !shipped.has(edge.target));
    expect(broken.map((edge) => `${edge.from}: ${edge.specifier}`)).toEqual([]);
  });

  it("imports stay relative, so they resolve below the ingress path", () => {
    const { edges } = importGraph();
    expect(edges.filter((edge) => !edge.target).map((edge) => `${edge.from}: ${edge.specifier}`)).toEqual([]);
  });

  it("a relative import carries no query string, so a module is never loaded twice", () => {
    const { edges } = importGraph();
    const offenders = edges.filter((edge) => /[?#]/.test(edge.specifier));
    expect(offenders.map((edge) => `${edge.from}: ${edge.specifier}`)).toEqual([]);
  });

  it("a script the page loads with the version is never imported again without it", () => {
    const loaded = new Set(pageScripts(indexHtml));
    const { edges } = importGraph();
    expect(edges.filter((edge) => loaded.has(edge.target)).map((edge) => `${edge.from}: ${edge.specifier}`)).toEqual([]);
  });

  it("the import scanner sees every shape of an import", () => {
    const source = [
      'import { a, b as c } from "./lib/a.js";',
      "import * as d from '../d.js';",
      'import "./e.js";',
      "import {",
      "  f,",
      '} from "./lib/f.js";',
      'export { g } from "./g.js?v=3";',
      'export * from "./h.js";',
      'const i = await import("./i.js");',
      'export const j = "k";',
      "export function l() {}",
    ].join("\n");
    expect(importSpecifiers(source)).toEqual([
      "./lib/a.js",
      "../d.js",
      "./e.js",
      "./lib/f.js",
      "./g.js?v=3",
      "./h.js",
      "./i.js",
    ]);
    expect(resolveSpecifier("lib/globals.js", "./i18n.js")).toBe("lib/i18n.js");
    expect(resolveSpecifier("lib/deep/x.js", "../../app.js")).toBe("app.js");
    expect(pageScripts('<script type="module" src="./lib/globals.js?v=7"></script>')).toEqual(["lib/globals.js"]);
  });
});
