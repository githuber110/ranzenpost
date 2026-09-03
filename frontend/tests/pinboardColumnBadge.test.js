import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderPostRow(window, tile, insideFolder) {
  const run = window.eval(
    "(function (tile, insideFolder) { return postRow(tile, insideFolder, ''); })"
  );
  return run(tile, insideFolder);
}

describe("[P144] pinboard rows show the column/area with visible contrast", () => {
  test("two same-titled tiles in different columns are distinguishable at a glance", () => {
    const { window } = loadApp();
    const tileA = { id: 1, title: "September 2025", column_title: "Einladungen", unread: false };
    const tileB = { id: 2, title: "September 2025", column_title: "Protokolle", unread: false };
    const rowA = renderPostRow(window, tileA, false);
    const rowB = renderPostRow(window, tileB, false);
    expect(rowA.textContent).toContain("Einladungen");
    expect(rowB.textContent).toContain("Protokolle");
  });

  test("the column badge is visible text content, not hidden or aria-only", () => {
    const { window } = loadApp();
    const tile = { id: 1, title: "September 2025", column_title: "Einladungen", unread: false };
    const row = renderPostRow(window, tile, false);
    const badge = Array.from(row.querySelectorAll(".row-tags .tag")).find((el) => el.textContent === "Einladungen");
    expect(badge).toBeTruthy();
    expect(badge.getAttribute("aria-hidden")).not.toBe("true");
    expect(badge.hasAttribute("hidden")).toBe(false);
    expect((badge.getAttribute("style") || "")).not.toMatch(/display:\s*none/);
    expect(badge.classList.contains("soft")).toBe(false);
  });

  test("the column badge stays visible inside the folder view too", () => {
    const { window } = loadApp();
    const tile = { id: 1, title: "September 2025", column_title: "Anwesenheitslisten", unread: false };
    const row = renderPostRow(window, tile, true);
    const badge = Array.from(row.querySelectorAll(".row-tags .tag")).find((el) => el.textContent === "Anwesenheitslisten");
    expect(badge).toBeTruthy();
  });

  test("no tags block when the tile has neither folder nor column title", () => {
    const { window } = loadApp();
    const tile = { id: 1, title: "September 2025", unread: false };
    const row = renderPostRow(window, tile, false);
    expect(row.querySelector(".row-tags")).toBeNull();
  });
});
