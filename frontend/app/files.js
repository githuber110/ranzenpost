const DISPOSITION_FILENAME_PATTERN = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i;

function filenameFromDisposition(header) {
  const match = DISPOSITION_FILENAME_PATTERN.exec(header || "");
  if (!match) return "";
  try {
    return decodeURIComponent(match[1]);
  } catch (error) {
    return match[1];
  }
}

async function responseUserMessage(response) {
  if (!(response.headers.get("content-type") || "").includes("json")) return "";
  try {
    return apiMessage(await response.json(), "");
  } catch (error) {
    return "";
  }
}

const IMAGE_EXTENSION_PATTERN = /\.(png|jpe?g|gif|webp|bmp|avif|heic|heif)$/i;
const IMAGE_TYPE_PATTERN = /^image\/(png|jpeg|gif|webp|bmp|avif|heic|heif)\b/i;
const PDF_EXTENSION_PATTERN = /\.pdf$/i;
const PDF_TYPE_PATTERN = /^application\/pdf\b/i;
const OPAQUE_TYPES = ["", "application/octet-stream", "binary/octet-stream"];
const DOWNLOAD_REVOKE_DELAY = 4000;
const VIEWER_ZOOM_MAX = 5;
const VIEWER_DOUBLE_TAP_MS = 320;
const VIEWER_DOUBLE_TAP_SLOP = 24;

function fileKind(filename, type) {
  const mime = String(type || "").split(";")[0].trim().toLowerCase();
  if (IMAGE_TYPE_PATTERN.test(mime)) return "image";
  if (PDF_TYPE_PATTERN.test(mime)) return "pdf";
  if (!OPAQUE_TYPES.includes(mime)) return "download";
  if (IMAGE_EXTENSION_PATTERN.test(filename || "")) return "image";
  if (PDF_EXTENSION_PATTERN.test(filename || "")) return "pdf";
  return "download";
}

function downloadBlob(objectUrl, filename) {
  const link = el("a", { href: objectUrl, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), DOWNLOAD_REVOKE_DELAY);
}

function openFileViewer(kind, objectUrl, filename, triggerEl, blob) {
  state.fileViewer = { kind, url: objectUrl, filename, blob: blob || null, trigger: triggerEl || null, pdfSettled: false };
  state.fileViewerFocused = false;
  rerender();
}

function discardFileViewer() {
  const current = state.fileViewer;
  if (!current) return;
  state.fileViewer = null;
  unmountFileViewer();
  if (typeof current.pdfCleanup === "function") current.pdfCleanup();
  URL.revokeObjectURL(current.url);
}

function closeFileViewer() {
  const current = state.fileViewer;
  if (!current) return;
  discardFileViewer();
  rerender();
  if (current.trigger && typeof current.trigger.focus === "function") current.trigger.focus();
}

function pdfViewerFailed(viewer) {
  if (state.fileViewer !== viewer || viewer.pdfSettled) return;
  viewer.pdfSettled = true;
  state.fileViewer = null;
  unmountFileViewer();
  if (typeof viewer.pdfCleanup === "function") viewer.pdfCleanup();
  rerender();
  if (viewer.trigger && typeof viewer.trigger.focus === "function") viewer.trigger.focus();
  toast(t("common.filePreviewUnavailable"), "good");
  downloadBlob(viewer.url, viewer.filename);
}

function pdfViewerLoaded(viewer) {
  if (state.fileViewer !== viewer) return;
  viewer.pdfSettled = true;
}

async function fetchAppFile(path, fallbackFilename) {
  const response = await getFile(path);
  if (!response.ok) {
    const failure = new Error("http " + response.status);
    failure.userMessage = await responseUserMessage(response);
    throw failure;
  }
  const filename = filenameFromDisposition(response.headers.get("content-disposition")) || fallbackFilename;
  const blob = await response.blob();
  return { blob, filename };
}

async function openAppFile(path, fallbackFilename, triggerEl) {
  const { blob, filename } = await fetchAppFile(path, fallbackFilename);
  const objectUrl = URL.createObjectURL(blob);
  const kind = fileKind(filename, blob.type);
  if (kind === "image" || kind === "pdf") {
    openFileViewer(kind, objectUrl, filename, triggerEl, blob);
    return;
  }
  downloadBlob(objectUrl, filename);
}

const PRINT_FRAME_RELEASE_MS = 60000;

