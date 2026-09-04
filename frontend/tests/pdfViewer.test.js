import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { JSDOM, VirtualConsole } from "jsdom";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(dirname, "..");
const viewerSource = fs.readFileSync(path.join(frontendDir, "pdfviewer.js"), "utf8");
const viewerStyles = fs.readFileSync(path.join(frontendDir, "pdfviewer.css"), "utf8");
const indexHtml = fs.readFileSync(path.join(frontendDir, "index.html"), "utf8");

const A4_WIDTH = 595.28;
const A4_HEIGHT = 841.89;

function loadViewer() {
  const quiet = new VirtualConsole();
  quiet.on("jsdomError", () => {});
  const dom = new JSDOM("<!doctype html><html><head></head><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost/",
    virtualConsole: quiet,
  });
  const { window } = dom;
  const script = window.document.createElement("script");
  script.textContent = viewerSource;
  window.document.body.appendChild(script);
  return window;
}

function label(key, vars) {
  return vars ? key + ":" + JSON.stringify(vars) : key;
}

function stubPdfjs(spec) {
  const config = spec || {};
  const pages = config.pages === undefined ? 3 : config.pages;
  const width = config.width || A4_WIDTH;
  const height = config.height || A4_HEIGHT;
  const calls = [];
  const worker = { workerSrc: "" };
  const pendingPages = new Map();
  let bookDestroyed = false;
  let loadingTaskDestroyed = false;

  function page(number) {
    return {
      getViewport(params) {
        const scale = params.scale;
        return { width: width * scale, height: height * scale, scale };
      },
      render(params) {
        calls.push({ page: number, scale: params.viewport.scale, transform: params.transform });
        let resolveFn;
        let rejectFn;
        const promise = new Promise((resolve, reject) => {
          resolveFn = resolve;
          rejectFn = reject;
        });
        const deferred = config.deferRender && config.deferRender.has(number);
        if (!deferred) resolveFn();
        return {
          promise,
          cancel() {
            const error = new Error("cancelled");
            error.name = "RenderingCancelledException";
            rejectFn(error);
          },
        };
      },
    };
  }

  function getPage(number) {
    if (config.deferPages && config.deferPages.has(number)) {
      return new Promise((resolve) => {
        pendingPages.set(number, () => resolve(page(number)));
      });
    }
    return Promise.resolve(page(number));
  }

  const module = {
    GlobalWorkerOptions: worker,
    getDocument() {
      if (config.rejectWith) {
        return {
          promise: Promise.reject(config.rejectWith),
          destroy() {
            loadingTaskDestroyed = true;
          },
        };
      }
      return {
        promise: Promise.resolve({
          numPages: pages,
          getPage,
          destroy() {
            bookDestroyed = true;
          },
        }),
        destroy() {
          loadingTaskDestroyed = true;
        },
      };
    },
  };
  return {
    module,
    calls,
    worker,
    isDestroyed() {
      return bookDestroyed;
    },
    isLoadingTaskDestroyed() {
      return loadingTaskDestroyed;
    },
    resolvePage(number) {
      const resume = pendingPages.get(number);
      if (resume) resume();
    },
  };
}

function installObservers(window) {
  const instances = [];
  window.IntersectionObserver = class {
    constructor(callback, options) {
      this.callback = callback;
      this.options = options;
      this.nodes = [];
      instances.push(this);
    }
    observe(node) {
      this.nodes.push(node);
    }
    disconnect() {
      this.disconnected = true;
    }
    unobserve() {}
  };
  function find(margin) {
    return instances.find((instance) => instance.options && instance.options.rootMargin === margin);
  }
  function emit(margin, nodes, isIntersecting) {
    find(margin).callback(nodes.map((target) => ({ target, isIntersecting })));
  }
  return {
    instances,
    prefetchNodes: () => find("200% 0px").nodes,
    emitPrefetch: (nodes, isIntersecting) => emit("200% 0px", nodes, isIntersecting),
    emitOnscreen: (nodes, isIntersecting) => emit("0px", nodes, isIntersecting),
  };
}

function flush(window, turns) {
  const rounds = turns || 6;
  let chain = Promise.resolve();
  for (let step = 0; step < rounds; step += 1) {
    chain = chain.then(() => new Promise((resolve) => window.setTimeout(resolve, 0)));
  }
  return chain;
}

async function mount(window, options) {
  const view = window.PdfViewer.create(options);
  window.document.body.appendChild(view.node);
  const status = await view.ready;
  await flush(window);
  return { view, status };
}

