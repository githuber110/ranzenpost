export const TOAST_HOLD_MS = 3200;

export function createToast({ slot, timers, rerender, dom }) {
  let timer = 0;

  const toast = (message, kind = "good") => {
    timers.clear(timer);
    slot.write({ message, kind });
    timer = timers.set(() => {
      slot.write(null);
      rerender();
    }, TOAST_HOLD_MS);
    rerender();
  };

  const toastNode = () => {
    const current = slot.read();
    return dom.el("div", { class: `toast ${current.kind}`, role: "status" }, [
      dom.icon(current.kind === "bad" ? "alert" : "check", 16),
      dom.el("span", {}, current.message),
    ]);
  };

  return { toast, toastNode };
}

export const SHEET_KEYS = Object.freeze([
  "sheet",
  "onSheetClose",
  "sheetForm",
  "sheetFormDefault",
  "sheetDiscardAsk",
  "sheetFocused",
]);

const snapshot = (value) => JSON.parse(JSON.stringify(value === undefined ? null : value));

export function createSheets({ slot, layout, t, dom, timers, rerender }) {
  const resetSheetForm = () => {
    slot.write("sheetForm", null);
    slot.write("sheetFormDefault", null);
  };

  const fillSheet = (factory, onClose) => {
    slot.write("sheet", factory);
    slot.write("onSheetClose", onClose);
    resetSheetForm();
    slot.write("sheetDiscardAsk", false);
  };

  const openSheet = (factory, onClose = null) => {
    fillSheet(factory, onClose);
    slot.write("sheetFocused", false);
    rerender();
  };

  const placeSheet = (factory) => {
    slot.write("sheet", factory);
  };

  const dropSheet = () => {
    fillSheet(null, null);
  };

  const discardSheet = () => {
    const after = slot.read("onSheetClose");
    dropSheet();
    if (after) return after();
    rerender();
  };

  const isSheetFormDirty = () => {
    const form = slot.read("sheetForm");
    const baseline = slot.read("sheetFormDefault");
    if (!form || !baseline) return false;
    return JSON.stringify(form) !== JSON.stringify(baseline);
  };

  const closeSheet = () => {
    if (isSheetFormDirty()) {
      slot.write("sheetDiscardAsk", true);
      return rerender();
    }
    return discardSheet();
  };

  const keepSheet = () => {
    slot.write("sheetDiscardAsk", false);
    rerender();
  };

  const discardPanel = () =>
    dom.el("div", {
      class: "sheet-confirm",
      role: "alertdialog",
      "aria-modal": "true",
      "aria-label": t("sheet.discard.title"),
    }, [
      dom.el("p", { class: "dlg-text" }, t("sheet.discard.text")),
      dom.el("div", { class: "btn-stack" }, [
        dom.el("button", { class: "btn destructive", type: "button", onclick: discardSheet }, t("sheet.discard.confirm")),
        dom.el("button", { class: "btn ghost", type: "button", onclick: keepSheet }, t("sheet.discard.keep")),
      ]),
    ]);

  const sheetState = (build) => {
    if (!slot.read("sheetForm")) {
      slot.write("sheetForm", build());
      slot.write("sheetFormDefault", snapshot(slot.read("sheetForm")));
    }
    return slot.read("sheetForm");
  };

  const sheet = (title, body, foot, headerExtra) => {
    const panel = dom.el("div", { class: "sheet", role: "dialog", "aria-modal": "true" }, [
      dom.el("div", { class: "sheet-head" }, [
        dom.el("div", { class: "sheet-title", tabindex: "-1" }, title),
        dom.el("div", { class: "sheet-head-actions" }, [
          headerExtra || null,
          dom.el("button", { class: "sheet-close", type: "button", "aria-label": t("common.close"), onclick: closeSheet }, [dom.icon("close", 16)]),
        ]),
      ]),
      dom.el("div", { class: "sheet-body" }, body),
      foot ? dom.el("div", { class: "sheet-foot" }, foot) : null,
    ]);
    if (slot.read("sheetDiscardAsk")) panel.append(discardPanel());
    panel.addEventListener("click", (event) => event.stopPropagation());
    const scrim = dom.el("div", { class: layout() === "phone" ? "scrim" : "scrim dialog", onclick: closeSheet });
    scrim.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeSheet();
    });
    scrim.append(panel);
    timers.set(() => {
      if (slot.read("sheetFocused")) return;
      const heading = panel.querySelector(".sheet-title");
      if (!heading) return;
      heading.focus();
      slot.write("sheetFocused", true);
    }, 0);
    return scrim;
  };

  const openNestedSheet = (factory) => {
    const previous = slot.read("sheet");
    const previousForm = slot.read("sheetForm");
    const previousDefault = slot.read("sheetFormDefault");
    const previousClose = slot.read("onSheetClose");
    if (!previous) return openSheet(factory);
    slot.write("onSheetClose", () => {
      slot.write("onSheetClose", previousClose);
      slot.write("sheet", previous);
      slot.write("sheetForm", previousForm);
      slot.write("sheetFormDefault", previousDefault);
      slot.write("sheetFocused", false);
      rerender();
    });
    slot.write("sheet", factory);
    slot.write("sheetForm", null);
    slot.write("sheetFormDefault", null);
    slot.write("sheetFocused", false);
    return rerender();
  };

  const askConfirmation = ({ title, text, quote, confirmLabel, destructive }, answer) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      dropSheet();
      rerender();
      answer(value);
    };
    const body = [];
    if (text) body.push(dom.el("p", { class: "dlg-text" }, text));
    if (quote) body.push(dom.el("blockquote", { class: "dlg-quote", dir: "auto" }, quote));
    openSheet(
      () =>
        sheet(title, body, [
          dom.el("div", { class: "btn-stack" }, [
            dom.el("button", { class: destructive ? "btn destructive" : "btn", type: "button", onclick: () => finish(true) }, confirmLabel),
            dom.el("button", { class: "btn ghost", type: "button", onclick: () => finish(false) }, t("common.cancel")),
          ]),
        ]),
      () => finish(false)
    );
  };

  return {
    openSheet,
    discardSheet,
    closeSheet,
    isSheetFormDirty,
    sheetState,
    sheet,
    openNestedSheet,
    askConfirmation,
    placeSheet,
    dropSheet,
    resetSheetForm,
  };
}

export function shellGlobals() {
  return Object.freeze({ createToast, createSheets });
}
