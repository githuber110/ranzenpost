import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

let CardClass;

beforeEach(async () => {
  freezeClock();
  CardClass = await loadCard();
  document.body.innerHTML = "";
});

afterEach(() => {
  vi.useRealTimers();
});

async function mountEditor(config, hass = makeHass()) {
  const editor = CardClass.getConfigElement();
  document.body.appendChild(editor);
  editor.setConfig(config);
  editor.hass = hass;
  await editor.settled;
  return editor;
}

function emittedAfterTitle(editor, title) {
  const emitted = [];
  editor.addEventListener("config-changed", (event) => emitted.push(event.detail.config));
  const field = editor.shadowRoot.querySelector("input[name=title]");
  field.value = title;
  field.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
  return emitted.at(-1);
}

function block(root, key) {
  return root.querySelector(`.block[data-block="${key}"]`);
}

describe("visual editor keeps what it does not manage", () => {
  it("keeps visibility, layout, styling and legacy keys", async () => {
    const extra = {
      visibility: [{ condition: "screen", media_query: "(min-width: 0px)" }],
      grid_options: { columns: 12, rows: "auto" },
      card_mod: { style: "ha-card { padding: 0; }" },
      view_layout: { position: "main" },
    };
    const editor = await mountEditor({ type: "custom:ranzenpost-card", blocks: ["today"], children: ["alex"], ...extra });

    expect(emittedAfterTitle(editor, "Schule")).toEqual({ type: "custom:ranzenpost-card", ...extra, title: "Schule", blocks: ["today"], children: ["alex"] });
  });

  it("turns a legacy family view with two days into today and next school day", async () => {
    const editor = await mountEditor({ view: "family" });

    expect(emittedAfterTitle(editor, "Familie").blocks).toEqual([
      { key: "today", size: "compact" },
      { key: "next_day", size: "compact" },
      "letters",
      "noticeboard",
      "holidays",
    ]);
  });

  it("drops a block that only the app overview has", async () => {
    const editor = await mountEditor({ blocks: ["today", "chat"], children: ["alex"] });

    expect([...editor.shadowRoot.querySelectorAll(".block-row.on")].map((row) => row.dataset.block)).toEqual(["today"]);
    expect(emittedAfterTitle(editor, "Schule").blocks).toEqual(["today"]);
  });
});

describe("switch time", () => {
  it("reads 7:30 as half past seven", async () => {
    freezeClock("2026-09-02T05:31:00Z");
    const card = await mountCard({ blocks: [{ key: "today", switch: "7:30" }], children: ["alex"] }, makeHass());

    expect(texts(block(card.shadowRoot, "today"), ".panel-head .section-label")).toEqual(["Morgen"]);
    const editor = await mountEditor({ blocks: [{ key: "today", switch: "7:30" }], children: ["alex"] });
    expect(editor.shadowRoot.querySelector("input[name=switch_time_today]").value).toBe("07:30");
  });

  it("keeps a whole number as minutes after midnight", async () => {
    freezeClock("2026-09-02T05:31:00Z");
    const early = await mountCard({ blocks: [{ key: "today", switch: 450 }], children: ["alex"] }, makeHass());
    expect(texts(block(early.shadowRoot, "today"), ".panel-head .section-label")).toEqual(["Morgen"]);

    const late = await mountCard({ blocks: [{ key: "today", switch: 452 }], children: ["alex"] }, makeHass());
    expect(texts(block(late.shadowRoot, "today"), ".panel-head .section-label")).toEqual(["Heute"]);
  });
});

describe("profiles with the same name", () => {
  it("proposes the name with the school as stub so the editor ticks one profile", async () => {
    const hass = makeHass({ twoSchools: true });
    const stub = await CardClass.getStubConfig(hass);

    expect(stub.children).toEqual(["Alex (Sample School)"]);
    const editor = await mountEditor(stub, hass);
    expect([...editor.shadowRoot.querySelectorAll("input[name=children]:checked")].map((input) => input.value)).toEqual(["Alex (Sample School)"]);
  });
});

describe("YAML with a single value instead of a list", () => {
  it("reads one block and one profile written without a list", async () => {
    const card = await mountCard({ blocks: "today", children: "alex" }, makeHass());

    expect([...card.shadowRoot.querySelectorAll(".block")].map((node) => node.dataset.block)).toEqual(["today"]);
    expect(card.shadowRoot.querySelector(".member")).toBeNull();
    expect(texts(block(card.shadowRoot, "today"), ".row[data-uid] .row-title")).toEqual(["Maths", "English", "Art"]);
  });

  it("refuses another type with a message", () => {
    const card = document.createElement("ranzenpost-card");

    expect(() => card.setConfig({ blocks: { today: true } })).toThrow("“blocks” must be a list.");
    expect(() => card.setConfig({ blocks: ["today"], children: 5 })).toThrow("“children” must be a list.");
  });
});