function pageWidths(view) {
  return [...view.node.querySelectorAll(".pdfv-page")].map((node) =>
    Number.parseFloat(node.style.getPropertyValue("--pdfv-page-w"))
  );
}

describe("[P216] fit-to-width is a pure scale, not a CSS transform", () => {
  test("a page fills the container width exactly", () => {
    const window = loadViewer();
    const { fitToWidthScale } = window.PdfViewer;
    expect(fitToWidthScale(320, A4_WIDTH, 0)).toBeCloseTo(320 / A4_WIDTH, 10);
    expect(A4_WIDTH * fitToWidthScale(320, A4_WIDTH, 0)).toBeCloseTo(320, 10);
    expect(fitToWidthScale(390, A4_WIDTH, 0)).toBeCloseTo(390 / A4_WIDTH, 10);
    expect(fitToWidthScale(1024, A4_WIDTH, 0)).toBeCloseTo(1024 / A4_WIDTH, 10);
    expect(fitToWidthScale(900, A4_HEIGHT, 0)).toBeCloseTo(900 / A4_HEIGHT, 10);
  });

  test("a gutter is taken off the container width before the division", () => {
    const window = loadViewer();
    const { fitToWidthScale } = window.PdfViewer;
    expect(fitToWidthScale(320, A4_WIDTH, 16)).toBeCloseTo(304 / A4_WIDTH, 10);
    expect(A4_WIDTH * fitToWidthScale(320, A4_WIDTH, 16)).toBeCloseTo(304, 10);
  });

  test("a narrow 320 px viewport still shrinks an A4 page below one", () => {
    const window = loadViewer();
    const scale = window.PdfViewer.fitToWidthScale(320, A4_WIDTH, 0);
    expect(scale).toBeLessThan(1);
    expect(scale).toBeGreaterThan(0.5);
  });

  test("degenerate input never yields zero, NaN or Infinity", () => {
    const window = loadViewer();
    const { fitToWidthScale } = window.PdfViewer;
    for (const value of [
      fitToWidthScale(0, A4_WIDTH, 0),
      fitToWidthScale(320, 0, 0),
      fitToWidthScale(NaN, A4_WIDTH, 0),
      fitToWidthScale(320, NaN, 0),
      fitToWidthScale(undefined, undefined, undefined),
      fitToWidthScale(320, A4_WIDTH, 400),
      fitToWidthScale(-100, A4_WIDTH, 0),
    ]) {
      expect(Number.isFinite(value)).toBe(true);
      expect(value).toBeGreaterThan(0);
    }
  });
});

describe("[P216] the canvas backing store follows the device pixel ratio", () => {
  test("a retina phone gets a denser backing store than the CSS box", () => {
    const window = loadViewer();
    const ratio = window.PdfViewer.canvasPixelRatio(320, 452, 3, 8388608);
    expect(ratio).toBe(3);
  });

  test("an ordinary display renders one canvas pixel per CSS pixel", () => {
    const window = loadViewer();
    expect(window.PdfViewer.canvasPixelRatio(320, 452, 1, 8388608)).toBe(1);
  });

  test("a huge page is capped by the pixel budget instead of blowing the canvas limit", () => {
    const window = loadViewer();
    const ratio = window.PdfViewer.canvasPixelRatio(2000, 2800, 3, 8388608);
    expect(ratio).toBeLessThan(3);
    expect(2000 * ratio * (2800 * ratio)).toBeLessThanOrEqual(8388608 + 1);
  });
});

describe("[P216] every page of a multi-page document reaches the DOM", () => {
  test("a twelve page letter renders twelve page nodes, not just page one", async () => {
    const window = loadViewer();
    const pdfjs = stubPdfjs({ pages: 12 });
    const { view, status } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    expect(status).toEqual({ ok: true, pages: 12 });
    expect(view.node.querySelectorAll(".pdfv-page").length).toBe(12);
    expect(view.node.querySelectorAll(".pdfv-canvas").length).toBe(12);
    expect(pdfjs.calls.map((call) => call.page)).toEqual([
      1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
    ]);
    expect(view.node.querySelector("iframe")).toBeNull();
  });

  test("the pages sit in one scrolling column, not in a paged widget", async () => {
    const window = loadViewer();
    const pdfjs = stubPdfjs({ pages: 4 });
    const { view } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    const column = view.node.querySelector(".pdfv-scroll > .pdfv-column");
    expect(column).not.toBeNull();
    expect(column.children.length).toBe(4);
    expect(viewerStyles).toMatch(/\.pdfv-scroll\s*\{[^}]*overflow-y:\s*auto/);
    expect(viewerStyles).toMatch(/\.pdfv-scroll\s*\{[^}]*overscroll-behavior:\s*contain/);
  });

  test("the worker points at the vendored pdf.js worker", async () => {
    const window = loadViewer();
    const pdfjs = stubPdfjs({ pages: 1 });
    await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    expect(pdfjs.worker.workerSrc).toBe("http://localhost/vendor/pdfjs/pdf.worker.mjs");
  });
});

