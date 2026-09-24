import { describe, expect, test } from "vitest";
import { JSDOM } from "jsdom";
import { createDom } from "../lib/dom.js";
import { SHEET_KEYS, TOAST_HOLD_MS, createSheets, createToast, shellGlobals } from "../lib/shell.js";

function fakeTimers() {
  const pending = new Map();
  const cleared = [];
  let next = 0;
  return {
    pending,
    cleared,
    set(run, ms) {
      next += 1;
      pending.set(next, { run, ms });
      return next;
    },
    clear(id) {
      cleared.push(id);
      pending.delete(id);
    },
    fire(id) {
      const entry = pending.get(id);
      pending.delete(id);
      entry.run();
    },
  };
}

function setup() {
  const { window } = new JSDOM("<!doctype html><html><body></body></html>");
  const held = { value: null };
  const slot = { read: () => held.value, write: (value) => { held.value = value; } };
  const timers = fakeTimers();
  const renders = [];
  const dom = createDom({ page: window.document });
  const shell = createToast({ slot, timers, rerender: () => renders.push(held.value), dom });
  return { window, dom, held, timers, renders, ...shell };
}

describe("toast writes its message into the slot it was given", () => {
  test("a toast fills the slot, repaints once and defaults to the good kind", () => {
    const { held, renders, toast } = setup();
    toast("saved");
    expect(held.value).toEqual({ message: "saved", kind: "good" });
    expect(renders).toEqual([{ message: "saved", kind: "good" }]);
  });

  test("the toast clears itself after the hold time and repaints the empty slot", () => {
    const { held, timers, renders, toast } = setup();
    toast("failed", "bad");
    const [[id, entry]] = [...timers.pending];
    expect(entry.ms).toBe(TOAST_HOLD_MS);
    expect(TOAST_HOLD_MS).toBe(3200);
    timers.fire(id);
    expect(held.value).toBe(null);
    expect(renders).toEqual([{ message: "failed", kind: "bad" }, null]);
  });

  test("a second toast cancels the first timer, so the newer message gets the full hold time", () => {
    const { held, timers, toast } = setup();
    toast("first");
    toast("second", "bad");
    expect(timers.cleared).toEqual([0, 1]);
    expect([...timers.pending.keys()]).toEqual([2]);
    expect(held.value).toEqual({ message: "second", kind: "bad" });
  });
});

describe("toastNode draws the message in the slot", () => {
  test("a good toast is a status line with the check icon and the message as text", () => {
    const { window, dom, toast, toastNode } = setup();
    toast("<b>saved</b>");
    const node = toastNode();
    expect(node.ownerDocument).toBe(window.document);
    expect(node.className).toBe("toast good");
    expect(node.getAttribute("role")).toBe("status");
    expect(node.querySelector(".ico-slot").innerHTML).toBe(dom.icon("check", 16).innerHTML);
    expect(node.querySelector("span:not(.ico-slot)").textContent).toBe("<b>saved</b>");
    expect(node.querySelector("b")).toBe(null);
  });

  test("a bad toast carries the bad class and the alert icon", () => {
    const { dom, toast, toastNode } = setup();
    toast("failed", "bad");
    const node = toastNode();
    expect(node.className).toBe("toast bad");
    expect(node.querySelector(".ico-slot").innerHTML).toBe(dom.icon("alert", 16).innerHTML);
  });

  test("toastNode reads the slot when it runs, so a message written by someone else shows", () => {
    const { held, toastNode } = setup();
    held.value = { message: "from outside", kind: "good" };
    expect(toastNode().textContent).toBe("from outside");
  });
});

function sheetSetup({ mode = "phone", initial = {} } = {}) {
  const { window } = new JSDOM("<!doctype html><html><body></body></html>");
  const held = { ...Object.fromEntries(SHEET_KEYS.map((key) => [key, null])), sheetDiscardAsk: false, sheetFocused: false, ...initial };
  const touched = new Set();
  const slot = {
    read: (key) => {
      touched.add(key);
      return held[key];
    },
    write: (key, value) => {
      touched.add(key);
      held[key] = value;
    },
  };
  const timers = fakeTimers();
  const layout = { mode };
  const renders = [];
  const dom = createDom({ page: window.document });
  const t = (key) => `t:${key}`;
  const sheets = createSheets({
    slot,
    layout: () => layout.mode,
    t,
    dom,
    timers,
    rerender: () => renders.push({ ...held }),
  });
  const draw = (...args) => {
    const scrim = sheets.sheet(...args);
    window.document.body.replaceChildren(scrim);
    return scrim;
  };
  return { window, dom, held, touched, timers, layout, renders, draw, ...sheets };
}

