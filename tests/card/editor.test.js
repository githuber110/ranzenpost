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

describe("config editor with blocks", () => {
  it("offers the children and the blocks of the account and emits a blocks config", async () => {
    const editor = await mountEditor({ blocks: ["today", { key: "letters", size: "compact" }], children: ["alex"] });
    const root = editor.shadowRoot;
    const emitted = [];
    editor.addEventListener("config-changed", (event) => emitted.push(event.detail.config));

    expect(texts(root, ".children label")).toEqual(["Alex", "Kim"]);
    expect(checkedValues(root, "children")).toEqual(["alex"]);
    expect([...root.querySelectorAll("input[name=blocks]")].map((input) => input.value)).toEqual([
      "today", "next_lesson", "week", "letters", "noticeboard", "absences", "conferences", "holidays", "changes",
    ]);
    expect(checkedValues(root, "blocks")).toEqual(["today", "letters"]);
    expect(texts(root, ".blocks label .hint")[0]).toBe("Stunden von heute, Änderungen, Schulschluss.");
    expect([...root.querySelectorAll(".size-row")].map((row) => row.dataset.block)).toEqual(["today", "letters"]);
    expect(root.querySelector("select[name=size_letters]").value).toBe("compact");

    tick(root, "input[name=blocks][value=holidays]", true);
    expect(emitted.at(-1)).toEqual({ type: "custom:ranzenpost-card", blocks: ["today", { key: "letters", size: "compact" }, "holidays"], children: ["alex"] });
    expect([...root.querySelectorAll(".size-row")].map((row) => row.dataset.block)).toEqual(["today", "letters", "holidays"]);

    change(root, "select[name=size_holidays]", "normal");
    expect(emitted.at(-1).blocks).toEqual(["today", { key: "letters", size: "compact" }, { key: "holidays", size: "normal" }]);

    tick(root, "input[name=blocks][value=today]", false);
    expect(emitted.at(-1).blocks).toEqual([{ key: "letters", size: "compact" }, { key: "holidays", size: "normal" }]);
    expect(root.querySelector('.size-row[data-block="today"]')).toBeNull();

    change(root, "input[name=title]", "Schule");
    expect(emitted.at(-1).title).toBe("Schule");
    tick(root, "input[name=children][value=kim]", true);
    expect(emitted.at(-1).children).toEqual(["alex", "kim"]);
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
    expect(root.querySelector("label[for=size_today]").textContent).toBe("Size of Today");
  });

  it("registers the card and proposes the first child with two blocks as stub config", async () => {
    const registered = window.customCards.filter((card) => card.type === "ranzenpost-card");

    expect(registered).toHaveLength(1);
    expect(registered[0].name).toBe("Ranzenpost");
    expect(registered[0].preview).toBe(true);
    expect(await CardClass.getStubConfig(makeHass())).toEqual({ blocks: ["today", "next_lesson"], children: ["alex"] });

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
      expect(form.schema.map((entry) => entry.name)).toEqual(["title", "children", "blocks", "size_today", "size_letters"]);
      expect(form.schema[2].selector.select.multiple).toBe(true);
      expect(form.schema[2].selector.select.options.map((option) => option.value)).toContain("holidays");
      expect(form.schema[2].selector.select.options[0].description).toBe("Stunden von heute, Änderungen, Schulschluss.");
      expect(form.schema[3].selector.select.options.map((option) => option.value)).toEqual(["compact", "normal"]);
      expect(form.data).toEqual({ title: "Schule", children: ["alex"], blocks: ["today", "letters"], size_today: "normal", size_letters: "normal" });
      expect(form.computeLabel(form.schema[2])).toBe("Bausteine");
      expect(form.computeHelper(form.schema[2])).toBe("Nur Bausteine der Module, die dein Konto hat.");
      expect(form.computeHelper(form.schema[3])).toBe("Stunden von heute, Änderungen, Schulschluss.");

      const emitted = [];
      editor.addEventListener("config-changed", (event) => emitted.push(event.detail.config));
      form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { title: "Schule", children: ["alex"], blocks: ["letters", "week"], size_letters: "compact", size_today: "normal" } }, bubbles: true, composed: true }));
      expect(emitted.at(-1)).toEqual({ type: "custom:ranzenpost-card", title: "Schule", blocks: [{ key: "letters", size: "compact" }, "week"], children: ["alex"] });
      expect(editor.shadowRoot.querySelector("ha-form")).toBe(form);
      expect(form.schema.map((entry) => entry.name)).toEqual(["title", "children", "blocks", "size_letters", "size_week"]);
      expect(form.data.size_week).toBe("normal");
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
