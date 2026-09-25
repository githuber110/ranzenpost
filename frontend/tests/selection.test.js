import { describe, expect, test } from "vitest";
import { JSDOM } from "jsdom";
import { createDom } from "../lib/dom.js";
import { ENTER_PULSE_MS, SELECTION_AREAS, SELECTION_KEYS, createSelection, selectionGlobals } from "../lib/selection.js";

function setup(initial = {}) {
  const { window } = new JSDOM("<!doctype html><html><body></body></html>");
  const held = { lettersSelectMode: false, lettersSelected: [], pinboardSelectMode: false, pinboardSelected: [], ...initial };
  const heard = [];
  const slot = {
    read: (key) => held[key],
    patch: (partial) => {
      heard.push(Object.keys(partial));
      Object.assign(held, partial);
    },
  };
  const renders = [];
  const pulses = [];
  const progress = { value: null };
  const selection = createSelection({
    slot,
    rerender: () => renders.push(held.lettersSelected.slice()),
    vibrate: (ms) => pulses.push(ms),
    progress: () => progress.value,
    t: (key, vars) => (vars ? `${key} ${JSON.stringify(vars)}` : key),
    tCount: (key, count) => `${key}#${count}`,
    formatNumber: (value) => `n${value}`,
    dom: createDom({ page: window.document }),
  });
  return { window, held, heard, renders, pulses, progress, selection };
}

describe("the selection module names its areas and hands out only its factory", () => {
  test("the letter and noticeboard areas own two keys each, mode first", () => {
    expect(SELECTION_AREAS).toEqual({
      letters: { mode: "lettersSelectMode", selected: "lettersSelected" },
      pinboard: { mode: "pinboardSelectMode", selected: "pinboardSelected" },
    });
    expect(SELECTION_KEYS).toEqual(["lettersSelectMode", "lettersSelected", "pinboardSelectMode", "pinboardSelected"]);
    expect(Object.keys(selectionGlobals())).toEqual(["createSelection"]);
    expect(Object.isFrozen(setup().selection)).toBe(true);
    expect(Object.keys(setup().selection.letters)).toEqual(["toggleMode", "enter", "exit", "reset", "toggleItem", "keepVisible", "bar"]);
  });
});

describe("an area changes its keys through the slot and repaints once per user step", () => {
  test("toggling the mode clears the list in one write and repaints", () => {
    const { held, heard, renders, selection } = setup({ lettersSelected: ["x"] });
    selection.letters.toggleMode();
    expect([held.lettersSelectMode, held.lettersSelected]).toEqual([true, []]);
    expect(heard).toEqual([["lettersSelectMode", "lettersSelected"]]);
    expect(renders).toHaveLength(1);
    selection.letters.toggleMode();
    expect(held.lettersSelectMode).toBe(false);
  });

  test("entering selects the pressed item, pulses once and does nothing while already selecting", () => {
    const { held, heard, renders, pulses, selection } = setup();
    selection.pinboard.enter(7);
    expect([held.pinboardSelectMode, held.pinboardSelected]).toEqual([true, [7]]);
    expect(pulses).toEqual([ENTER_PULSE_MS]);
    expect(ENTER_PULSE_MS).toBe(12);
    selection.pinboard.enter(8);
    expect(held.pinboardSelected).toEqual([7]);
    expect(heard).toEqual([["pinboardSelectMode", "pinboardSelected"]]);
    expect(renders).toHaveLength(1);
    expect(pulses).toHaveLength(1);
  });

  test("toggling an item replaces the list instead of changing it", () => {
    const { held, heard, selection } = setup({ lettersSelectMode: true });
    selection.letters.toggleItem("a");
    selection.letters.toggleItem("b");
    const before = held.lettersSelected;
    selection.letters.toggleItem("a");
    expect(before).toEqual(["a", "b"]);
    expect(held.lettersSelected).toEqual(["b"]);
    expect(heard).toEqual([["lettersSelected"], ["lettersSelected"], ["lettersSelected"]]);
  });

  test("exit clears and repaints, reset clears without a repaint, resetAll clears both areas in one write", () => {
    const { held, heard, renders, selection } = setup({
      lettersSelectMode: true,
      lettersSelected: ["a"],
      pinboardSelectMode: true,
      pinboardSelected: [1],
    });
    selection.letters.reset();
    expect(renders).toHaveLength(0);
    selection.pinboard.exit();
    expect(renders).toHaveLength(1);
    expect(heard).toEqual([["lettersSelectMode", "lettersSelected"], ["pinboardSelectMode", "pinboardSelected"]]);
    Object.assign(held, { lettersSelectMode: true, lettersSelected: ["a"], pinboardSelectMode: true, pinboardSelected: [1] });
    selection.resetAll();
    expect(heard.at(-1)).toEqual(SELECTION_KEYS);
    expect(held).toEqual({ lettersSelectMode: false, lettersSelected: [], pinboardSelectMode: false, pinboardSelected: [] });
    expect(renders).toHaveLength(1);
  });

  test("keepVisible drops hidden items, writes only when something changed and never repaints", () => {
    const { held, heard, renders, selection } = setup({ lettersSelected: ["a", "b", "c"] });
    selection.letters.keepVisible(["c", "a", "z"]);
    expect(held.lettersSelected).toEqual(["a", "c"]);
    selection.letters.keepVisible(["a", "c"]);
    selection.pinboard.keepVisible([]);
    expect(heard).toEqual([["lettersSelected"]]);
    expect(renders).toEqual([]);
  });
});

