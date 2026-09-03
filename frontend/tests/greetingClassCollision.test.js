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

describe("[P145] Begruessung: Klassenkonflikt behoben, Vorname wieder sichtbar", () => {
  test("the greeting headline no longer shares its class with the unrelated .card.hero modifier", () => {
    const css = fs.readFileSync(path.resolve(dirname, "..", "styles.css"), "utf8");

    expect(css).toMatch(/\.card\.hero\s*\{/);
    expect(css).not.toMatch(/\.card\.greeting\b/);

    const greetingSelectorMatches = css.match(/\.greeting\s*\{/g) || [];
    expect(greetingSelectorMatches).toHaveLength(1);
  });

  test("the rendered greeting carries the renamed class and the full first name text, not just an inert DOM fragment", () => {
    const { window } = loadApp();
    const { html, className } = renderGreetingHeadline(window, "Alex", "2026-09-01T08:00:00");

    expect(className).toBe("greeting");
    expect(className).not.toBe("hero");

    const doc = new window.DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
    const nameSpan = doc.querySelector(".greeting-name");
    expect(nameSpan).not.toBeNull();
    expect(nameSpan.textContent).toBe("Alex");
    expect(doc.querySelector("h1").textContent).toContain("Alex");
  });
});
