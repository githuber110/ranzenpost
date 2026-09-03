import { describe, expect, test } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));

function renderGreetingHeadline(window, forename, fixedIso) {
  const run = window.eval(`
    (function (forename, fixedIso) {
      state.me = { forename };
      const headline = greetingHeadline(new Date(fixedIso));
      return { html: headline.outerHTML, className: headline.className };
    })
  `);
  return run(forename, fixedIso);
}

describe("[P135] greeting headline stays calm and never overflows for long first names", () => {
  test("styles.css caps the headline at two lines and applies overflow-wrap to the name only", () => {
    const css = fs.readFileSync(path.resolve(dirname, "..", "styles.css"), "utf8");
    const greetingBlock = /\.greeting\s*\{[^}]*\}/.exec(css)[0];
    const greetingNameBlock = /\.greeting-name\s*\{[^}]*\}/.exec(css)[0];
    expect(greetingBlock).toMatch(/-webkit-line-clamp:\s*2/);
    expect(greetingBlock).toMatch(/font-size:\s*clamp\(/);
    expect(greetingNameBlock).toMatch(/overflow-wrap:\s*anywhere/);
    expect(greetingBlock).not.toMatch(/overflow-wrap/);
  });

  test("an extremely long, spaceless name gets truncated with a title attribute carrying the full name", () => {
    const { window } = loadApp();
    const longName = "A".repeat(120);
    const { html, className } = renderGreetingHeadline(window, longName, "2026-09-01T08:00:00");

    expect(className).toBe("greeting");
    const doc = new window.DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
    const nameSpan = doc.querySelector(".greeting-name");

    expect(nameSpan).not.toBeNull();
    expect(nameSpan.getAttribute("title")).toBe(longName);
    expect(nameSpan.textContent.length).toBeLessThan(longName.length);
    expect(nameSpan.textContent.endsWith("…")).toBe(true);
  });

  test("a short name is shown in full without truncation or a title attribute", () => {
    const { window } = loadApp();
    const { html } = renderGreetingHeadline(window, "Mira", "2026-09-01T08:00:00");
    const doc = new window.DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
    const nameSpan = doc.querySelector(".greeting-name");

    expect(nameSpan.textContent).toBe("Mira");
    expect(nameSpan.hasAttribute("title")).toBe(false);
  });
});
