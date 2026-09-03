import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("isoDate local-date semantics", () => {
  test("formats the local calendar date, not the UTC date", () => {
    const { window } = loadApp();
    const isoDate = window.eval("isoDate");
    expect(isoDate(new Date(2026, 0, 1, 0, 5))).toBe("2026-01-01");
    expect(isoDate(new Date(2026, 8, 2, 0, 0, 1))).toBe("2026-09-02");
    expect(isoDate(new Date(2026, 11, 31, 23, 59))).toBe("2026-12-31");
  });
});
