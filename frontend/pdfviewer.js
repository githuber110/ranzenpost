(function () {
  const PDFV_MIN_SCALE = 0.05;
  const PDFV_MAX_SCALE = 8;
  const PDFV_MIN_PIXEL_RATIO = 0.5;
  const PDFV_MAX_PIXEL_RATIO = 3;
  const PDFV_MAX_CANVAS_PIXELS = 8388608;
  const PDFV_RESIZE_DEBOUNCE = 160;
  const PDFV_ROOT_MARGIN = "200% 0px";
  const PDFV_MODULE_PATH = "./vendor/pdfjs/pdf.mjs";
  const PDFV_WORKER_PATH = "./vendor/pdfjs/pdf.worker.mjs";
  const PDFV_HOST_CLASS = "pdfv-host";
  const PDFV_PASSWORD_ERROR = "PasswordException";

  function toPositive(value) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? number : 0;
  }

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  function fitToWidthScale(containerWidth, pageWidth, gutter) {
    const available = toPositive(containerWidth) - toPositive(gutter);
    const natural = toPositive(pageWidth);
    if (available <= 0 || natural <= 0) return PDFV_MIN_SCALE;
    return clamp(available / natural, PDFV_MIN_SCALE, PDFV_MAX_SCALE);
  }

  function canvasPixelRatio(cssWidth, cssHeight, deviceRatio, maxPixels) {
    const width = toPositive(cssWidth);
    const height = toPositive(cssHeight);
    if (width <= 0 || height <= 0) return 1;
    const requested = clamp(toPositive(deviceRatio) || 1, PDFV_MIN_PIXEL_RATIO, PDFV_MAX_PIXEL_RATIO);
    const budget = toPositive(maxPixels) || PDFV_MAX_CANVAS_PIXELS;
    const allowed = Math.sqrt(budget / (width * height));
    return Math.max(PDFV_MIN_PIXEL_RATIO, Math.min(requested, allowed));
  }

  function make(tag, attrs, children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") node.className = value;
      else node.setAttribute(key, value);
    }
    for (const child of [].concat(children === undefined || children === null ? [] : children)) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child.nodeType ? child : document.createTextNode(child));
    }
    return node;
  }

  function translator(custom) {
    if (typeof custom === "function") return custom;
    return (key, vars) => (typeof window.t === "function" ? window.t(key, vars) : key);
  }

  function digits(value) {
    return typeof window.formatNumber === "function" ? window.formatNumber(value) : String(value);
  }

  function absolutePath(path) {
    try {
      return new URL(path, document.baseURI).href;
    } catch (error) {
      return path;
    }
  }

  function defaultLoader() {
    return import(PDFV_MODULE_PATH);
  }

  function create(options) {
    const config = options || {};
    const t = translator(config.translate);
    const gutter = toPositive(config.gutter);
    const maxPixels = toPositive(config.maxCanvasPixels) || PDFV_MAX_CANVAS_PIXELS;
    const loadPdfjs = typeof config.loadPdfjs === "function" ? config.loadPdfjs : defaultLoader;
    const workerSrc = config.workerSrc || absolutePath(PDFV_WORKER_PATH);

    const column = make("div", { class: "pdfv-column" });
    const scroll = make(
      "div",
      { class: "pdfv-scroll", tabindex: "0", role: "region", "aria-label": t("viewer.pdf.region") },
      [column]
    );
    const banner = make("p", { class: "pdfv-banner", role: "status" }, [t("viewer.pdf.loading")]);
    const counter = make("p", { class: "pdfv-counter", hidden: "" });
    const root = make("div", { class: "pdfv pdfv-busy" }, [scroll, banner, counter]);

    const slots = [];
    const visible = new Set();
    const onscreen = new Set();
    let destroyed = false;
    let book = null;
    let loadingTask = null;
    let watcher = null;
    let counterWatcher = null;
    let sizeWatcher = null;
    let resizeTimer = 0;
    let hosts = [];
    let scale = 1;
    let baseWidth = 0;
    let baseHeight = 0;
    let epoch = 0;

    function measure() {
      const width = toPositive(column.clientWidth) || toPositive(scroll.clientWidth) || toPositive(config.width);
      return width || toPositive(window.innerWidth);
    }

    function claimHosts() {
      hosts = [];
      let parent = root.parentElement;
      while (parent && parent !== document.documentElement) {
        parent.classList.add(PDFV_HOST_CLASS);
        hosts.push(parent);
        parent = parent.parentElement;
      }
    }

    function releaseHosts() {
      for (const host of hosts) host.classList.remove(PDFV_HOST_CLASS);
      hosts = [];
    }

    function applySlotSize(slot) {
      const width = Math.round(slot.pageWidth * scale);
      const height = Math.round(slot.pageHeight * scale);
      slot.node.style.setProperty("--pdfv-page-w", width + "px");
      slot.node.style.setProperty("--pdfv-page-h", height + "px");
      slot.width = width;
      slot.height = height;
    }

    function releaseSlot(slot) {
      if (slot.task && typeof slot.task.cancel === "function") {
        try {
          slot.task.cancel();
        } catch (error) {
          slot.task = null;
        }
      }
      slot.task = null;
      slot.painted = false;
      if (!slot.canvas) return;
      slot.canvas.width = 0;
      slot.canvas.height = 0;
      slot.canvas.remove();
      slot.canvas = null;
    }

    function updateCounter() {
      if (slots.length < 2) return;
      const current = onscreen.size ? Math.min(...onscreen) : 0;
      counter.textContent = t("viewer.pdf.position", {
        current: digits(current + 1),
        total: digits(slots.length),
      });
      counter.hidden = false;
    }

    function context2d(canvas) {
      try {
        return typeof canvas.getContext === "function" ? canvas.getContext("2d") : null;
      } catch (error) {
        return null;
      }
    }

    async function paint(slot) {
      if (destroyed || slot.painting || slot.painted) return;
      const stamp = epoch;
      slot.painting = true;
      try {
        const sheet = await book.getPage(slot.index + 1);
        if (destroyed || stamp !== epoch || !desired(slot)) return;
        const natural = sheet.getViewport({ scale: 1 });
        slot.pageWidth = toPositive(natural.width) || baseWidth;
        slot.pageHeight = toPositive(natural.height) || baseHeight;
        applySlotSize(slot);
        const viewport = sheet.getViewport({ scale });
        const ratio = canvasPixelRatio(viewport.width, viewport.height, window.devicePixelRatio, maxPixels);
        const canvas = make("canvas", {
          class: "pdfv-canvas",
          role: "img",
          "aria-label": t("viewer.pdf.page", { number: digits(slot.index + 1) }),
        });
        canvas.width = Math.max(1, Math.round(viewport.width * ratio));
        canvas.height = Math.max(1, Math.round(viewport.height * ratio));
        if (destroyed || stamp !== epoch || !desired(slot)) return;
        const task = sheet.render({
          canvas,
          canvasContext: context2d(canvas),
          viewport,
          transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0],
        });
        slot.task = task;
        slot.node.append(canvas);
        slot.canvas = canvas;
        if (task && task.promise) await task.promise;
        if (destroyed || stamp !== epoch) return;
        slot.painted = true;
        slot.node.classList.add("pdfv-page-ready");
        slot.node.classList.remove("pdfv-page-failed");
      } catch (error) {
        if (destroyed || stamp !== epoch) return;
        releaseSlot(slot);
        if (!(error && error.name === "RenderingCancelledException")) {
          slot.node.classList.add("pdfv-page-failed");
        }
      } finally {
        slot.painting = false;
        if (!destroyed && stamp !== epoch && desired(slot)) paint(slot);
      }
    }

    function desired(slot) {
      return !watcher || visible.has(slot.index);
    }

    function wanted() {
      return slots.filter(desired);
    }

    function pump() {
      for (const slot of wanted()) paint(slot);
    }

    function onIntersect(entries) {
      for (const entry of entries) {
        const index = Number(entry.target.getAttribute("data-page")) - 1;
        const slot = slots[index];
        if (!slot) continue;
        if (entry.isIntersecting) visible.add(index);
        else {
          visible.delete(index);
          releaseSlot(slot);
        }
      }
      updateCounter();
      pump();
    }

    function onCounterIntersect(entries) {
      for (const entry of entries) {
        const index = Number(entry.target.getAttribute("data-page")) - 1;
        if (!slots[index]) continue;
        if (entry.isIntersecting) onscreen.add(index);
        else onscreen.delete(index);
      }
      updateCounter();
    }

    function rescale() {
      if (destroyed || !slots.length) return;
      const next = fitToWidthScale(measure(), baseWidth, gutter);
      if (Math.abs(next - scale) < 0.001) return;
      scale = next;
      epoch += 1;
      for (const slot of slots) {
        applySlotSize(slot);
        releaseSlot(slot);
      }
      pump();
    }

    function onResize() {
      if (destroyed) return;
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(rescale, PDFV_RESIZE_DEBOUNCE);
    }

    function listen() {
      window.addEventListener("resize", onResize);
      window.addEventListener("orientationchange", onResize);
      if (window.visualViewport) window.visualViewport.addEventListener("resize", onResize);
      if (typeof window.ResizeObserver === "function") {
        sizeWatcher = new window.ResizeObserver(onResize);
        sizeWatcher.observe(scroll);
      }
    }

    function unlisten() {
      window.clearTimeout(resizeTimer);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", onResize);
      if (window.visualViewport) window.visualViewport.removeEventListener("resize", onResize);
      if (sizeWatcher) sizeWatcher.disconnect();
      sizeWatcher = null;
    }

    function build(total) {
      for (let index = 0; index < total; index += 1) {
        const node = make("div", { class: "pdfv-page", "data-page": String(index + 1) });
        const slot = {
          index,
          node,
          canvas: null,
          task: null,
          painted: false,
          painting: false,
          pageWidth: baseWidth,
          pageHeight: baseHeight,
          width: 0,
          height: 0,
        };
        applySlotSize(slot);
        slots.push(slot);
        column.append(node);
      }
    }

    function cleanupAfterFailure() {
      releaseHosts();
      if (loadingTask && typeof loadingTask.destroy === "function") {
        try {
          loadingTask.destroy();
        } catch (error) {
          loadingTask = null;
        }
      }
      loadingTask = null;
      if (book && typeof book.destroy === "function") {
        try {
          book.destroy();
        } catch (error) {
          book = null;
        }
      }
      book = null;
    }

    function fail(error) {
      if (destroyed) return { ok: false, error };
      cleanupAfterFailure();
      root.classList.remove("pdfv-busy");
      root.classList.add("pdfv-failed");
      banner.className = "pdfv-banner pdfv-banner-error";
      banner.setAttribute("role", "alert");
      banner.textContent =
        error && error.name === PDFV_PASSWORD_ERROR ? t("viewer.pdf.protected") : t("viewer.pdf.error");
      banner.hidden = false;
      counter.hidden = true;
      if (typeof config.onError === "function") config.onError(error);
      return { ok: false, error };
    }

    async function start() {
      claimHosts();
      try {
        const pdfjs = await loadPdfjs();
        if (destroyed) return { ok: false, error: null };
        if (pdfjs.GlobalWorkerOptions && !pdfjs.GlobalWorkerOptions.workerSrc) {
          pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;
        }
        const payload = config.data ? await config.data : null;
        const source = payload ? { data: new Uint8Array(payload) } : { url: config.url };
        loadingTask = pdfjs.getDocument(source);
        book = await loadingTask.promise;
        if (destroyed) return { ok: false, error: null };
        const total = Number(book.numPages) || 0;
        if (total < 1) throw new Error("empty document");
        const first = await book.getPage(1);
        if (destroyed) return { ok: false, error: null };
        const natural = first.getViewport({ scale: 1 });
        baseWidth = toPositive(natural.width) || 1;
        baseHeight = toPositive(natural.height) || 1;
        scale = fitToWidthScale(measure(), baseWidth, gutter);
        build(total);
        root.classList.remove("pdfv-busy");
        banner.hidden = true;
        if (typeof window.IntersectionObserver === "function") {
          watcher = new window.IntersectionObserver(onIntersect, {
            root: scroll,
            rootMargin: PDFV_ROOT_MARGIN,
          });
          counterWatcher = new window.IntersectionObserver(onCounterIntersect, {
            root: scroll,
            rootMargin: "0px",
          });
          for (const slot of slots) {
            watcher.observe(slot.node);
            counterWatcher.observe(slot.node);
          }
        }
        listen();
        updateCounter();
        pump();
        return { ok: true, pages: total };
      } catch (error) {
        return fail(error);
      }
    }

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      unlisten();
      releaseHosts();
      if (watcher) watcher.disconnect();
      watcher = null;
      if (counterWatcher) counterWatcher.disconnect();
      counterWatcher = null;
      for (const slot of slots) releaseSlot(slot);
      visible.clear();
      onscreen.clear();
      if (loadingTask && typeof loadingTask.destroy === "function") {
        try {
          loadingTask.destroy();
        } catch (error) {
          loadingTask = null;
        }
      }
      loadingTask = null;
      if (book && typeof book.destroy === "function") {
        try {
          book.destroy();
        } catch (error) {
          book = null;
        }
      }
      book = null;
    }

    const ready = Promise.resolve().then(start);

    return { node: root, ready, destroy, rescale };
  }

  window.PdfViewer = { create, fitToWidthScale, canvasPixelRatio };
})();