describe("[P216] long documents render lazily", () => {
  test("with an IntersectionObserver every page gets a node but only visible pages get a canvas", async () => {
    const window = loadViewer();
    const observers = installObservers(window);
    const pdfjs = stubPdfjs({ pages: 40 });
    const { view } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    const pages = [...view.node.querySelectorAll(".pdfv-page")];
    expect(pages.length).toBe(40);
    expect(observers.prefetchNodes().length).toBe(40);
    expect(view.node.querySelectorAll(".pdfv-canvas").length).toBe(0);

    observers.emitPrefetch(pages.slice(0, 3), true);
    await flush(window);
    expect(view.node.querySelectorAll(".pdfv-canvas").length).toBe(3);
    expect(pdfjs.calls.map((call) => call.page)).toEqual([1, 2, 3]);

    observers.emitPrefetch(pages.slice(0, 2), false);
    await flush(window);
    expect(view.node.querySelectorAll(".pdfv-canvas").length).toBe(1);
  });

  test("the counter names the first visible page out of the total", async () => {
    const window = loadViewer();
    const observers = installObservers(window);
    const pdfjs = stubPdfjs({ pages: 40 });
    const { view } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    const pages = [...view.node.querySelectorAll(".pdfv-page")];
    observers.emitPrefetch(pages.slice(6, 9), true);
    observers.emitOnscreen(pages.slice(6, 9), true);
    await flush(window);
    const counter = view.node.querySelector(".pdfv-counter");
    expect(counter.hidden).toBe(false);
    expect(counter.textContent).toBe('viewer.pdf.position:{"current":"7","total":"40"}');
  });

  test("the counter reports the page actually on screen, not a prefetched one [P216]", async () => {
    const window = loadViewer();
    const observers = installObservers(window);
    const pdfjs = stubPdfjs({ pages: 40 });
    const { view } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    const pages = [...view.node.querySelectorAll(".pdfv-page")];
    observers.emitPrefetch(pages.slice(0, 3), true);
    observers.emitOnscreen(pages.slice(0, 1), true);
    await flush(window);
    const counter = view.node.querySelector(".pdfv-counter");
    expect(counter.textContent).toBe('viewer.pdf.position:{"current":"1","total":"40"}');
  });

  test("a single page document shows no counter", async () => {
    const window = loadViewer();
    const pdfjs = stubPdfjs({ pages: 1 });
    const { view } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    expect(view.node.querySelector(".pdfv-counter").hidden).toBe(true);
  });
});

describe("[P216] a broken payload lands in a visible error state", () => {
  test("a rejected document shows the error text and reports it", async () => {
    const window = loadViewer();
    const seen = [];
    const pdfjs = stubPdfjs({ rejectWith: new Error("not a pdf") });
    const { view, status } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      onError: (error) => seen.push(error),
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    expect(status.ok).toBe(false);
    const banner = view.node.querySelector(".pdfv-banner");
    expect(banner.hidden).toBe(false);
    expect(banner.classList.contains("pdfv-banner-error")).toBe(true);
    expect(banner.getAttribute("role")).toBe("alert");
    expect(banner.textContent).toBe("viewer.pdf.error");
    expect(view.node.classList.contains("pdfv-failed")).toBe(true);
    expect(seen.length).toBe(1);
  });

  test("an encrypted document names the password case", async () => {
    const window = loadViewer();
    const locked = new Error("password required");
    locked.name = "PasswordException";
    const pdfjs = stubPdfjs({ rejectWith: locked });
    const { view } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    expect(view.node.querySelector(".pdfv-banner").textContent).toBe("viewer.pdf.protected");
  });

  test("a document reporting zero pages fails visibly instead of showing an empty box", async () => {
    const window = loadViewer();
    const pdfjs = stubPdfjs({ pages: 0 });
    const { view, status } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    expect(status.ok).toBe(false);
    expect(view.node.querySelector(".pdfv-banner").classList.contains("pdfv-banner-error")).toBe(true);
  });

  test("a pdf.js module that cannot be imported fails visibly", async () => {
    const window = loadViewer();
    const { view, status } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.reject(new Error("module blocked")),
    });
    expect(status.ok).toBe(false);
    expect(view.node.querySelector(".pdfv-banner").textContent).toBe("viewer.pdf.error");
  });

  test("a failed load destroys the loading task and the document, and releases the app shell [P216]", async () => {
    const window = loadViewer();
    const app = window.document.createElement("div");
    app.id = "app";
    window.document.body.appendChild(app);
    const pdfjs = stubPdfjs({ rejectWith: new Error("not a pdf") });
    const view = window.PdfViewer.create({
      url: "blob:doc",
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    app.appendChild(view.node);
    const status = await view.ready;
    await flush(window);
    expect(status.ok).toBe(false);
    expect(pdfjs.isLoadingTaskDestroyed()).toBe(true);
    expect(app.classList.contains("pdfv-host")).toBe(false);
    expect(window.document.body.classList.contains("pdfv-host")).toBe(false);
  });

  test("a document that fails after loading is destroyed too", async () => {
    const window = loadViewer();
    const pdfjs = stubPdfjs({ pages: 0 });
    const { status } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    expect(status.ok).toBe(false);
    expect(pdfjs.isDestroyed()).toBe(true);
  });

  test("destroy() after a failed load, and destroy() called twice, never throws", async () => {
    const window = loadViewer();
    const pdfjs = stubPdfjs({ rejectWith: new Error("not a pdf") });
    const { view } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    expect(() => view.destroy()).not.toThrow();
    expect(() => view.destroy()).not.toThrow();
  });
});

