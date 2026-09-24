import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const LEAVE_ENTRY = { id: 7, kind: "leave", student_id: 1, label: "Beurlaubungsantrag", deletable: true };

function openDetail(window, entry) {
  window.eval(`
    (function (entry) {
      state.absence = { data: { children: [{ id: entry.student_id, name: "Mia" }], rules: {} } };
      openAbsenceSheet(entry);
    })
  `)(entry);
}

describe("cancelling the absence withdraw confirmation", () => {
  test("returns to the absence detail sheet, same as deleteEntry does for own entries", async () => {
    const { window } = loadApp();
    openDetail(window, LEAVE_ENTRY);

    await window.eval(`
      (function () {
        const trigger = state.sheet().querySelector(".sheet .btn.destructive");
        trigger.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
        return new Promise((resolve) => window.setTimeout(resolve, 0));
      })()
    `);

    const result = window.eval(`
      (function () {
        const scrim = state.sheet();
        const cancelBtn = scrim.querySelector(".sheet .btn.ghost");
        cancelBtn.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
        return true;
      })()
    `);
    expect(result).toBe(true);
    for (let tick = 0; tick < 4; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));

    const after = window.eval(`
      (function () {
        const scrim = state.sheet ? state.sheet() : null;
        return {
          sheetOpen: !!state.sheet,
          title: scrim ? scrim.querySelector(".sheet-title").textContent : "",
          hasWithdraw: scrim ? !!scrim.querySelector(".sheet .btn.destructive") : false,
        };
      })()
    `);
    expect(after.sheetOpen).toBe(true);
    expect(after.title).toBe("Beurlaubungsantrag");
    expect(after.hasWithdraw).toBe(true);
  });

  test("confirming still withdraws and closes the sheet, unchanged", async () => {
    const { window } = loadApp();
    window.fetch = () =>
      Promise.resolve({
        ok: true,
        headers: { get: () => "application/json" },
        json: () => Promise.resolve({ ok: true }),
      });
    openDetail(window, LEAVE_ENTRY);

    await window.eval(`
      (function () {
        const trigger = state.sheet().querySelector(".sheet .btn.destructive");
        trigger.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
        return new Promise((resolve) => window.setTimeout(resolve, 0));
      })()
    `);

    window.eval(`
      (function () {
        const confirmBtn = state.sheet().querySelector(".sheet .btn.destructive");
        confirmBtn.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
      })()
    `);
    for (let tick = 0; tick < 6; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));

    const sheetOpen = window.eval("!!state.sheet");
    expect(sheetOpen).toBe(false);
  });
});
