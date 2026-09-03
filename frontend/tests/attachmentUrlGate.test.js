import { describe, expect, test, vi } from "vitest";
import { loadApp } from "./loadApp.js";

function mockBlobResponse(window, { ok = true, disposition = "" } = {}) {
  window.URL.createObjectURL = vi.fn(() => "blob:mock-url");
  window.URL.revokeObjectURL = vi.fn();
  const headers = { get: (name) => (name.toLowerCase() === "content-disposition" ? disposition : null) };
  window.fetch = vi.fn(() =>
    Promise.resolve({ ok, status: ok ? 200 : 401, headers, blob: () => Promise.resolve(new window.Blob(["x"])) })
  );
  return window.fetch;
}

describe("[P111-B8] attachmentRows never renders a clickable link for an empty url", () => {
  test("a file with a url renders a button, not a same-tab-breaking link", () => {
    const { window } = loadApp();
    const rows = window.eval(`attachmentRows([{ filename: "Elternbrief.pdf", url: "api/letters/attachment/x" }])`);
    const row = rows.querySelector(".row");
    expect(row.tagName).toBe("BUTTON");
    expect(row.hasAttribute("href")).toBe(false);
    expect(row.hasAttribute("target")).toBe(false);
  });

  test("a file with an empty url (rejected filename) renders a non-link, disabled row", () => {
    const { window } = loadApp();
    const rows = window.eval(`attachmentRows([{ filename: "../evil", url: "" }])`);
    const row = rows.querySelector(".row");
    expect(row.tagName).toBe("DIV");
    expect(row.hasAttribute("href")).toBe(false);
    expect(row.classList.contains("disabled")).toBe(true);
  });
});

describe("[P150] attachment click fetches in the current document context", () => {
  test("clicking triggers fetch on the relative api path, not a new-tab navigation", async () => {
    const { window } = loadApp();
    const fetchMock = mockBlobResponse(window);
    const rows = window.eval(`attachmentRows([{ filename: "Elternbrief.pdf", url: "api/letters/attachment/x" }])`);
    rows.querySelector(".row").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(fetchMock).toHaveBeenCalledWith("http://localhost/api/letters/attachment/x");
  });

  test("a non-ok response shows an error toast instead of failing silently", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { ok: false });
    const rows = window.eval(`attachmentRows([{ filename: "Elternbrief.pdf", url: "api/letters/attachment/x" }])`);
    rows.querySelector(".row").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    for (let tick = 0; tick < 6; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(window.eval("state.toast && state.toast.kind")).toBe("bad");
  });

  test("a successful download frees the object URL again", async () => {
    const { window } = loadApp();
    mockBlobResponse(window);
    const rows = window.eval(`attachmentRows([{ filename: "Elternbrief.pdf", url: "api/letters/attachment/x" }])`);
    rows.querySelector(".row").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    for (let tick = 0; tick < 6; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(window.URL.createObjectURL).toHaveBeenCalledTimes(1);
    await new Promise((resolve) => window.setTimeout(resolve, 4100));
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
  });
});

describe("[P150] structural tripwire: no target=_blank on our own api paths", () => {
  test("app.js never opens a relative api/... path in a new top-level tab", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const dirname = path.dirname(fileURLToPath(import.meta.url));
    const source = fs.readFileSync(path.join(dirname, "..", "app.js"), "utf8");
    const attrBlocks = source.match(/\{[^{}]*target:\s*"_blank"[^{}]*\}/g) || [];
    expect(attrBlocks.length).toBeGreaterThan(0);
    for (const block of attrBlocks) {
      expect(block.includes('href: "api' + "/")).toBe(false);
      expect(block.includes("href: `api" + "/")).toBe(false);
    }
  });
});
