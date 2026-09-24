import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("empty state icon", () => {
  test("the icon leaves its size to the stylesheet so the round plate keeps a drawing area", () => {
    const { window } = loadApp();
    const block = window.eval('emptyBlock("letters", "Nothing here", "Come back later")');
    const svg = block.querySelector(".ico-slot > svg.ico");
    expect(svg).not.toBeNull();
    expect(svg.getAttribute("style")).toBeNull();
  });

  test("a button icon still carries its explicit size", () => {
    const { window } = loadApp();
    const small = window.eval('icon("alert", 16)');
    expect(small.querySelector("svg").getAttribute("style")).toContain("width:16px");
  });
});