describe("an area builds its selection bar from the actions it is handed", () => {
  test("the bar counts the selection, disables the actions when empty and ends the selection from its round button", () => {
    const runs = [];
    const { held, selection } = setup({ pinboardSelectMode: true, pinboardSelected: [] });
    const actions = [
      { icon: "check", label: "Read", run: () => runs.push("read") },
      { icon: "restore", label: "Unread", run: () => runs.push("unread") },
    ];
    const empty = selection.pinboard.bar(actions);
    expect([...empty.querySelectorAll(".select-bar-actions button")].map((button) => button.disabled)).toEqual([true, true]);
    held.pinboardSelected = [1, 2];
    const bar = selection.pinboard.bar(actions);
    expect(bar.className).toBe("select-bar");
    expect(bar.getAttribute("aria-busy")).toBe("false");
    expect(bar.querySelector(".select-bar-info > span").textContent).toBe("common.selected#2");
    expect(bar.querySelector(".select-bar-info > span").getAttribute("role")).toBe(null);
    const buttons = [...bar.querySelectorAll(".select-bar-actions button")];
    expect(buttons.map((button) => [button.className, button.type, button.disabled, button.textContent])).toEqual([
      ["btn slim ghost", "button", false, "Read"],
      ["btn slim ghost", "button", false, "Unread"],
    ]);
    expect(buttons.map((button) => button.querySelector("svg") !== null)).toEqual([true, true]);
    buttons[1].click();
    expect(runs).toEqual(["unread"]);
    const cancel = bar.querySelector(".select-bar-cancel");
    expect(cancel.getAttribute("aria-label")).toBe("common.selection.end");
    cancel.click();
    expect([held.pinboardSelectMode, held.pinboardSelected]).toEqual([false, []]);
  });

  test("while a bulk action runs the bar shows its progress and locks the round button", () => {
    const { progress, selection } = setup({ lettersSelectMode: true, lettersSelected: ["a", "b", "c"] });
    progress.value = { done: 1, total: 3 };
    const bar = selection.letters.bar([]);
    expect(bar.getAttribute("aria-busy")).toBe("true");
    expect(bar.querySelector(".select-bar-cancel").disabled).toBe(true);
    const label = bar.querySelector(".select-bar-info > span");
    expect(label.getAttribute("role")).toBe("status");
    expect(label.textContent).toBe('common.bulkProgress {"done":"n1","total":"n3"}');
  });
});