describe("openSheet, closeSheet and discardSheet keep the sheet keys in the slot", () => {
  test("opening a sheet stores its factory, clears the focus flag and repaints once", () => {
    const { held, renders, openSheet } = sheetSetup({ initial: { sheetFocused: true } });
    const factory = () => null;
    expect(openSheet(factory)).toBe(undefined);
    expect(held.sheet).toBe(factory);
    expect(held.sheetFocused).toBe(false);
    expect(renders).toHaveLength(1);
  });

  test("opening a second sheet replaces the first and lets its title take focus again", () => {
    const { held, openSheet } = sheetSetup();
    const first = () => null;
    const second = () => null;
    openSheet(first);
    held.sheetFocused = true;
    openSheet(second);
    expect(held.sheet).toBe(second);
    expect(held.sheetFocused).toBe(false);
  });

  test("closing a clean sheet clears every sheet key and repaints", () => {
    const { held, renders, openSheet, closeSheet } = sheetSetup();
    openSheet(() => null);
    held.sheetForm = { a: 1 };
    held.sheetFormDefault = { a: 1 };
    closeSheet();
    expect(held).toMatchObject({ sheet: null, onSheetClose: null, sheetForm: null, sheetFormDefault: null, sheetDiscardAsk: false });
    expect(renders).toHaveLength(2);
  });

  test("closing hands over to onSheetClose instead of repainting and returns what it returns", () => {
    const { held, renders, closeSheet } = sheetSetup();
    const seen = [];
    held.sheet = () => null;
    held.onSheetClose = () => {
      seen.push({ sheet: held.sheet, onSheetClose: held.onSheetClose });
      return "handled";
    };
    expect(closeSheet()).toBe("handled");
    expect(seen).toEqual([{ sheet: null, onSheetClose: null }]);
    expect(renders).toEqual([]);
  });

  test("discardSheet drops a dirty form without asking", () => {
    const { held, discardSheet } = sheetSetup({
      initial: { sheet: () => null, sheetForm: { a: 2 }, sheetFormDefault: { a: 1 }, sheetDiscardAsk: true },
    });
    discardSheet();
    expect(held).toMatchObject({ sheet: null, sheetForm: null, sheetFormDefault: null, sheetDiscardAsk: false });
  });

  test("the sheets read and write only the six sheet keys", () => {
    const setup = sheetSetup();
    const { touched, openSheet, closeSheet, sheetState, isSheetFormDirty, draw, timers } = setup;
    openSheet(() => null, () => null);
    sheetState(() => ({ a: 1 }));
    isSheetFormDirty();
    draw("title", []);
    for (const id of [...timers.pending.keys()]) timers.fire(id);
    closeSheet();
    setup.openNestedSheet(() => null);
    setup.openNestedSheet(() => null);
    setup.askConfirmation({ title: "t", confirmLabel: "c" }, () => null);
    setup.placeSheet(() => null);
    setup.resetSheetForm();
    setup.dropSheet();
    expect([...touched].sort()).toEqual([...SHEET_KEYS].sort());
  });
});

