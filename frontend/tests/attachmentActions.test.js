import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function mockBlobResponse(window, type = "application/pdf") {
  window.URL.createObjectURL = () => "blob:mock-url";
  window.URL.revokeObjectURL = () => {};
  window.fetch = () =>
    Promise.resolve({
      ok: true,
      status: 200,
      headers: { get: () => "" },
      blob: () => Promise.resolve(new window.Blob(["x"], { type })),
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

function choicePanel(window) {
  const factory = window.eval("state.sheet");
  return factory ? factory() : null;
}

async function settle(window, ticks = 8) {
  for (let tick = 0; tick < ticks; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
}

const FILE = { filename: "Elternbrief.pdf", url: "api/letters/attachment/x" };

describe("[P249] a tap on an attachment asks what to do with it", () => {
  test("the sheet offers open, save and print, titled with the file name", () => {
    const { window } = loadApp();
    tapAttachment(window, FILE);
    const panel = choicePanel(window);
    expect(panel).not.toBeNull();
    expect(panel.querySelector(".sheet-title").textContent).toBe("Elternbrief.pdf");
    const labels = Array.from(panel.querySelectorAll(".rows .row .row-title")).map((node) => node.textContent);
    expect(labels).toEqual([
      window.eval("t('attachment.action.open')"),
      window.eval("t('attachment.action.save')"),
      window.eval("t('attachment.action.print')"),
    ]);
  });

  test("open fetches the file on the relative api path and shows the viewer", async () => {
    const { window } = loadApp();
    const requested = [];
    window.URL.createObjectURL = () => "blob:mock-url";
    window.URL.revokeObjectURL = () => {};
    window.fetch = (url) => {
      requested.push(String(url));
      return Promise.resolve({
        ok: true,
        headers: { get: () => "" },
        blob: () => Promise.resolve(new window.Blob(["x"], { type: "image/jpeg" })),
      });
    };
    tapAttachment(window, { filename: "Foto.jpg", url: "api/pinboard/attachment/x" });
    choicePanel(window).querySelector(".attach-open").click();
    await settle(window);
    expect(requested).toContain("http://localhost/api/pinboard/attachment/x");
    expect(window.eval("state.sheet")).toBeNull();
    expect(window.eval("state.fileViewer && state.fileViewer.kind")).toBe("image");
  });

  test("save without a native picker falls back to a browser download under the file name", async () => {
    const { window } = loadApp();
    mockBlobResponse(window);
    const downloads = trackDownloads(window);
    tapAttachment(window, FILE);
    choicePanel(window).querySelector(".attach-save").click();
    await settle(window);
    expect(downloads).toEqual([{ href: "blob:mock-url", download: "Elternbrief.pdf" }]);
    expect(window.eval("state.fileViewer")).toBeNull();
  });

  test("save uses the native save dialog when the browser offers one", async () => {
    const { window } = loadApp();
    mockBlobResponse(window);
    const downloads = trackDownloads(window);
    const written = [];
    window.showSaveFilePicker = (options) => {
      written.push(options.suggestedName);
      return Promise.resolve({
        createWritable: () => Promise.resolve({ write: () => Promise.resolve(), close: () => Promise.resolve() }),
      });
    };
    tapAttachment(window, FILE);
    choicePanel(window).querySelector(".attach-save").click();
    await settle(window);
    expect(written).toEqual(["Elternbrief.pdf"]);
    expect(downloads).toEqual([]);
  });

  test("save on a touch device goes through the system share sheet", async () => {
    const { window } = loadApp();
    mockBlobResponse(window);
    const downloads = trackDownloads(window);
    window.matchMedia = (query) => ({ matches: query.includes("pointer: coarse"), addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} });
    const shared = [];
    window.navigator.canShare = () => true;
    window.navigator.share = (data) => {
      shared.push(data.files.map((file) => file.name));
      return Promise.resolve();
    };
    tapAttachment(window, FILE);
    choicePanel(window).querySelector(".attach-save").click();
    await settle(window);
    expect(shared).toEqual([["Elternbrief.pdf"]]);
    expect(downloads).toEqual([]);
  });

  test("print loads a pdf into a hidden frame and opens the print dialog from there", async () => {
    const { window } = loadApp();
    mockBlobResponse(window);
    const printed = [];
    const original = window.document.body.append.bind(window.document.body);
    window.document.body.append = (...nodes) => {
      for (const node of nodes) {
        if (node.tagName === "IFRAME") {
          Object.defineProperty(node, "contentWindow", { value: { focus() {}, print() { printed.push(node.getAttribute("src")); } } });
          Object.defineProperty(node, "contentDocument", { value: { querySelector: () => null } });
          original(node);
          node.dispatchEvent(new window.Event("load"));
          continue;
        }
        original(node);
      }
    };
    tapAttachment(window, FILE);
    choicePanel(window).querySelector(".attach-print").click();
    await settle(window);
    expect(printed).toEqual(["blob:mock-url"]);
    expect(window.document.querySelector(".print-frame")).not.toBeNull();
  });

  test("a file the browser cannot print is saved instead, and the user is told", async () => {
    const { window } = loadApp();
    mockBlobResponse(window, "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
    const downloads = trackDownloads(window);
    tapAttachment(window, { filename: "Liste.docx", url: "api/letters/attachment/x" });
    choicePanel(window).querySelector(".attach-print").click();
    await settle(window);
    expect(downloads).toEqual([{ href: "blob:mock-url", download: "Liste.docx" }]);
    expect(window.eval("state.toast && state.toast.message")).toBe(window.eval("t('attachment.print.unsupported')"));
  });
});

describe("[P249] the viewer carries save and print of its own", () => {
  function openViewer(window) {
    window.eval(`openFileViewer("image", "blob:mock-url", "Foto.jpg", null, new Blob(["x"], { type: "image/jpeg" }))`);
    return window.eval("(function () { return fileViewerNode(); })")();
  }

  test("save and print sit beside the close button, each a 44px round button", () => {
    const { window } = loadApp();
    window.URL.createObjectURL = () => "blob:mock-url";
    const overlay = openViewer(window);
    const actions = overlay.querySelector(".viewer-actions");
    expect(actions).not.toBeNull();
    const labels = Array.from(actions.querySelectorAll("button")).map((node) => node.getAttribute("aria-label"));
    expect(labels).toEqual([
      window.eval("t('attachment.action.save')"),
      window.eval("t('attachment.action.print')"),
      window.eval("t('common.close')"),
    ]);
  });

  test("a right click on the picture opens the app's own menu instead of the browser's image menu", () => {
    const { window } = loadApp();
    window.URL.createObjectURL = () => "blob:mock-url";
    const overlay = openViewer(window);
    window.document.body.append(overlay);
    const event = new window.MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 40, clientY: 50 });
    overlay.querySelector(".viewer-stage").dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    const menu = overlay.querySelector(".viewer-menu");
    expect(menu).not.toBeNull();
    const labels = Array.from(menu.querySelectorAll(".viewer-menu-item > span:last-child")).map((node) => node.textContent);
    expect(labels).toEqual([window.eval("t('attachment.action.save')"), window.eval("t('attachment.action.print')")]);
  });

  test("Escape closes the menu first and the viewer only on the second press", () => {
    const { window } = loadApp();
    window.URL.createObjectURL = () => "blob:mock-url";
    window.URL.revokeObjectURL = () => {};
    const overlay = openViewer(window);
    window.document.body.append(overlay);
    overlay.querySelector(".viewer-stage").dispatchEvent(new window.MouseEvent("contextmenu", { bubbles: true, cancelable: true }));
    overlay.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(overlay.querySelector(".viewer-menu")).toBeNull();
    expect(window.eval("state.fileViewer")).not.toBeNull();
    overlay.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(window.eval("state.fileViewer")).toBeNull();
  });

  test("the viewer's save button downloads the very file that is shown", async () => {
    const { window } = loadApp();
    window.URL.createObjectURL = () => "blob:mock-url";
    const downloads = trackDownloads(window);
    const overlay = openViewer(window);
    overlay.querySelector(".viewer-save").click();
    await settle(window);
    expect(downloads).toEqual([{ href: "blob:mock-url", download: "Foto.jpg" }]);
  });
});
