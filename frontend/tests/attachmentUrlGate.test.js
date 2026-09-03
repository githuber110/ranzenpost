import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function mockBlobResponse(window, { ok = true, disposition = "", type = "" } = {}) {
  window.URL.createObjectURL = () => "blob:mock-url";
  window.URL.revokeObjectURL = () => {};
  const headers = { get: (name) => (name.toLowerCase() === "content-disposition" ? disposition : null) };
  window.fetch = () =>
    Promise.resolve({
      ok,
      status: ok ? 200 : 401,
      headers,
      blob: () => Promise.resolve(new window.Blob(["x"], type ? { type } : undefined)),
    });
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
  window.document.body.append(rows);
  rows.querySelector(".row").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  return rows.querySelector(".row");
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
    const requestedUrls = [];
    window.URL.createObjectURL = () => "blob:mock-url";
    window.URL.revokeObjectURL = () => {};
    window.fetch = (url) => {
      requestedUrls.push(url);
      return Promise.resolve({
        ok: true,
        headers: { get: () => "" },
        blob: () => Promise.resolve(new window.Blob(["x"])),
      });
    };
    tapAttachment(window, { filename: "Stundenplan.docx", url: "api/letters/attachment/x" });
    await settle(window, 2);
    expect(requestedUrls).toContain("http://localhost/api/letters/attachment/x");
  });

  test("a non-ok response shows an error toast instead of failing silently", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { ok: false });
    tapAttachment(window, { filename: "Elternbrief.pdf", url: "api/letters/attachment/x" });
    await settle(window, 6);
    expect(window.eval("state.toast && state.toast.kind")).toBe("bad");
  });

  test("a successful download frees the object URL again", async () => {
    const { window } = loadApp();
    mockBlobResponse(window);
    trackDownloads(window);
    let revoked = "";
    window.URL.revokeObjectURL = (url) => { revoked = url; };
    tapAttachment(window, { filename: "Stundenplan.docx", url: "api/letters/attachment/x" });
    await settle(window, 6);
    await new Promise((resolve) => window.setTimeout(resolve, 4100));
    expect(revoked).toBe("blob:mock-url");
  });
});

describe("[P197] an in-app overlay opens for images and PDFs, everything else downloads", () => {
  test("an image opens in the overlay as an <img>, no download happens", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "image/jpeg" });
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "Klassenfoto.JPG", url: "api/pinboard/attachment/x" });
    await settle(window);
    const img = window.document.querySelector(".viewer-overlay .viewer-img");
    expect(img).toBeTruthy();
    expect(img.getAttribute("src")).toBe("blob:mock-url");
    expect(downloads).toEqual([]);
  });

  test("an image is recognised through its extension even when the server hides the type", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "application/octet-stream" });
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "Klassenfoto.JPG", url: "api/pinboard/attachment/x" });
    await settle(window);
    expect(window.document.querySelector(".viewer-overlay .viewer-img")).toBeTruthy();
    expect(downloads).toEqual([]);
  });

  test("a docx is never shown in the overlay, it is downloaded as before", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "Anmeldung.docx", url: "api/letters/attachment/x" });
    await settle(window);
    expect(window.document.querySelector(".viewer-overlay")).toBeNull();
    expect(downloads).toEqual([{ href: "blob:mock-url", download: "Anmeldung.docx" }]);
  });

  test("a viewable name that turns out to be something else is never shown, it downloads under its real name", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "text/html", disposition: 'attachment; filename="tricky.html"' });
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "tricky.pdf", url: "api/letters/attachment/x" });
    await settle(window);
    expect(window.document.querySelector(".viewer-overlay")).toBeNull();
    expect(downloads).toEqual([{ href: "blob:mock-url", download: "tricky.html" }]);
  });

  test("a failed request never opens an overlay and says so", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { ok: false });
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "Elternbrief.pdf", url: "api/letters/attachment/x" });
    await settle(window);
    expect(window.document.querySelector(".viewer-overlay")).toBeNull();
    expect(downloads).toEqual([]);
    expect(window.eval("state.toast && state.toast.kind")).toBe("bad");
  });

  test("the sick note pdf and the attachments share the one opener", async () => {
    const { window } = loadApp();
    const source = window.eval("String(sickNotePdfBlock)");
    expect(source).toContain("openAppFile");
    expect(window.eval("String(attachmentButton)")).toContain("openAppFile");
  });
});

