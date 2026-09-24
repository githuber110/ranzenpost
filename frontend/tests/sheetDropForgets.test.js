import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function quiet(window) {
  window.clearTimeout(window.eval("bootWatchdog"));
  for (let round = 0; round < 6; round += 1) await flush();
  window.clearTimeout(window.eval("bootWatchdog"));
}

async function appWithSheetA() {
  const { window, document } = loadApp();
  await quiet(window);
  window.eval("state.account = 'parent.one';");
  window.eval("var sheetA = () => sheet('Sheet A', [techDetailsButton([{ label: 'Value', kind: 'text', value: 'x' }])]);");
  window.eval("openSheet(sheetA)");
  return { window, document };
}

function signInFails(window) {
  const error = window.eval('apiError("auth_failed", { error: "auth_failed", message_key: "api.login.session" })');
  expect(window.eval("handleApiFailure")(error, "c1")).toBe(true);
}

describe("a sheet dropped by a sign-in failure leaves nothing behind for the next sheet", () => {
  test("closing a later plain sheet does not bring back the sheet under the dropped technical details", async () => {
    const { window, document } = await appWithSheetA();
    document.querySelector(".scrim .tech-btn").click();
    expect(window.eval("state.sheet === sheetA")).toBe(false);
    expect(window.eval("typeof state.onSheetClose")).toBe("function");
    signInFails(window);
    expect(window.eval("state.sheet")).toBe(null);
    window.eval("var sheetB = () => sheet('Sheet B', ['b']); openSheet(sheetB)");
    expect(window.eval("state.sheet === sheetB")).toBe(true);
    window.eval("closeSheet()");
    expect(window.eval("state.sheet === sheetA")).toBe(false);
    expect(window.eval("[state.sheet, state.onSheetClose]")).toEqual([null, null]);
  });

  test("a later sheet builds its own form instead of reading the dropped one", async () => {
    const { window } = await appWithSheetA();
    window.eval("sheetState(() => ({ short_name: 'A' })).short_name = 'changed'");
    signInFails(window);
    window.eval("openSheet(() => sheet('Sheet B', ['b']))");
    expect(window.eval("sheetState(() => ({ password: '' }))")).toEqual({ password: "" });
    expect(window.eval("isSheetFormDirty()")).toBe(false);
    window.eval("closeSheet()");
    expect(window.eval("[state.sheet, state.sheetDiscardAsk]")).toEqual([null, false]);
  });

  test("a discard question pending on the dropped sheet does not open over the next one", async () => {
    const { window } = await appWithSheetA();
    window.eval("sheetState(() => ({ short_name: 'A' })).short_name = 'changed'; closeSheet()");
    expect(window.eval("state.sheetDiscardAsk")).toBe(true);
    signInFails(window);
    window.eval("openSheet(() => sheet('Sheet B', ['b']))");
    expect(window.eval("state.sheetDiscardAsk")).toBe(false);
  });

  test("the dropped state is gone right after the drop, before any other sheet opens", async () => {
    const { window } = await appWithSheetA();
    window.eval("var closedA = 0; openSheet(sheetA, () => { closedA += 1; })");
    window.eval("sheetState(() => ({ short_name: 'A' })).short_name = 'changed'; closeSheet()");
    expect(window.eval("state.sheetDiscardAsk")).toBe(true);
    signInFails(window);
    expect(window.eval("closedA")).toBe(0);
    expect(window.eval("[state.sheet, state.onSheetClose, state.sheetForm, state.sheetFormDefault, state.sheetDiscardAsk]")).toEqual([
      null,
      null,
      null,
      null,
      false,
    ]);
  });
});
