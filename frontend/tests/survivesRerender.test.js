import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

async function quiet(window) {
  for (let round = 0; round < 6; round += 1) await settle();
  window.clearTimeout(window.eval("bootWatchdog"));
}

function openSubjectsSheet(window) {
  window.eval(`
    state.config = { subjects: { D: { label: "Deutsch", color: "" }, M: { label: "Mathe", color: "" } } };
    openSheet(namesSheet);
  `);
}

describe("[W7] state that a rerender must not lose", () => {
  test("the sheet body keeps its scroll position when a toast repaints the screen", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    openSubjectsSheet(window);

    const body = document.querySelector(".sheet-body");
    expect(body).not.toBeNull();
    body.scrollTop = 240;

    window.eval('toast("x")');

    const after = document.querySelector(".sheet-body");
    expect(after).not.toBeNull();
    expect(after.scrollTop).toBe(240);
  });

  test("the sheet title takes focus once, not again on every repaint", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    openSubjectsSheet(window);
    await settle();
    expect(window.eval("state.sheetFocused")).toBe(true);

    const other = document.querySelector(".sheet-body input");
    expect(other).not.toBeNull();
    other.focus();
    window.eval("rerender()");
    await settle();

    expect(document.activeElement.classList.contains("sheet-title")).toBe(false);
  });

  test("the colour dialog hangs inside the sheet scrim and is closed by a repaint", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    openSubjectsSheet(window);

    document.querySelector(".swatch-trigger").click();
    const dialog = document.querySelector(".color-dialog-scrim");
    expect(dialog).not.toBeNull();
    expect(dialog.closest(".scrim")).not.toBeNull();
    expect(window.eval("typeof state.colorDialogClose")).toBe("function");

    window.eval("rerender()");
    expect(document.querySelector(".color-dialog-scrim")).toBeNull();
    expect(window.eval("state.colorDialogClose")).toBeNull();
  });

  test("a dirty settings draft survives a tap next to the sheet", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    openSubjectsSheet(window);

    const input = document.querySelector(".sheet-body input");
    input.value = "Deutsch LK";
    input.dispatchEvent(new window.Event("input"));
    expect(window.eval("isSheetFormDirty()")).toBe(true);

    document.querySelector(".scrim").click();

    expect(window.eval("state.sheet")).not.toBeNull();
    expect(window.eval("state.sheetForm.subjects.D.label")).toBe("Deutsch LK");
    expect(document.querySelector(".sheet-confirm")).not.toBeNull();

    const keep = [...document.querySelectorAll(".sheet-confirm button")].find(
      (node) => node.textContent.trim() === window.eval('t("sheet.discard.keep")')
    );
    keep.click();
    expect(document.querySelector(".sheet-confirm")).toBeNull();
    expect(window.eval("state.sheetForm.subjects.D.label")).toBe("Deutsch LK");
  });

  test("a clean settings draft still closes on the first tap", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    openSubjectsSheet(window);

    document.querySelector(".scrim").click();

    expect(window.eval("state.sheet")).toBeNull();
    expect(window.eval("state.sheetForm")).toBeNull();
  });

  test("the bulk progress lives in state, so the selection bar keeps showing it", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    window.eval(`
      state.view = "post";
      state.postTab = "letters";
      state.lettersTab = "current";
      state.letters = { tab: "current", letters: [{ letter_id: "1", recipient_id: "1", title: "A" }] };
      state.lettersSelectMode = true;
      state.lettersSelected = ["1:1"];
      state.bulkProgress = { done: 1, total: 3 };
      rerender();
    `);

    const bar = document.querySelector(".select-bar");
    expect(bar).not.toBeNull();
    expect(bar.getAttribute("aria-busy")).toBe("true");
    expect(bar.textContent).toContain(
      window.eval('t("common.bulkProgress", { done: formatNumber(1), total: formatNumber(3) })')
    );

    window.eval("rerender()");
    expect(document.querySelector(".select-bar").getAttribute("aria-busy")).toBe("true");
  });

  test("the technical sheet returns to the sheet it was opened from", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    window.eval(`
      state.children = [{ child_id: "c1", name: "Alex", class_name: "4a" }];
      state.childId = "c1";
      openSheet(childSheet);
    `);
    expect(document.querySelector(".sheet-title").textContent).toBe(window.eval('t("child.sheet")'));

    document.querySelector(".tech-btn").click();
    expect(document.querySelector(".sheet-title").textContent).toContain(
      window.eval('t("common.techDetails")')
    );

    document.querySelector(".sheet-close").click();
    expect(document.querySelector(".sheet-title").textContent).toBe(window.eval('t("child.sheet")'));
  });
});
