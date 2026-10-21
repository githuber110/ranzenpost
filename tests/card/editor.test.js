import { readFileSync } from "node:fs";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ENTRY_ID, SCHOOL, makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, texts } from "./loadCard.js";

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

function change(root, selector, value) {
  const field = root.querySelector(selector);
  field.value = value;
  field.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
}

function tick(root, selector, checked) {
  const box = root.querySelector(selector);
  box.checked = checked;
  box.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
}

function checkedValues(root, name) {
  return [...root.querySelectorAll(`input[name=${name}]:checked`)].map((input) => input.value);
}

function shownRows(root) {
  return [...root.querySelectorAll(".block-row.on")].map((row) => row.dataset.block);
}

describe("config editor with blocks", () => {
  it("offers the children and the blocks of the account and emits a blocks config", async () => {
    const editor = await mountEditor({ blocks: ["today", { key: "letters", size: "compact" }], children: ["alex"] });
    const root = editor.shadowRoot;
    const emitted = [];
    editor.addEventListener("config-changed", (event) => emitted.push(event.detail.config));

    expect(texts(root, ".children label")).toEqual(["Alex", "Kim"]);
    expect(checkedValues(root, "children")).toEqual(["alex"]);
    expect([...root.querySelectorAll("input[name=blocks]")].map((input) => input.value)).toEqual([
      "today", "letters", "next_day", "next_lesson", "week", "noticeboard", "absences", "conferences", "holidays", "changes",
    ]);
    expect(checkedValues(root, "blocks")).toEqual(["today", "letters"]);
    expect(texts(root, ".blocks .block-row .hint")[0]).toBe("Stunden von heute, Änderungen, Schulschluss.");
    expect(shownRows(root)).toEqual(["today", "letters"]);
    expect(root.querySelector("select[name=size_letters]").value).toBe("compact");
    expect(root.querySelector('.block-row:not(.on)[data-block="week"] select')).toBeNull();

    root.querySelector("input[name=blocks][value=holidays]").focus();
    tick(root, "input[name=blocks][value=holidays]", true);
    expect(emitted.at(-1)).toEqual({ type: "custom:ranzenpost-card", blocks: ["today", { key: "letters", size: "compact" }, "holidays"], children: ["alex"] });
    expect(shownRows(root)).toEqual(["today", "letters", "holidays"]);
    expect(root.activeElement).toBe(root.querySelector("input[name=blocks][value=holidays]"));

    change(root, "select[name=size_holidays]", "normal");
    expect(emitted.at(-1).blocks).toEqual(["today", { key: "letters", size: "compact" }, { key: "holidays", size: "normal" }]);

    tick(root, "input[name=blocks][value=today]", false);
    expect(emitted.at(-1).blocks).toEqual([{ key: "letters", size: "compact" }, { key: "holidays", size: "normal" }]);
    expect(shownRows(root)).not.toContain("today");
    expect(root.querySelector("input[name=blocks][value=today]").checked).toBe(false);
    expect(root.querySelector("select[name=size_today]")).toBeNull();

    change(root, "input[name=title]", "Schule");
    expect(emitted.at(-1).title).toBe("Schule");
    tick(root, "input[name=children][value=kim]", true);
    expect(emitted.at(-1).children).toEqual(["alex", "kim"]);
  });

  it("moves blocks up and down so the order needs no code", async () => {
    const editor = await mountEditor({ blocks: ["today", "letters", "holidays"], children: ["alex"] });
    const root = editor.shadowRoot;
    const emitted = [];
    editor.addEventListener("config-changed", (event) => emitted.push(event.detail.config));
    const order = () => shownRows(root);
    const button = (block, move) => root.querySelector(`.block-row.on[data-block="${block}"] .order-move[data-move="${move}"]`);

    expect(root.querySelector(".order-host")).toBeNull();
    expect(order()).toEqual(["today", "letters", "holidays"]);
    expect(button("today", "up").disabled).toBe(true);
    expect(button("holidays", "down").disabled).toBe(true);
    expect(button("letters", "up").getAttribute("aria-label")).toBe("Elternbriefe nach oben");

    button("holidays", "up").focus();
    button("holidays", "up").click();
    expect(emitted.at(-1).blocks).toEqual(["today", "holidays", "letters"]);
    expect(order()).toEqual(["today", "holidays", "letters"]);
    expect(root.activeElement).toBe(button("holidays", "up"));

    button("holidays", "up").click();
    expect(emitted.at(-1).blocks).toEqual(["holidays", "today", "letters"]);
    expect(root.activeElement).toBe(button("holidays", "down"));
  });

  it("offers a field for every option the card reads, apart from the legacy view options", async () => {
    const source = readFileSync(join(process.cwd(), "custom_components", "ranzenpost", "frontend", "ranzenpost-card.js"), "utf8");
    const read = new Set([...source.matchAll(/(?<![.\w])(?:this\._config|config)\.([a-z_]+)/g)].map((match) => match[1]));
    const legacy = new Set(["view", "days", "child"]);
    const editor = await mountEditor({ blocks: ["today", "letters"], children: ["alex"] });
    const emitted = [];
    editor.addEventListener("config-changed", (event) => emitted.push(event.detail.config));
    change(editor.shadowRoot, "input[name=title]", "Schule");
    const offered = new Set(Object.keys(emitted.at(-1)));
    expect([...read].filter((key) => !legacy.has(key) && !offered.has(key))).toEqual([]);
    expect(read.has("blocks") && read.has("title") && read.has("children")).toBe(true);
  });

  it("shows no move buttons for a single block", async () => {
    const editor = await mountEditor({ blocks: ["today"], children: ["alex"] });
    expect(editor.shadowRoot.querySelectorAll(".order-move")).toHaveLength(0);
    expect(editor.shadowRoot.querySelector("select[name=size_today]")).not.toBeNull();
  });

  it("shows one row per block with its name, its size and its moves, and explains each block once", async () => {
    const editor = await mountEditor({ blocks: ["today", "letters"], children: ["alex"] });
    const root = editor.shadowRoot;
    const row = root.querySelector('.block-row.on[data-block="letters"]');
    expect(row.querySelector(".block-name").textContent).toBe("Elternbriefe");
    expect(row.querySelector("select").getAttribute("aria-label")).toBe("Größe von Elternbriefe");
    expect(row.querySelectorAll(".order-move")).toHaveLength(2);
    expect(root.innerHTML.split("Ungelesene Elternbriefe.")).toHaveLength(2);
    expect(root.querySelectorAll(".size-row, .order-list, .sizes")).toHaveLength(0);
    expect(root.querySelectorAll(".blocks")).toHaveLength(1);
  });

  it("hides the profile field while the integration has no profile", async () => {
    const editor = await mountEditor({ blocks: ["letters"] }, makeHass({ childless: true }));
    const root = editor.shadowRoot;
    expect(root.querySelector(".children")).toBeNull();
    expect(root.textContent).not.toContain("Leer lassen für alle Profile");
    expect(root.querySelector("input[name=title]")).not.toBeNull();
    expect(checkedValues(root, "blocks")).toEqual(["letters"]);
  });

  it("turns a legacy view config into blocks on the first change", async () => {
    const editor = await mountEditor({ view: "family", days: 1 });
    const root = editor.shadowRoot;
    const emitted = [];
    editor.addEventListener("config-changed", (event) => emitted.push(event.detail.config));
    expect(checkedValues(root, "blocks")).toEqual(["today", "letters", "noticeboard", "holidays"]);
    expect(root.querySelector("select[name=size_today]").value).toBe("compact");
    change(root, "input[name=title]", "Familie");
    expect(emitted.at(-1)).toEqual({
      type: "custom:ranzenpost-card",
      title: "Familie",
      blocks: [{ key: "today", size: "compact" }, "letters", "noticeboard", "holidays"],
    });
    const single = await mountEditor({ view: "week", child: "kim" });
    expect(checkedValues(single.shadowRoot, "blocks")).toEqual(["week"]);
    expect(checkedValues(single.shadowRoot, "children")).toEqual(["kim"]);
  });

  it("offers no block of a module the schools lack and names the gap in the helper", async () => {
    const hass = makeHass({
      states: {
        "sensor.ranzenpost_school_connection": {
          state: "ok",
          attributes: { modules: { timetable: true, letters: false, pinboard: true, absences: true, conferences: false, messenger: true } },
        },
      },
    });
    const editor = await mountEditor({ blocks: ["today"] }, hass);
    const root = editor.shadowRoot;
    expect([...root.querySelectorAll("input[name=blocks]")].map((input) => input.value)).not.toContain("letters");
    expect([...root.querySelectorAll("input[name=blocks]")].map((input) => input.value)).not.toContain("conferences");
    expect(texts(root, ".field .hint")[1]).toContain("Elternbriefe, Elternsprechtage");
  });

  it("speaks the language of the user", async () => {
    const editor = await mountEditor({ blocks: ["today"] }, makeHass({ language: "en" }));
    const root = editor.shadowRoot;
    expect(root.querySelector("label[for=title]").textContent).toBe("Title");
    expect(texts(root, ".blocks label")[0]).toContain("Today");
    expect(root.querySelector("select[name=size_today]").getAttribute("aria-label")).toBe("Size of Today");
    expect(root.querySelector(".children").closest(".field").querySelector(".lbl").textContent).toBe("Profiles");
  });

  it("registers the card and proposes the first child with two blocks as stub config", async () => {
    const registered = window.customCards.filter((card) => card.type === "ranzenpost-card");

    expect(registered).toHaveLength(1);
    expect(registered[0].name).toBe("Ranzenpost");
    expect(registered[0].preview).toBe(true);
    expect(await CardClass.getStubConfig(makeHass())).toEqual({ blocks: ["today", "next_day"], children: ["alex"] });

    const broken = makeHass();
    broken.callWS = async () => {
      throw new Error("offline");
    };
    CardClass.resetCaches();
    expect(await CardClass.getStubConfig(broken)).toEqual({ blocks: ["today"] });
  });

  it("keeps a focused control in place and adds newly discovered children on later hass updates", async () => {
    const hass = makeHass();
    const originalCallWS = hass.callWS.bind(hass);
    let addRobin = false;
    hass.callWS = async (message) => {
      const result = await originalCallWS(message);
      if (!addRobin) return result;
      if (message.type === "config/entity_registry/list") {
        return [
          ...result,
          {
            entity_id: "sensor.ranzenpost_robin_current_lesson",
            unique_id: `ranzenpost_${ENTRY_ID}_${SCHOOL}:child-3_current_lesson`,
            platform: "ranzenpost",
            device_id: "device-3",
            translation_key: "current_lesson",
          },
        ];
      }
      if (message.type === "config/device_registry/list") {
        return [
          ...result,
          {
            id: "device-3",
            name: "Ranzenpost Robin",
            name_by_user: null,
            via_device_id: "device-school",
            identifiers: [["ranzenpost", `child:${ENTRY_ID}:${SCHOOL}:child-3`]],
          },
        ];
      }
      return result;
    };

    const editor = await mountEditor({ blocks: ["today"], children: ["alex"] }, hass);
    const root = editor.shadowRoot;
    const select = root.querySelector("select[name=size_today]");
    select.focus();
    expect(root.activeElement).toBe(select);

    vi.setSystemTime(new Date("2026-09-02T07:16:01Z"));
    addRobin = true;
    editor.hass = hass;
    await editor.settled;

    expect(root.querySelector("select[name=size_today]")).toBe(select);
    expect(root.activeElement).toBe(select);
    expect(texts(root, ".children label")).toEqual(["Alex", "Kim", "Robin"]);
    expect(checkedValues(root, "children")).toEqual(["alex"]);
  });

  it("uses ha-form with selectors when Home Assistant provides it and never rebuilds the form", async () => {
    class FakeForm extends HTMLElement {}
    customElements.define("ha-form", FakeForm);
    try {
      const editor = await mountEditor({ blocks: ["today", "letters"], children: ["alex"], title: "Schule" });
      const form = editor.shadowRoot.querySelector("ha-form");
      expect(form).not.toBeNull();
      expect(form.schema.map((entry) => entry.name)).toEqual(["title", "children"]);
      expect(form.schema[1].selector.select.multiple).toBe(true);
      expect(form.data).toEqual({ title: "Schule", children: ["alex"] });
      expect(form.computeLabel(form.schema[1])).toBe("Profile");
      expect(form.computeHelper(form.schema[1])).toBe("Leer lassen für alle Profile");
      const root = editor.shadowRoot;
      expect(root.querySelector(".blocks-host .lbl").textContent).toBe("Bausteine");
      expect(root.querySelector(".blocks-host .hint").textContent).toBe("Nur Bausteine der Module, die dein Konto hat.");
      expect(shownRows(root)).toEqual(["today", "letters"]);

      const emitted = [];
      editor.addEventListener("config-changed", (event) => emitted.push(event.detail.config));
      form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { title: "Schulweg", children: ["alex", "kim"] } }, bubbles: true, composed: true }));
      expect(emitted.at(-1)).toEqual({ type: "custom:ranzenpost-card", title: "Schulweg", blocks: ["today", "letters"], children: ["alex", "kim"] });
      tick(root, "input[name=blocks][value=week]", true);
      change(root, "select[name=size_letters]", "compact");
      root.querySelector('.block-row.on[data-block="week"] .order-move[data-move="up"]').click();
      expect(emitted.at(-1)).toEqual({ type: "custom:ranzenpost-card", title: "Schulweg", blocks: ["today", "week", { key: "letters", size: "compact" }], children: ["alex", "kim"] });
      expect(editor.shadowRoot.querySelector("ha-form")).toBe(form);
      expect(form.schema.map((entry) => entry.name)).toEqual(["title", "children"]);

      CardClass.resetCaches();
      const childless = await mountEditor({ blocks: ["letters"] }, makeHass({ childless: true }));
      expect(childless.shadowRoot.querySelector("ha-form").schema.map((entry) => entry.name)).toEqual(["title"]);
    } finally {
      document.body.innerHTML = "";
    }
  });

  it("reports its size per view and per block count", async () => {
    for (const [view, size] of [
      ["today", 4],
      ["week", 6],
      ["family", 5],
    ]) {
      const card = document.createElement("ranzenpost-card");
      card.setConfig({ view, child: "alex" });
      expect(card.getCardSize()).toBe(size);
    }
    const blocks = document.createElement("ranzenpost-card");
    blocks.setConfig({ blocks: ["today", "letters", "holidays"] });
    expect(blocks.getCardSize()).toBe(6);
  });

  it("refuses an unknown block with a translated message", () => {
    const card = document.createElement("ranzenpost-card");
    expect(() => card.setConfig({ blocks: ["today", "bogus"] })).toThrow("Unknown block “bogus”.");
    expect(() => card.setConfig({ blocks: ["chat"] })).toThrow("Unknown block “chat”.");
  });
});
