import { describe, expect, test } from "vitest";
import { readShipped } from "./shippedSources.js";

const indexHtml = readShipped("index.html");

function scriptTags(html) {
  return [...html.matchAll(/<script\b([^>]*)><\/script>/g)].map((match) => {
    const attributes = match[1];
    const src = /\bsrc="\.\/([\w./-]+)\?v=\d+"/.exec(attributes);
    return {
      name: src ? src[1] : "",
      defer: /\sdefer\b/.test(attributes),
      async: /\sasync\b/.test(attributes),
      module: /\stype="module"/.test(attributes),
    };
  });
}

function section(html, tag) {
  const match = new RegExp(`<${tag}>([\\s\\S]*?)</${tag}>`).exec(html);
  return match ? match[1] : "";
}

const headScripts = scriptTags(section(indexHtml, "head"));
const bodyScripts = scriptTags(section(indexHtml, "body"));

describe("the page loads its scripts in a fixed order", () => {
  test("the direction script runs synchronously in the head, before the first paint", () => {
    expect(headScripts).toEqual([{ name: "bootdir.js", defer: false, async: false, module: false }]);
  });

  test("the body scripts keep their order and app.js comes last", () => {
    expect(bodyScripts.map((script) => script.name)).toEqual([
      "blocks.js",
      "periods.js",
      "steps.js",
      "wizard.js",
      "qr.js",
      "pdfviewer.js",
      "colour.js",
      "lib/globals.js",
      "app.js",
    ]);
  });

  test("the translation globals load as a module right before app.js", () => {
    const globals = bodyScripts.find((script) => script.name === "lib/globals.js");
    expect(globals).toEqual({ name: "lib/globals.js", defer: false, async: false, module: true });
    expect(bodyScripts.at(-2)).toBe(globals);
  });

  test("every body script is deferred, so modules and classic scripts run in one queue", () => {
    expect(bodyScripts.length).toBeGreaterThan(0);
    expect(bodyScripts.filter((script) => !script.defer && !script.module).map((script) => script.name)).toEqual([]);
  });

  test("no script is async, because an async script would leave the queue", () => {
    expect([...headScripts, ...bodyScripts].filter((script) => script.async).map((script) => script.name)).toEqual([]);
  });

  test("every script tag loads a local file", () => {
    expect([...headScripts, ...bodyScripts].filter((script) => !script.name)).toEqual([]);
  });
});
