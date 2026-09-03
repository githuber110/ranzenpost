import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function metas(document) {
  return {
    light: document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: light)"]'),
    dark: document.querySelector('meta[name="theme-color"][media="(prefers-color-scheme: dark)"]'),
  };
}

describe("setTheme keeps theme-color in sync with the manual toggle", () => {
  test("setTheme('dark') forces both metas to the dark color", () => {
    const { window, document } = loadApp();
    window.setTheme("dark");
    const { light, dark } = metas(document);
    expect(light.getAttribute("content")).toBe("#0e1412");
    expect(dark.getAttribute("content")).toBe("#0e1412");
  });

  test("setTheme('light') forces both metas to the light color", () => {
    const { window, document } = loadApp();
    window.setTheme("light");
    const { light, dark } = metas(document);
    expect(light.getAttribute("content")).toBe("#e4eae8");
    expect(dark.getAttribute("content")).toBe("#e4eae8");
  });

  test("setTheme('system') restores the original media-query-driven values", () => {
    const { window, document } = loadApp();
    window.setTheme("dark");
    window.setTheme("system");
    const { light, dark } = metas(document);
    expect(light.getAttribute("content")).toBe("#e4eae8");
    expect(dark.getAttribute("content")).toBe("#0e1412");
  });
});