function coarsePointer() {
  return !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches);
}

function shareableFile(blob, filename) {
  if (typeof File !== "function" || !navigator.share || !navigator.canShare) return null;
  const file = new File([blob], filename || t("common.attachment"), { type: blob.type || "" });
  return navigator.canShare({ files: [file] }) ? file : null;
}

async function shareFile(file, filename) {
  try {
    await navigator.share({ files: [file], title: filename });
    return true;
  } catch (error) {
    return !!(error && error.name === "AbortError");
  }
}

async function saveFile(blob, filename) {
  const file = coarsePointer() ? shareableFile(blob, filename) : null;
  if (file && (await shareFile(file, filename))) return;
  if (typeof window.showSaveFilePicker === "function") {
    try {
      const handle = await window.showSaveFilePicker({ suggestedName: filename });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      toast(t("common.saved"));
      return;
    } catch (error) {
      if (error && error.name === "AbortError") return;
    }
  }
  downloadBlob(URL.createObjectURL(blob), filename);
}

function printDocumentFor(blob, filename) {
  const kind = fileKind(filename, blob.type);
  if (kind === "pdf") return blob;
  if (kind !== "image") return null;
  const picture = URL.createObjectURL(blob);
  const page = `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(filename)}</title>` +
    `<style>html,body{margin:0}img{max-width:100%;max-height:100vh}</style></head>` +
    `<body><img src="${picture}" alt=""></body></html>`;
  return new Blob([page], { type: "text/html" });
}

function printInFrame(source) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(source);
    const frame = el("iframe", { class: "print-frame", src: url, "aria-hidden": "true", tabindex: "-1" });
    let settled = false;
    const finish = (ok) => {
      if (settled) return;
      settled = true;
      window.setTimeout(() => {
        frame.remove();
        URL.revokeObjectURL(url);
      }, PRINT_FRAME_RELEASE_MS);
      resolve(ok);
    };
    frame.addEventListener("load", () => {
      const run = () => {
        try {
          frame.contentWindow.focus();
          frame.contentWindow.print();
          finish(true);
        } catch (error) {
          finish(false);
        }
      };
      const picture = frame.contentDocument && frame.contentDocument.querySelector("img");
      if (picture && !picture.complete) {
        picture.addEventListener("load", run, { once: true });
        picture.addEventListener("error", () => finish(false), { once: true });
        return;
      }
      run();
    });
    frame.addEventListener("error", () => finish(false));
    document.body.append(frame);
  });
}

async function printFile(blob, filename) {
  const document_ = printDocumentFor(blob, filename);
  if (!document_) {
    toast(t("attachment.print.unsupported"), "bad");
    downloadBlob(URL.createObjectURL(blob), filename);
    return;
  }
  if (coarsePointer()) {
    const file = shareableFile(blob, filename);
    if (file && (await shareFile(file, filename))) return;
  }
  if (!(await printInFrame(document_))) toast(t("attachment.print.failed"), "bad");
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function pointDistance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function attachImageViewerGestures(img) {
  const pointers = new Map();
  let scale = 1;
  let translateX = 0;
  let translateY = 0;
  let startDistance = 0;
  let startScale = 1;
  let panStart = null;
  let lastTapTime = 0;
  let lastTapPoint = null;

  function applyTransform() {
    img.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
  }

  function resetZoom() {
    scale = 1;
    translateX = 0;
    translateY = 0;
    applyTransform();
  }

  function toggleZoom() {
    if (scale > 1) resetZoom();
    else {
      scale = 2.5;
      applyTransform();
    }
  }

  img.addEventListener("pointerdown", (event) => {
    img.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 1) {
      panStart = { x: event.clientX - translateX, y: event.clientY - translateY };
    } else if (pointers.size === 2) {
      const points = [...pointers.values()];
      startDistance = pointDistance(points[0], points[1]);
      startScale = scale;
      panStart = null;
    }
  });

  img.addEventListener("pointermove", (event) => {
    if (!pointers.has(event.pointerId)) return;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 2) {
      const points = [...pointers.values()];
      const newDistance = pointDistance(points[0], points[1]);
      if (startDistance > 0) {
        scale = Math.min(Math.max(startScale * (newDistance / startDistance), 1), VIEWER_ZOOM_MAX);
        applyTransform();
      }
    } else if (pointers.size === 1 && panStart && scale > 1) {
      translateX = event.clientX - panStart.x;
      translateY = event.clientY - panStart.y;
      applyTransform();
    }
  });

  function endPointer(event) {
    const wasSingle = pointers.size === 1;
    const point = pointers.get(event.pointerId);
    pointers.delete(event.pointerId);
    if (pointers.size === 0) {
      panStart = null;
      if (scale < 1) resetZoom();
      if (wasSingle && point) {
        const now = Date.now();
        if (now - lastTapTime < VIEWER_DOUBLE_TAP_MS && lastTapPoint && pointDistance(point, lastTapPoint) < VIEWER_DOUBLE_TAP_SLOP) {
          toggleZoom();
          lastTapTime = 0;
          lastTapPoint = null;
        } else {
          lastTapTime = now;
          lastTapPoint = point;
        }
      }
    } else if (pointers.size === 1) {
      const [remaining] = [...pointers.values()];
      panStart = { x: remaining.x - translateX, y: remaining.y - translateY };
    }
  }

  img.addEventListener("pointerup", endPointer);
  img.addEventListener("pointercancel", endPointer);
}

