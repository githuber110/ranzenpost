import { describe, expect, test, vi } from "vitest";
import { loadApp } from "./loadApp.js";

function mockBlobResponse(window, { ok = true, disposition = "", type = "" } = {}) {
  window.URL.createObjectURL = vi.fn(() => "blob:mock-url");
  window.URL.revokeObjectURL = vi.fn();
  const headers = { get: (name) => (name.toLowerCase() === "content-disposition" ? disposition : null) };
  window.fetch = vi.fn(() =>
    Promise.resolve({
      ok,
      status: ok ? 200 : 401,
      headers,
      blob: () => Promise.resolve(new window.Blob(["x"], type ? { type } : undefined)),
    })
  );
  return window.fetch;
}

function trackWindows(window, { blocked = false } = {}) {
  const opened = [];
  window.open = vi.fn((url, target) => {
    if (blocked) return null;
    const viewer = {
      url,
      target,
      closed: false,
      navigated: "",
      location: { replace: (next) => { viewer.navigated = next; } },
      close: () => { viewer.closed = true; },
    };
    opened.push(viewer);
    return viewer;
  });
  return opened;
}

function trackDownloads(window) {
  const downloads = [];
  window.HTMLAnchorElement.prototype.click = function click() {
    downloads.push({ href: this.getAttribute("href"), download: this.getAttribute("download") });
  };
  return downloads;
}

function tapAttachment(window, file) {
  const rows = window.eval(`attachmentRows([${JSON.stringify(file)}])`);
  rows.querySelector(".row").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
}

async function settle(window, ticks = 8) {
  for (let tick = 0; tick < ticks; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
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
    trackWindows(window);
    tapAttachment(window, { filename: "Elternbrief.pdf", url: "api/letters/attachment/x" });
    await settle(window, 2);
    expect(fetchMock).toHaveBeenCalledWith("http://localhost/api/letters/attachment/x");
  });

  test("a non-ok response shows an error toast instead of failing silently", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { ok: false });
    trackWindows(window);
    tapAttachment(window, { filename: "Elternbrief.pdf", url: "api/letters/attachment/x" });
    await settle(window, 6);
    expect(window.eval("state.toast && state.toast.kind")).toBe("bad");
  });

  test("a successful download frees the object URL again", async () => {
    const { window } = loadApp();
    mockBlobResponse(window);
    trackWindows(window);
    trackDownloads(window);
    tapAttachment(window, { filename: "Stundenplan.docx", url: "api/letters/attachment/x" });
    await settle(window, 6);
    expect(window.URL.createObjectURL).toHaveBeenCalledTimes(1);
    await new Promise((resolve) => window.setTimeout(resolve, 4100));
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
  });
});

describe("[P191] a tap on an attachment opens it, and only falls back to downloading", () => {
  test("a pdf lands in a viewer window that was reserved inside the click itself", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "application/pdf" });
    const opened = trackWindows(window);
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "Elternbrief.pdf", url: "api/letters/attachment/x" });
    expect(opened.length).toBe(1);
    expect(opened[0].url).toBe("");
    expect(opened[0].target).toBe("_blank");
    await settle(window);
    expect(opened[0].navigated).toBe("blob:mock-url");
    expect(opened[0].closed).toBe(false);
    expect(downloads).toEqual([]);
  });

  test("an image opens the same way, even when the server hides the type", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "application/octet-stream" });
    const opened = trackWindows(window);
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "Klassenfoto.JPG", url: "api/pinboard/attachment/x" });
    await settle(window);
    expect(opened[0].navigated).toBe("blob:mock-url");
    expect(downloads).toEqual([]);
  });

  test("a docx is never shown in a window, it is downloaded as before", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    const opened = trackWindows(window);
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "Anmeldung.docx", url: "api/letters/attachment/x" });
    await settle(window);
    expect(opened).toEqual([]);
    expect(downloads).toEqual([{ href: "blob:mock-url", download: "Anmeldung.docx" }]);
  });

  test("a viewable name that turns out to be something else closes the window and downloads", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "text/html", disposition: 'attachment; filename="tricky.html"' });
    const opened = trackWindows(window);
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "tricky.pdf", url: "api/letters/attachment/x" });
    await settle(window);
    expect(opened[0].navigated).toBe("");
    expect(opened[0].closed).toBe(true);
    expect(downloads).toEqual([{ href: "blob:mock-url", download: "tricky.html" }]);
  });

  test("a suppressed popup is a dead end for nobody: the download takes over", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "application/pdf" });
    trackWindows(window, { blocked: true });
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "Elternbrief.pdf", url: "api/letters/attachment/x" });
    await settle(window);
    expect(downloads).toEqual([{ href: "blob:mock-url", download: "Elternbrief.pdf" }]);
  });

  test("a failed request closes the reserved window and says so", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { ok: false });
    const opened = trackWindows(window);
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "Elternbrief.pdf", url: "api/letters/attachment/x" });
    await settle(window);
    expect(opened[0].closed).toBe(true);
    expect(downloads).toEqual([]);
    expect(window.eval("state.toast && state.toast.kind")).toBe("bad");
  });

  test("an opened blob url is freed later than a downloaded one, never right away", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "application/pdf" });
    trackWindows(window);
    tapAttachment(window, { filename: "Elternbrief.pdf", url: "api/letters/attachment/x" });
    await settle(window);
    await new Promise((resolve) => window.setTimeout(resolve, 4100));
    expect(window.URL.revokeObjectURL).not.toHaveBeenCalled();
  });

  test("the sick note pdf and the attachments share the one opener", async () => {
    const { window } = loadApp();
    const source = window.eval("String(sickNotePdfBlock)");
    expect(source).toContain("openAppFile");
    expect(window.eval("String(attachmentButton)")).toContain("openAppFile");
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

  test("[P191] no window is ever opened on an api path, only on a blank tab we fill ourselves", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const dirname = path.dirname(fileURLToPath(import.meta.url));
    const source = fs.readFileSync(path.join(dirname, "..", "app.js"), "utf8");
    const calls = source.match(/window\.open\(([^)]*)\)/g) || [];
    expect(calls.length).toBeGreaterThan(0);
    for (const call of calls) expect(call).toBe('window.open("", "_blank")');
    const navigations = source.match(/\.location\.replace\(([^)]*)\)/g) || [];
    expect(navigations.length).toBeGreaterThan(0);
    for (const navigation of navigations) expect(navigation).toBe(".location.replace(objectUrl)");
  });
});
