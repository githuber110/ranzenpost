import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("formatEpoch", () => {
  test("formats a unix epoch as a de-DE date and time", () => {
    const { window } = loadApp();
    const text = window.formatEpoch(1700000000);
    expect(text).toMatch(/\d{1,2}\.\d{1,2}\.\d{4}/);
    expect(text).toMatch(/\d{1,2}:\d{2}/);
  });

  test("returns an empty string for falsy or invalid values", () => {
    const { window } = loadApp();
    expect(window.formatEpoch(0)).toBe("");
    expect(window.formatEpoch(null)).toBe("");
    expect(window.formatEpoch(undefined)).toBe("");
    expect(window.formatEpoch("not-a-number")).toBe("");
  });
});

describe("techValue", () => {
  test("renders bool entries as Ja/Nein", () => {
    const { window } = loadApp();
    expect(window.techValue({ kind: "bool", value: true })).toBe("Ja");
    expect(window.techValue({ kind: "bool", value: false })).toBe("Nein");
  });

  test("renders epoch entries through formatEpoch", () => {
    const { window } = loadApp();
    expect(window.techValue({ kind: "epoch", value: 0 })).toBe("");
    expect(window.techValue({ kind: "epoch", value: 1700000000 })).toMatch(/\d{4}/);
  });

  test("passes through other kinds unchanged, including empty values", () => {
    const { window } = loadApp();
    expect(window.techValue({ kind: "text", value: "hello" })).toBe("hello");
    expect(window.techValue({ kind: "text", value: "" })).toBe("");
  });
});

describe("techDetailsButton / techDetailsSheet", () => {
  test("the button carries one class and the expected aria-label", () => {
    const { window } = loadApp();
    const button = window.techDetailsButton([]);
    expect(button.className).toBe("tech-btn");
    expect(button.getAttribute("aria-label")).toBe("Technische Details");
  });

  test("the sheet title reads Technische Details and lists non-empty entries only", () => {
    const { window } = loadApp();
    const entries = [
      { label: "Aktiv", kind: "bool", value: true },
      { label: "Leer", kind: "text", value: "" },
      { label: "Fehlt", kind: "text", value: null },
      { label: "Wert", kind: "text", value: "Hallo" },
    ];
    const sheet = window.techDetailsSheet(entries);
    const text = sheet.textContent;
    expect(text).toContain("Technische Details");
    expect(text).toContain("Aktiv");
    expect(text).toContain("Wert");
    expect(text).not.toContain("Leer");
    expect(text).not.toContain("Fehlt");
  });
});