function fileViewerImage(viewer) {
  const img = el("img", {
    src: viewer.url,
    alt: viewer.filename || t("common.attachment"),
    class: "viewer-img",
    draggable: "false",
  });
  attachImageViewerGestures(img);
  return img;
}

function pdfViewerBytes(blob) {
  if (!blob || typeof blob.arrayBuffer !== "function") return null;
  return blob.arrayBuffer();
}

function fileViewerPdf(viewer) {
  if (!viewer.pdfView) {
    const view = window.PdfViewer.create({
      url: viewer.url,
      data: pdfViewerBytes(viewer.blob),
      onError: () => pdfViewerFailed(viewer),
    });
    view.ready.then((outcome) => {
      if (outcome && outcome.ok) pdfViewerLoaded(viewer);
    });
    viewer.pdfView = view;
    viewer.pdfCleanup = () => {
      viewer.pdfView = null;
      view.destroy();
    };
  }
  return el("div", { class: "viewer-pdf-wrap" }, [viewer.pdfView.node]);
}

let mountedFileViewer = null;

function syncFileViewer() {
  const wanted = state.fileViewer;
  if (!wanted) {
    unmountFileViewer();
    return;
  }
  if (mountedFileViewer && mountedFileViewer.viewer === wanted) return;
  unmountFileViewer();
  const node = fileViewerNode();
  if (!node) return;
  mountedFileViewer = { viewer: wanted, node };
  document.body.append(node);
}

function unmountFileViewer() {
  if (!mountedFileViewer) return;
  mountedFileViewer.node.remove();
  mountedFileViewer = null;
}

function trapViewerFocus(event, overlay) {
  const focusable = [...overlay.querySelectorAll("button, [tabindex]")].filter((node) => !node.disabled);
  if (!focusable.length) return;
  event.preventDefault();
  const current = focusable.indexOf(document.activeElement);
  const step = event.shiftKey ? -1 : 1;
  const next = current < 0 ? 0 : (current + step + focusable.length) % focusable.length;
  focusable[next].focus();
}

function viewerSave(viewer) {
  if (!viewer || !viewer.blob) return Promise.resolve();
  return saveFile(viewer.blob, viewer.filename);
}

function viewerPrint(viewer) {
  if (!viewer || !viewer.blob) return Promise.resolve();
  return printFile(viewer.blob, viewer.filename);
}

function viewerButton(className, iconName, label, onclick) {
  return el("button", { class: className, type: "button", "aria-label": label, title: label, onclick }, [icon(iconName, 20)]);
}

function closeViewerMenu(overlay) {
  const menu = overlay.querySelector(".viewer-menu");
  if (menu) menu.remove();
}

function openViewerMenu(overlay, viewer, x, y) {
  closeViewerMenu(overlay);
  const menu = el("div", { class: "viewer-menu", role: "menu" }, [
    el("button", { class: "viewer-menu-item viewer-menu-save", type: "button", role: "menuitem", onclick: () => { closeViewerMenu(overlay); viewerSave(viewer); } }, [icon("download", 16), el("span", {}, t("attachment.action.save"))]),
    el("button", { class: "viewer-menu-item viewer-menu-print", type: "button", role: "menuitem", onclick: () => { closeViewerMenu(overlay); viewerPrint(viewer); } }, [icon("print", 16), el("span", {}, t("attachment.action.print"))]),
  ]);
  menu.style.insetInlineStart = `${Math.max(0, x)}px`;
  menu.style.insetBlockStart = `${Math.max(0, y)}px`;
  overlay.append(menu);
  const first = menu.querySelector("button");
  if (first) first.focus();
}

