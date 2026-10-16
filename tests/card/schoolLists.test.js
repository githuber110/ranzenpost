import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FORUM_ITEMS, INGRESS_PATH, OPEN_TASKS, TEXT_ITEMS, makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

let CardClass;

beforeEach(async () => {
  freezeClock();
  CardClass = await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

function shownBlocks(card) {
  return [...card.shadowRoot.querySelectorAll(".block")].map((node) => node.dataset.block);
}

async function offeredInEditor(hass) {
  document.body.innerHTML = "";
  const editor = CardClass.getConfigElement();
  document.body.appendChild(editor);
  editor.setConfig({ blocks: ["today"] });
  editor.hass = hass;
  await editor.settled;
  return [...editor.shadowRoot.querySelectorAll('input[name="blocks"]')].map((input) => input.value);
}

describe("the tasks and news blocks", () => {
  it("list the open tasks with their due date and the news with category and date", async () => {
    const hass = makeHass({ schoolLists: true });
    const card = await mountCard({ blocks: [{ key: "tasks", size: "normal" }, { key: "news", size: "normal" }], children: ["alex"] }, hass);
    expect(shownBlocks(card)).toEqual(["tasks", "news"]);
    expect(texts(card.shadowRoot, '.block[data-block="tasks"] .row-title')).toEqual(OPEN_TASKS.map((task) => task.title));
    expect(texts(card.shadowRoot, '.block[data-block="tasks"] .row-meta')).toEqual(["04.09.", "10.09."]);
    expect(texts(card.shadowRoot, '.block[data-block="news"] .row-title')).toEqual(["Library opens later"]);
    expect(texts(card.shadowRoot, '.block[data-block="news"] .row-sub')).toEqual(["General"]);
    expect(card.shadowRoot.querySelector('.block[data-block="tasks"] .row-title').getAttribute("dir")).toBe("auto");
  });

  it("open the app's views from their heads", async () => {
    const hass = makeHass({ schoolLists: true });
    const card = await mountCard({ blocks: ["tasks", "news"], children: ["alex"] }, hass);
    expect(card.shadowRoot.querySelector('.block[data-block="tasks"] .panel-link').getAttribute("href")).toBe(`${INGRESS_PATH}?view=tasks`);
    expect(card.shadowRoot.querySelector('.block[data-block="news"] .panel-link').getAttribute("href")).toBe(`${INGRESS_PATH}?view=news`);
  });

  it("show for an account without a child", async () => {
    const hass = makeHass({ childless: true, schoolLists: true });
    const card = await mountCard({ blocks: ["tasks", "news"] }, hass);
    expect(shownBlocks(card)).toEqual(["tasks", "news"]);
  });

  it("render nothing and are not offered while the school lacks the modules", async () => {
    const hass = makeHass();
    const card = await mountCard({ blocks: ["tasks", "news"], children: ["alex"] }, hass);
    expect(shownBlocks(card)).toEqual([]);
    expect(await offeredInEditor(makeHass())).not.toContain("tasks");
    expect(await offeredInEditor(makeHass({ schoolLists: true }))).toEqual(expect.arrayContaining(["tasks", "news"]));
  });
});

describe("the forum block", () => {
  it("lists the forums with unread posts and opens the app's forum view", async () => {
    const hass = makeHass({ schoolLists: true });
    const card = await mountCard({ blocks: [{ key: "forums", size: "normal" }], children: ["alex"] }, hass);
    expect(shownBlocks(card)).toEqual(["forums"]);
    expect(texts(card.shadowRoot, '.block[data-block="forums"] .row-title')).toEqual(FORUM_ITEMS.map((item) => item.title));
    expect(texts(card.shadowRoot, '.block[data-block="forums"] .row-sub')).toEqual(["General forums"]);
    expect(card.shadowRoot.querySelector('.block[data-block="forums"] .panel-link').getAttribute("href")).toBe(`${INGRESS_PATH}?view=forums`);
  });

  it("is offered only while the school confirmed the forum module", async () => {
    expect(await offeredInEditor(makeHass())).not.toContain("forums");
    expect(await offeredInEditor(makeHass({ schoolLists: true }))).toContain("forums");
    expect(await offeredInEditor(makeHass({ schoolLists: true }))).not.toContain("infodisplay");
  });
});

describe("the text block", () => {
  it("lists the texts with owner and date and opens the app's text view", async () => {
    const hass = makeHass({ schoolLists: true });
    const card = await mountCard({ blocks: [{ key: "texts", size: "normal" }], children: ["alex"] }, hass);
    expect(shownBlocks(card)).toEqual(["texts"]);
    expect(texts(card.shadowRoot, '.block[data-block="texts"] .row-title')).toEqual(TEXT_ITEMS.map((item) => item.title));
    expect(texts(card.shadowRoot, '.block[data-block="texts"] .row-sub')).toEqual(["Class teacher"]);
    expect(card.shadowRoot.querySelector('.block[data-block="texts"] .panel-link').getAttribute("href")).toBe(`${INGRESS_PATH}?view=texts`);
    expect(await offeredInEditor(makeHass())).not.toContain("texts");
    expect(await offeredInEditor(makeHass({ schoolLists: true }))).toContain("texts");
  });
});