describe("sheetState and the dirty-form question", () => {
  test("sheetState builds the form once and keeps a separate baseline", () => {
    const { held, sheetState } = sheetSetup();
    let builds = 0;
    const form = sheetState(() => {
      builds += 1;
      return { names: ["a"] };
    });
    expect(sheetState(() => ({ names: ["other"] }))).toBe(form);
    expect(builds).toBe(1);
    expect(held.sheetForm).toBe(form);
    expect(held.sheetFormDefault).toEqual({ names: ["a"] });
    expect(held.sheetFormDefault).not.toBe(form);
    form.names.push("b");
    expect(held.sheetFormDefault).toEqual({ names: ["a"] });
  });

  test("a form built from undefined keeps a null baseline and never counts as dirty", () => {
    const { held, sheetState, isSheetFormDirty } = sheetSetup();
    expect(sheetState(() => undefined)).toBe(undefined);
    expect(held.sheetFormDefault).toBe(null);
    expect(isSheetFormDirty()).toBe(false);
  });

  test("the form turns dirty only when its JSON differs from the baseline", () => {
    const { sheetState, isSheetFormDirty } = sheetSetup();
    expect(isSheetFormDirty()).toBe(false);
    const form = sheetState(() => ({ label: "a" }));
    expect(isSheetFormDirty()).toBe(false);
    form.label = "b";
    expect(isSheetFormDirty()).toBe(true);
    form.label = "a";
    expect(isSheetFormDirty()).toBe(false);
  });

  test("closing a dirty sheet asks first and keeps the sheet open", () => {
    const { held, renders, sheetState, openSheet, closeSheet } = sheetSetup();
    const factory = () => null;
    openSheet(factory);
    sheetState(() => ({ label: "a" })).label = "b";
    closeSheet();
    expect(held.sheetDiscardAsk).toBe(true);
    expect(held.sheet).toBe(factory);
    expect(held.sheetForm).toEqual({ label: "b" });
    expect(renders).toHaveLength(2);
  });

  test("the question is an alert dialog with one destructive and one quiet button", () => {
    const { draw } = sheetSetup({ initial: { sheetDiscardAsk: true } });
    const ask = draw("title", []).querySelector(".sheet > .sheet-confirm");
    expect(ask.getAttribute("role")).toBe("alertdialog");
    expect(ask.getAttribute("aria-modal")).toBe("true");
    expect(ask.getAttribute("aria-label")).toBe("t:sheet.discard.title");
    expect(ask.querySelector(".dlg-text").textContent).toBe("t:sheet.discard.text");
    const buttons = [...ask.querySelectorAll(".btn-stack button")];
    expect(buttons.map((button) => [button.className, button.type, button.textContent])).toEqual([
      ["btn destructive", "button", "t:sheet.discard.confirm"],
      ["btn ghost", "button", "t:sheet.discard.keep"],
    ]);
  });

  test("keeping the sheet withdraws the question, discarding closes it", () => {
    const { held, renders, draw } = sheetSetup({
      initial: { sheet: () => null, sheetForm: { a: 2 }, sheetFormDefault: { a: 1 }, sheetDiscardAsk: true },
    });
    draw("title", []).querySelector(".sheet-confirm .btn.ghost").click();
    expect(held.sheetDiscardAsk).toBe(false);
    expect(held.sheetForm).toEqual({ a: 2 });
    expect(renders).toHaveLength(1);
    held.sheetDiscardAsk = true;
    draw("title", []).querySelector(".sheet-confirm .btn.destructive").click();
    expect(held).toMatchObject({ sheet: null, sheetForm: null, sheetFormDefault: null, sheetDiscardAsk: false });
  });

  test("a clean sheet draws no question", () => {
    const { draw } = sheetSetup();
    expect(draw("title", []).querySelector(".sheet-confirm")).toBe(null);
  });
});

