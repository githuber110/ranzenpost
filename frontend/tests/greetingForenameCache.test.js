import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function jsonResponse(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

function baseFetch(mePromise) {
  return (path) => {
    const p = String(path);
    if (p.includes("api/health")) return jsonResponse({ configured: true, connection: "ok" });
    if (p.includes("api/config")) return jsonResponse({});
    if (p.includes("api/children")) return jsonResponse([]);
    if (p.includes("api/timetable-availability")) return jsonResponse({ available: true });
    if (p.includes("api/me")) return mePromise;
    return jsonResponse({});
  };
}

describe("[P145] Begruessung: Vorname aus Cache, kein Nachflackern", () => {
  test("cached forename is already in the first render, before /api/me responds", async () => {
    const { window, document } = loadApp();
    window.localStorage.setItem("meForename", "Alex");
    const mePromise = new Promise(() => {});
    window.fetch = baseFetch(mePromise);

    await window.eval("boot()");

    const app = document.getElementById("app");
    const nameSpan = app.querySelector(".greeting-name");
    expect(nameSpan).not.toBeNull();
    expect(nameSpan.textContent).toBe("Alex");
  });

  test("without a cache, the greeting starts without a name and updates once /api/me resolves", async () => {
    const { window, document } = loadApp();
    let resolveMe;
    const mePromise = new Promise((resolve) => { resolveMe = resolve; });
    window.fetch = baseFetch(mePromise);

    await window.eval("boot()");

    const app = document.getElementById("app");
    expect(app.querySelector(".greeting-name")).toBeNull();

    resolveMe(jsonResponse({ forename: "Mira" }));
    await flush();

    const nameSpan = app.querySelector(".greeting-name");
    expect(nameSpan).not.toBeNull();
    expect(nameSpan.textContent).toBe("Mira");
    expect(window.localStorage.getItem("meForename")).toBe("Mira");
  });

  test("a throwing localStorage does not crash rendering and still falls back to no-name-then-update", async () => {
    const { window, document } = loadApp();
    window.localStorage.getItem = () => { throw new Error("storage blocked"); };
    window.localStorage.setItem = () => { throw new Error("storage blocked"); };
    let resolveMe;
    const mePromise = new Promise((resolve) => { resolveMe = resolve; });
    window.fetch = baseFetch(mePromise);

    await window.eval("boot()");

    const app = document.getElementById("app");
    expect(app.querySelector(".greeting-name")).toBeNull();

    resolveMe(jsonResponse({ forename: "Mira" }));
    await flush();

    expect(app.querySelector(".greeting-name").textContent).toBe("Mira");
  });
});