describe("[P197] the pdf overlay renders inline, but falls back to a download on failure", () => {
  test("a pdf that loads a real document stays in the overlay and is never downloaded", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "application/pdf" });
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "Elternbrief.pdf", url: "api/letters/attachment/x" });
    await settle(window);
    const frame = window.document.querySelector(".viewer-overlay .viewer-pdf");
    expect(frame).toBeTruthy();
    expect(frame.getAttribute("src")).toBe("blob:mock-url");
    window.pdfFrameIsEmpty = () => false;
    frame.dispatchEvent(new window.Event("load"));
    await new Promise((resolve) => window.setTimeout(resolve, 400));
    expect(window.document.querySelector(".viewer-overlay .viewer-pdf")).toBeTruthy();
    expect(downloads).toEqual([]);
  });

  test("a pdf whose document stays empty after load falls back to a download and a friendly toast", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "application/pdf" });
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "Elternbrief.pdf", url: "api/letters/attachment/x" });
    await settle(window);
    const frame = window.document.querySelector(".viewer-overlay .viewer-pdf");
    expect(frame).toBeTruthy();
    window.pdfFrameIsEmpty = () => true;
    frame.dispatchEvent(new window.Event("load"));
    await new Promise((resolve) => window.setTimeout(resolve, 400));
    expect(window.document.querySelector(".viewer-overlay")).toBeNull();
    expect(downloads).toEqual([{ href: "blob:mock-url", download: "Elternbrief.pdf" }]);
    expect(window.eval("state.toast && state.toast.kind")).toBe("good");
  });

  test("a pdf that never fires a load event within the timeout falls back to a download", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "application/pdf" });
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "Elternbrief.pdf", url: "api/letters/attachment/x" });
    await settle(window);
    expect(window.document.querySelector(".viewer-overlay .viewer-pdf")).toBeTruthy();
    await new Promise((resolve) => window.setTimeout(resolve, 5300));
    expect(window.document.querySelector(".viewer-overlay")).toBeNull();
    expect(downloads).toEqual([{ href: "blob:mock-url", download: "Elternbrief.pdf" }]);
  }, 8000);
});

describe("[P197] the overlay closes cleanly and gives focus back", () => {
  test("clicking the close button frees the object URL and returns focus to the trigger", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "image/png" });
    let revoked = "";
    window.URL.revokeObjectURL = (url) => { revoked = url; };
    const button = tapAttachment(window, { filename: "Klassenfoto.png", url: "api/pinboard/attachment/x" });
    await settle(window);
    const close = window.document.querySelector(".viewer-close");
    expect(close).toBeTruthy();
    close.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    expect(window.document.querySelector(".viewer-overlay")).toBeNull();
    expect(revoked).toBe("blob:mock-url");
    expect(window.document.activeElement).toBe(button);
  });

  test("pressing Escape inside the overlay closes it too", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "image/png" });
    tapAttachment(window, { filename: "Klassenfoto.png", url: "api/pinboard/attachment/x" });
    await settle(window);
    const overlay = window.document.querySelector(".viewer-overlay");
    expect(overlay).toBeTruthy();
    overlay.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(window.document.querySelector(".viewer-overlay")).toBeNull();
  });

  test("the overlay carries aria-modal and an aria-label with the filename", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "image/png" });
    tapAttachment(window, { filename: "Klassenfoto.png", url: "api/pinboard/attachment/x" });
    await settle(window);
    const overlay = window.document.querySelector(".viewer-overlay");
    expect(overlay.getAttribute("role")).toBe("dialog");
    expect(overlay.getAttribute("aria-modal")).toBe("true");
    expect(overlay.getAttribute("aria-label")).toBe("Klassenfoto.png");
  });

  test("Tab inside the overlay keeps focus trapped on the only focusable control", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, { type: "image/png" });
    tapAttachment(window, { filename: "Klassenfoto.png", url: "api/pinboard/attachment/x" });
    await settle(window);
    const overlay = window.document.querySelector(".viewer-overlay");
    const close = window.document.querySelector(".viewer-close");
    close.blur();
    overlay.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true }));
    expect(window.document.activeElement).toBe(close);
  });
});

describe("[P150/P191] structural tripwire: no target=_blank on our own api paths, no window bypass", () => {
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

  test("[P197] the old 401-window path is gone for good: window.open is never called from app.js", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const dirname = path.dirname(fileURLToPath(import.meta.url));
    const source = fs.readFileSync(path.join(dirname, "..", "app.js"), "utf8");
    expect(source.includes("window.open(")).toBe(false);
    expect(source.includes(".location.replace(")).toBe(false);
  });

  test("[P197] blob: urls only ever come from our own fetch response, never from a remote src", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const dirname = path.dirname(fileURLToPath(import.meta.url));
    const source = fs.readFileSync(path.join(dirname, "..", "app.js"), "utf8");
    expect(source).toContain("URL.createObjectURL(blob)");
    expect(source).not.toMatch(/src:\s*["'`]https?:/);
  });
});