describe("sheet draws the container", () => {
  test("the panel is a modal dialog with a focusable title, a labelled close button, the body and the foot", () => {
    const { window, dom, draw } = sheetSetup();
    const extra = dom.el("button", { class: "extra" }, "x");
    const scrim = draw("<b>Title</b>", ["body text"], ["foot text"], extra);
    expect(scrim.ownerDocument).toBe(window.document);
    const panel = scrim.firstElementChild;
    expect(scrim.children).toHaveLength(1);
    expect(panel.className).toBe("sheet");
    expect(panel.getAttribute("role")).toBe("dialog");
    expect(panel.getAttribute("aria-modal")).toBe("true");
    const title = panel.querySelector(".sheet-head > .sheet-title");
    expect(title.getAttribute("tabindex")).toBe("-1");
    expect(title.textContent).toBe("<b>Title</b>");
    expect(title.querySelector("b")).toBe(null);
    const actions = [...panel.querySelector(".sheet-head-actions").children];
    expect(actions[0]).toBe(extra);
    expect(actions[1].className).toBe("sheet-close");
    expect(actions[1].type).toBe("button");
    expect(actions[1].getAttribute("aria-label")).toBe("t:common.close");
    expect(actions[1].querySelector(".ico-slot").innerHTML).toBe(dom.icon("close", 16).innerHTML);
    expect(panel.querySelector(".sheet-body").textContent).toBe("body text");
    expect(panel.querySelector(".sheet-foot").textContent).toBe("foot text");
  });

  test("without a foot or extra there is no foot and only the close button", () => {
    const { draw } = sheetSetup();
    const panel = draw("title", []).firstElementChild;
    expect(panel.querySelector(".sheet-foot")).toBe(null);
    expect([...panel.querySelector(".sheet-head-actions").children].map((node) => node.className)).toEqual(["sheet-close"]);
  });

  test("a phone gets the bottom sheet, wider layouts the dialog, read when the sheet is drawn", () => {
    const { layout, draw } = sheetSetup();
    expect(draw("title", []).className).toBe("scrim");
    layout.mode = "wide";
    expect(draw("title", []).className).toBe("scrim dialog");
    layout.mode = "desk";
    expect(draw("title", []).className).toBe("scrim dialog");
    layout.mode = "phone";
    expect(draw("title", []).className).toBe("scrim");
  });

  test("the scrim, the close button and Escape close the sheet, a click inside the panel does not", () => {
    const { window, held, draw } = sheetSetup();
    const factory = () => null;
    const reopen = () => {
      held.sheet = factory;
      return draw("title", ["body"]);
    };
    reopen().querySelector(".sheet-body").click();
    expect(held.sheet).toBe(factory);
    reopen().click();
    expect(held.sheet).toBe(null);
    reopen().querySelector(".sheet-close").click();
    expect(held.sheet).toBe(null);
    const press = (key) =>
      reopen().querySelector(".sheet-title").dispatchEvent(new window.KeyboardEvent("keydown", { key, bubbles: true }));
    press("Enter");
    expect(held.sheet).toBe(factory);
    press("Escape");
    expect(held.sheet).toBe(null);
  });

  test("Escape on a dirty sheet asks instead of closing", () => {
    const { window, held, draw } = sheetSetup({ initial: { sheetForm: { a: 2 }, sheetFormDefault: { a: 1 } } });
    const factory = () => null;
    held.sheet = factory;
    draw("title", []).dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(held.sheet).toBe(factory);
    expect(held.sheetDiscardAsk).toBe(true);
  });
});

describe("the sheet title takes focus through the injected timers", () => {
  test("drawing schedules one zero-delay timer that focuses the title and marks it focused", () => {
    const { window, held, timers, draw } = sheetSetup();
    const scrim = draw("title", []);
    const entries = [...timers.pending];
    expect(entries).toHaveLength(1);
    expect(entries[0][1].ms).toBe(0);
    expect(held.sheetFocused).toBe(false);
    timers.fire(entries[0][0]);
    expect(window.document.activeElement).toBe(scrim.querySelector(".sheet-title"));
    expect(held.sheetFocused).toBe(true);
  });

  test("a title that already took focus is not focused again on a repaint", () => {
    const { window, held, timers, draw } = sheetSetup({ initial: { sheetFocused: true } });
    const scrim = draw("title", []);
    const other = window.document.createElement("input");
    scrim.querySelector(".sheet-body").append(other);
    other.focus();
    const [[id]] = [...timers.pending];
    timers.fire(id);
    expect(window.document.activeElement).toBe(other);
    expect(held.sheetFocused).toBe(true);
  });

  test("the focus timer clears nothing and leaves the flag alone when the title is gone", () => {
    const { held, timers, draw } = sheetSetup();
    const scrim = draw("title", []);
    scrim.querySelector(".sheet-title").remove();
    const [[id]] = [...timers.pending];
    timers.fire(id);
    expect(held.sheetFocused).toBe(false);
    expect(timers.cleared).toEqual([]);
  });
});

