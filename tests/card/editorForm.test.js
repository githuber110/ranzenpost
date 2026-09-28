import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeHass } from "./fakeHass.js";
import { freezeClock, loadCard } from "./loadCard.js";

let CardClass;
let broken = false;

class FakeForm extends HTMLElement {
  set schema(value) {
    if (broken) throw new Error("selector not available");
    this._schema = value;
  }

  get schema() {
    return this._schema;
  }
}

beforeEach(async () => {
  freezeClock();
  CardClass = await loadCard();
  if (!customElements.get("ha-form")) customElements.define("ha-form", FakeForm);
  document.body.innerHTML = "";
  broken = false;
});

afterEach(() => {
  vi.useRealTimers();
});

async function mountEditor(config) {
  const editor = CardClass.getConfigElement();
  document.body.appendChild(editor);
  editor.setConfig(config);
  editor.hass = makeHass();
  await editor.settled;
  return editor;
}

describe("card editor with Home Assistant's form", () => {
  it("never stays empty when the form cannot be built", async () => {
    broken = true;
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const editor = await mountEditor({ blocks: ["today", "letters"], children: ["alex"] });
    const root = editor.shadowRoot;
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
    expect(root.querySelector("ha-form")).toBeNull();
    expect(root.querySelector("input[name=title]")).not.toBeNull();
    expect(root.querySelectorAll("input[name=blocks]").length).toBeGreaterThan(0);
    expect(root.querySelectorAll(".order-row").length).toBe(2);
  });

  it("keeps the order list next to the form and hands the new order to the form", async () => {
    const editor = await mountEditor({ blocks: ["today", "letters"], children: ["alex"] });
    const root = editor.shadowRoot;
    const form = root.querySelector("ha-form");
    const emitted = [];
    editor.addEventListener("config-changed", (event) => emitted.push(event.detail.config));
    root.querySelector('.order-move[data-block="letters"][data-move="up"]').click();
    expect(emitted.at(-1).blocks).toEqual(["letters", "today"]);
    expect(root.querySelector("ha-form")).toBe(form);
    expect(form.data.blocks).toEqual(["letters", "today"]);
    expect(form.schema.map((entry) => entry.name).slice(3)).toEqual(["size_letters", "size_today"]);
  });
});
