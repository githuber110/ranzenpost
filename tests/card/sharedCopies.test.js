import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CARD = fs.readFileSync(path.join(ROOT, "custom_components", "ranzenpost", "frontend", "ranzenpost-card.js"), "utf8");
const COLOUR = fs.readFileSync(path.join(ROOT, "frontend", "colour.js"), "utf8");
const BLOCKS = fs.readFileSync(path.join(ROOT, "frontend", "blocks.js"), "utf8");
const COLOUR_START = "const RanzenpostColour = (() => {";
const COLOUR_END = "})();";

function colourModule(source) {
  const lines = source.split("\n");
  const first = lines.findIndex((line) => line.trim() === COLOUR_START);
  expect(first, "colour module start").toBeGreaterThanOrEqual(0);
  const indent = lines[first].slice(0, lines[first].indexOf(COLOUR_START));
  const last = lines.findIndex((line, index) => index > first && line === `${indent}${COLOUR_END}`);
  expect(last, "colour module end").toBeGreaterThan(first);
  return lines.slice(first, last + 1).map((line) => (line.startsWith(indent) ? line.slice(indent.length) : line)).join("\n");
}

function colourApi(source) {
  return vm.runInNewContext(`${colourModule(source)}\nRanzenpostColour`, {});
}

function cardCatalogue() {
  const start = CARD.indexOf("const BLOCK_CATALOGUE = [");
  const end = CARD.indexOf("];", start);
  return vm.runInNewContext(`(${CARD.slice(CARD.indexOf("[", start), end + 1)})`, {});
}

function appBlocks() {
  const context = { window: {} };
  vm.runInNewContext(BLOCKS, context);
  return context.window.RanzenpostBlocks;
}

describe("the card carries exact copies of the app's shared lists", () => {
  it("uses the same colour module as the app", () => {
    expect(colourModule(CARD)).toBe(colourModule(COLOUR));
    const card = colourApi(CARD);
    const app = colourApi(COLOUR);
    expect(JSON.parse(JSON.stringify(card.PALETTE))).toEqual(JSON.parse(JSON.stringify(app.PALETTE)));
    expect(card.tokens("dark")).toEqual(app.tokens("dark"));
  });

  it("offers the same blocks with the same limits as the app", () => {
    const card = cardCatalogue().map(({ scope, ...block }) => block);
    const app = appBlocks().BLOCK_CATALOGUE;
    expect(JSON.parse(JSON.stringify(card))).toEqual(JSON.parse(JSON.stringify(app)));
    expect(cardCatalogue().every((block) => ["child", "family", "school"].includes(block.scope))).toBe(true);
  });
});