describe("openSheet can hand over the close, and the quiet primitives never repaint", () => {
  test("a handover given to openSheet is stored before the repaint and runs on close", () => {
    const { renders, openSheet, closeSheet } = sheetSetup();
    const factory = () => null;
    const closed = [];
    openSheet(factory, () => closed.push("closed"));
    expect(renders).toHaveLength(1);
    expect(renders[0].sheet).toBe(factory);
    expect(typeof renders[0].onSheetClose).toBe("function");
    closeSheet();
    expect(closed).toEqual(["closed"]);
    expect(renders).toHaveLength(1);
  });

  test("openSheet without a handover forgets an earlier one, so closing it cannot run a stale handler", () => {
    const { held, openSheet, closeSheet } = sheetSetup();
    const calls = [];
    held.onSheetClose = () => calls.push("stale");
    openSheet(() => null);
    expect(held.onSheetClose).toBe(null);
    closeSheet();
    expect(calls).toEqual([]);
    expect(held.sheet).toBe(null);
  });

  test("openSheet starts a fresh form and no pending discard question", () => {
    const { held, openSheet, sheetState, isSheetFormDirty } = sheetSetup({
      initial: { sheetForm: { a: 2 }, sheetFormDefault: { a: 1 }, sheetDiscardAsk: true },
    });
    openSheet(() => null);
    expect(held).toMatchObject({ sheetForm: null, sheetFormDefault: null, sheetDiscardAsk: false });
    expect(isSheetFormDirty()).toBe(false);
    expect(sheetState(() => ({ b: 1 }))).toEqual({ b: 1 });
  });

  test("an explicitly undefined handover is stored as none", () => {
    const { held, openSheet } = sheetSetup({ initial: { onSheetClose: () => null } });
    openSheet(() => null, undefined);
    expect(held.onSheetClose).toBe(null);
  });

  test("placeSheet stores the factory without repainting and keeps the focus flag", () => {
    const { held, renders, placeSheet } = sheetSetup({ initial: { sheetFocused: true } });
    const factory = () => null;
    expect(placeSheet(factory)).toBe(undefined);
    expect(held.sheet).toBe(factory);
    expect(held.sheetFocused).toBe(true);
    expect(renders).toEqual([]);
  });

  test("dropSheet forgets the factory, the handover, the form and the discard question without calling or repainting", () => {
    const calls = [];
    const handover = () => calls.push("handover");
    const initial = {
      sheet: () => null,
      onSheetClose: handover,
      sheetForm: { a: 2 },
      sheetFormDefault: { a: 1 },
      sheetDiscardAsk: true,
      sheetFocused: true,
    };
    const { held, renders, dropSheet } = sheetSetup({ initial });
    expect(dropSheet()).toBe(undefined);
    expect(held).toEqual({ sheet: null, onSheetClose: null, sheetForm: null, sheetFormDefault: null, sheetDiscardAsk: false, sheetFocused: true });
    expect(calls).toEqual([]);
    expect(renders).toEqual([]);
  });

  test("dropSheet takes no options, so no caller can keep a stale handover or form", () => {
    const { dropSheet } = sheetSetup();
    expect(dropSheet.length).toBe(0);
  });

  test("a sheet opened after a dropped nested sheet closes to nothing", () => {
    const { held, openSheet, openNestedSheet, dropSheet, closeSheet } = sheetSetup();
    const first = () => null;
    const later = () => null;
    openSheet(first);
    openNestedSheet(() => null);
    dropSheet();
    openSheet(later);
    closeSheet();
    expect(held.sheet).toBe(null);
    expect(held.onSheetClose).toBe(null);
  });

  test("resetSheetForm clears the form and its baseline, so the next sheetState builds afresh", () => {
    const factory = () => null;
    const { held, renders, resetSheetForm, sheetState, isSheetFormDirty } = sheetSetup({
      initial: { sheet: factory, sheetForm: { a: 2 }, sheetFormDefault: { a: 1 } },
    });
    expect(isSheetFormDirty()).toBe(true);
    resetSheetForm();
    expect(held).toMatchObject({ sheet: factory, sheetForm: null, sheetFormDefault: null });
    expect(isSheetFormDirty()).toBe(false);
    expect(sheetState(() => ({ a: 3 }))).toEqual({ a: 3 });
    expect(renders).toEqual([]);
  });
});