describe("[P216] a slot that scrolls away mid-render never leaks a stale canvas or a false failure", () => {
  test("a page that leaves the keep-window during its getPage await never gets a canvas appended", async () => {
    const window = loadViewer();
    const observers = installObservers(window);
    const pdfjs = stubPdfjs({ pages: 5, deferPages: new Set([2]) });
    const { view } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    const pages = [...view.node.querySelectorAll(".pdfv-page")];
    observers.emitPrefetch([pages[1]], true);
    await flush(window, 1);
    observers.emitPrefetch([pages[1]], false);
    pdfjs.resolvePage(2);
    await flush(window);
    expect(pages[1].querySelector(".pdfv-canvas")).toBeNull();
  });

  test("a render cancelled by scrolling out leaves no permanent failed marker", async () => {
    const window = loadViewer();
    const observers = installObservers(window);
    const pdfjs = stubPdfjs({ pages: 5, deferRender: new Set([2]) });
    const { view } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    const pages = [...view.node.querySelectorAll(".pdfv-page")];
    observers.emitPrefetch([pages[1]], true);
    await flush(window, 1);
    observers.emitPrefetch([pages[1]], false);
    await flush(window);
    expect(pages[1].classList.contains("pdfv-page-failed")).toBe(false);
  });

  test("a page repainted successfully after an earlier real failure loses the failed marker", async () => {
    const window = loadViewer();
    Object.defineProperty(window, "innerWidth", { value: 320, configurable: true });
    const pdfjs = stubPdfjs({ pages: 2 });
    const view = window.PdfViewer.create({
      url: "blob:doc",
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    window.document.body.appendChild(view.node);
    await view.ready;
    await flush(window);
    const pages = [...view.node.querySelectorAll(".pdfv-page")];
    pages[0].classList.add("pdfv-page-failed");
    Object.defineProperty(window, "innerWidth", { value: 768, configurable: true });
    view.rescale();
    await flush(window);
    expect(pages[0].classList.contains("pdfv-page-failed")).toBe(false);
    expect(pages[0].classList.contains("pdfv-page-ready")).toBe(true);
  });
});

describe("[P216] a 320 px phone never gains a horizontal scroll", () => {
  test("no page box is ever wider than the container", async () => {
    const window = loadViewer();
    const pdfjs = stubPdfjs({ pages: 6 });
    const { view } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    const widths = pageWidths(view);
    expect(widths.length).toBe(6);
    for (const width of widths) {
      expect(width).toBeGreaterThan(0);
      expect(width).toBeLessThanOrEqual(320);
    }
  });

  test("a landscape page is fitted to the width too, never overflowing it", async () => {
    const window = loadViewer();
    const pdfjs = stubPdfjs({ pages: 2, width: A4_HEIGHT, height: A4_WIDTH });
    const { view } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    for (const width of pageWidths(view)) expect(width).toBeLessThanOrEqual(320);
  });

  test("the stylesheet clips the inline axis and caps the page box", () => {
    expect(viewerStyles).toMatch(/\.pdfv-scroll\s*\{[^}]*overflow-x:\s*hidden/);
    expect(viewerStyles).toMatch(/\.pdfv-page\s*\{[^}]*max-inline-size:\s*100%/);
    expect(viewerStyles).toMatch(/\.pdfv-canvas\s*\{[^}]*max-inline-size:\s*100%/);
  });
});

describe("[P216] pinch zoom stays with the browser and is handed back on close", () => {
  test("the ancestors of the viewer allow pinch zoom while a pdf is open", async () => {
    const window = loadViewer();
    const pdfjs = stubPdfjs({ pages: 2 });
    const { view } = await mount(window, {
      url: "blob:doc",
      width: 320,
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    expect(window.document.body.classList.contains("pdfv-host")).toBe(true);
    view.destroy();
    expect(window.document.body.classList.contains("pdfv-host")).toBe(false);
    expect(pdfjs.isDestroyed()).toBe(true);
  });

  test("the host rule really grants pinch-zoom and beats the app shell rule", () => {
    expect(viewerStyles).toMatch(/body \.pdfv-host\s*\{[^}]*touch-action:\s*pan-x pan-y pinch-zoom/);
    expect(viewerStyles).toMatch(/\.pdfv-scroll\s*\{[^}]*touch-action:\s*pan-x pan-y pinch-zoom/);
    expect(indexHtml.indexOf("pdfviewer.css")).toBeGreaterThan(indexHtml.indexOf("styles.css"));
  });

  test("the page keeps the browser zoom unlocked", () => {
    const viewport = /<meta name="viewport" content="([^"]+)"/.exec(indexHtml);
    expect(viewport).not.toBeNull();
    expect(viewport[1]).not.toMatch(/user-scalable/);
    expect(viewport[1]).not.toMatch(/maximum-scale/);
  });
});

describe("[P216] a width change re-renders instead of stretching a bitmap", () => {
  test("a wider container repaints the pages at a larger render scale", async () => {
    const window = loadViewer();
    const pdfjs = stubPdfjs({ pages: 2 });
    Object.defineProperty(window, "innerWidth", { value: 320, configurable: true });
    const view = window.PdfViewer.create({
      url: "blob:doc",
      translate: label,
      loadPdfjs: () => Promise.resolve(pdfjs.module),
    });
    window.document.body.appendChild(view.node);
    await view.ready;
    await flush(window);
    const first = pdfjs.calls.map((call) => call.scale);
    expect(first).toEqual([320 / A4_WIDTH, 320 / A4_WIDTH]);

    Object.defineProperty(window, "innerWidth", { value: 768, configurable: true });
    view.rescale();
    await flush(window);
    const repainted = pdfjs.calls.slice(2).map((call) => call.scale);
    expect(repainted).toEqual([768 / A4_WIDTH, 768 / A4_WIDTH]);
    for (const node of view.node.querySelectorAll(".pdfv-canvas")) {
      expect(node.getAttribute("style") || "").not.toMatch(/transform/);
    }
  });
});

describe("[P216] the viewer is wired into the shell", () => {
  test("index.html loads the module and its stylesheet", () => {
    expect(indexHtml).toMatch(/<link rel="stylesheet" href="\.\/pdfviewer\.css\?v=\d+">/);
    expect(indexHtml).toMatch(/<script src="\.\/pdfviewer\.js\?v=\d+"><\/script>/);
    expect(indexHtml.indexOf("pdfviewer.js")).toBeLessThan(indexHtml.indexOf("app.js"));
  });

  test("every user visible string in the module is an i18n key the backend guard can see", () => {
    const used = [...viewerSource.matchAll(/\bt\(\s*"([a-z][\w.]*)"/g)].map((hit) => hit[1]);
    expect([...new Set(used)].sort()).toEqual([
      "viewer.pdf.error",
      "viewer.pdf.loading",
      "viewer.pdf.page",
      "viewer.pdf.position",
      "viewer.pdf.protected",
      "viewer.pdf.region",
    ]);
  });

  test("the module registers a self-contained entry point on the window", () => {
    const window = loadViewer();
    expect(typeof window.PdfViewer.create).toBe("function");
    expect(typeof window.PdfViewer.fitToWidthScale).toBe("function");
    expect(typeof window.PdfViewer.canvasPixelRatio).toBe("function");
    const view = window.PdfViewer.create({ url: "blob:doc", loadPdfjs: () => Promise.reject(new Error("x")) });
    expect(view.node.nodeType).toBe(1);
    expect(typeof view.destroy).toBe("function");
    expect(typeof view.rescale).toBe("function");
    expect(typeof view.ready.then).toBe("function");
    view.destroy();
  });
});