function fileViewerNode() {
  const viewer = state.fileViewer;
  if (!viewer) return null;
  const body = viewer.kind === "image" ? fileViewerImage(viewer) : fileViewerPdf(viewer);
  const stage = el("div", { class: "viewer-stage" }, [body]);
  const overlay = el(
    "div",
    { class: "viewer-overlay", role: "dialog", "aria-modal": "true", "aria-label": viewer.filename || t("common.attachment") },
    [
      stage,
      el("div", { class: "viewer-actions" }, [
        viewerButton("viewer-btn viewer-save", "download", t("attachment.action.save"), () => viewerSave(viewer)),
        viewerButton("viewer-btn viewer-print", "print", t("attachment.action.print"), () => viewerPrint(viewer)),
        viewerButton("viewer-btn viewer-close", "close", t("common.close"), closeFileViewer),
      ]),
    ]
  );
  stage.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    const box = overlay.getBoundingClientRect();
    openViewerMenu(overlay, viewer, event.clientX - box.left, event.clientY - box.top);
  });
  overlay.addEventListener("pointerdown", (event) => {
    if (!event.target.closest(".viewer-menu")) closeViewerMenu(overlay);
  });
  overlay.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      if (overlay.querySelector(".viewer-menu")) {
        closeViewerMenu(overlay);
        return;
      }
      closeFileViewer();
    } else if (event.key === "Tab") {
      trapViewerFocus(event, overlay);
    }
  });
  window.setTimeout(() => {
    if (state.fileViewerFocused) return;
    const close = overlay.querySelector(".viewer-close");
    if (close) close.focus();
    state.fileViewerFocused = true;
  }, 0);
  return overlay;
}

function fileName(file) {
  return file.filename || "";
}

function attachmentRowContent(filename, sub) {
  return [
    el("span", { class: "row-dot" }, [icon("clip", 14)]),
    el("div", { class: "row-main" }, [
      iservText("div", { class: "row-title full" }, filename || t("common.attachment")),
      sub ? iservText("div", { class: "row-sub" }, sub) : null,
    ]),
  ];
}

function attachmentActionRow(className, iconName, label, onclick) {
  return el("button", { type: "button", class: `row ${className}`, onclick }, [
    el("span", { class: "row-dot" }, [icon(iconName, 14)]),
    el("div", { class: "row-main" }, [el("div", { class: "row-title full" }, label)]),
  ]);
}

async function runAttachmentAction(action, file, filename, trigger) {
  try {
    if (action === "open") {
      await openAppFile(file.url, filename, trigger);
      return;
    }
    const loaded = await fetchAppFile(file.url, filename);
    if (action === "save") await saveFile(loaded.blob, loaded.filename);
    else await printFile(loaded.blob, loaded.filename);
  } catch (error) {
    toast(error.userMessage || t("common.attachmentOpenFailed"), "bad");
  }
}

function attachmentActionsSheet(file, trigger) {
  const filename = file.filename || t("common.attachment");
  const choose = (action) => () => {
    discardSheet();
    runAttachmentAction(action, file, filename, trigger);
  };
  return sheet(filename, [
    el("div", { class: "rows" }, [
      attachmentActionRow("attach-open", "open", t("attachment.action.open"), choose("open")),
      attachmentActionRow("attach-save", "download", t("attachment.action.save"), choose("save")),
      attachmentActionRow("attach-print", "print", t("attachment.action.print"), choose("print")),
    ]),
  ]);
}

function attachmentButton(file) {
  const filename = file.filename || t("common.attachment");
  const button = el(
    "button",
    { type: "button", class: "row read" },
    attachmentRowContent(filename, file.sub)
  );
  button.addEventListener("click", () => {
    openNestedSheet(() => attachmentActionsSheet(file, button));
  });
  return button;
}

function attachmentRows(files) {
  const rows = el("div", { class: "rows" });
  for (const file of files) {
    rows.append(
      file.url ? attachmentButton(file) : el("div", { class: "row read disabled" }, attachmentRowContent(fileName(file), file.sub))
    );
  }
  return rows;
}