describe("openNestedSheet stacks a sheet over the open one", () => {
  test("without an open sheet it opens like openSheet and leaves the close handover alone", () => {
    const { held, renders, openNestedSheet } = sheetSetup({ initial: { sheetFocused: true } });
    const factory = () => null;
    openNestedSheet(factory);
    expect(held.sheet).toBe(factory);
    expect(held.sheetFocused).toBe(false);
    expect(held.onSheetClose).toBe(null);
    expect(renders).toHaveLength(1);
  });

  test("over an open sheet it parks the form and closing brings the first sheet back with its form", () => {
    const { held, renders, openSheet, openNestedSheet, closeSheet } = sheetSetup();
    const first = () => null;
    const second = () => null;
    openSheet(first);
    held.sheetForm = { a: 2 };
    held.sheetFormDefault = { a: 1 };
    held.sheetFocused = true;
    openNestedSheet(second);
    expect(held).toMatchObject({ sheet: second, sheetForm: null, sheetFormDefault: null, sheetFocused: false });
    expect(typeof held.onSheetClose).toBe("function");
    expect(renders).toHaveLength(2);
    held.sheetFocused = true;
    closeSheet();
    expect(held).toMatchObject({ sheet: first, onSheetClose: null, sheetForm: { a: 2 }, sheetFormDefault: { a: 1 }, sheetFocused: false });
    expect(renders).toHaveLength(3);
  });
});

describe("openNestedSheet hands the close back to the sheet underneath", () => {
  test("closing the nested sheet restores the first sheet's own handover, which then runs on its close", () => {
    const { held, openSheet, openNestedSheet, closeSheet } = sheetSetup();
    const first = () => null;
    const calls = [];
    const handover = () => calls.push("first closed");
    openSheet(first, handover);
    openNestedSheet(() => null);
    expect(held.onSheetClose).not.toBe(handover);
    closeSheet();
    expect(held).toMatchObject({ sheet: first, onSheetClose: handover });
    expect(calls).toEqual([]);
    closeSheet();
    expect(calls).toEqual(["first closed"]);
    expect(held.sheet).toBe(null);
  });
});

describe("askConfirmation asks in a sheet and answers once", () => {
  const ask = (setup, extra = {}) => {
    const answers = [];
    setup.askConfirmation({ title: "Sure?", text: "Text", confirmLabel: "Yes", ...extra }, (value) => answers.push(value));
    return answers;
  };

  test("the sheet shows the title, the text, the quote as auto direction and one primary button", () => {
    const setup = sheetSetup();
    ask(setup, { quote: "Quoted" });
    const drawn = setup.held.sheet();
    expect(drawn.querySelector(".sheet-title").textContent).toBe("Sure?");
    expect(drawn.querySelector(".dlg-text").textContent).toBe("Text");
    expect(drawn.querySelector(".dlg-quote").getAttribute("dir")).toBe("auto");
    const buttons = [...drawn.querySelectorAll(".sheet-foot .btn-stack button")];
    expect(buttons.map((button) => [button.className, button.textContent])).toEqual([
      ["btn", "Yes"],
      ["btn ghost", "t:common.cancel"],
    ]);
  });

  test("a destructive question marks its confirm button destructive", () => {
    const setup = sheetSetup();
    ask(setup, { destructive: true });
    expect(setup.held.sheet().querySelector(".sheet-foot .btn-stack button").className).toBe("btn destructive");
  });

  test("confirming clears the sheet and the handover, repaints and then answers true", () => {
    const setup = sheetSetup();
    const seen = [];
    setup.askConfirmation({ title: "Sure?", confirmLabel: "Yes" }, (value) => {
      seen.push({ value, sheet: setup.held.sheet, onSheetClose: setup.held.onSheetClose, renders: setup.renders.length });
    });
    expect(typeof setup.held.onSheetClose).toBe("function");
    expect(setup.renders).toHaveLength(1);
    setup.held.sheet().querySelector(".sheet-foot .btn-stack button").click();
    expect(seen).toEqual([{ value: true, sheet: null, onSheetClose: null, renders: 2 }]);
  });

  test("closing the sheet answers false once, and a later click changes nothing", () => {
    const setup = sheetSetup();
    const answers = ask(setup);
    const drawn = setup.held.sheet();
    setup.closeSheet();
    expect(answers).toEqual([false]);
    const renders = setup.renders.length;
    drawn.querySelector(".sheet-foot .btn-stack button").click();
    expect(answers).toEqual([false]);
    expect(setup.renders).toHaveLength(renders);
  });
});

test("the globals hand out the toast and sheet factories, frozen", () => {
  const globals = shellGlobals();
  expect(Object.isFrozen(globals)).toBe(true);
  expect(Object.keys(globals)).toEqual(["createToast", "createSheets"]);
  expect(globals.createToast).toBe(createToast);
  expect(globals.createSheets).toBe(createSheets);
});
