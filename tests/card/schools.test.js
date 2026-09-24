import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CHILDREN, OTHER_CHILDREN, SCHOOL, SECOND_SCHOOL, makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

let CardClass;

beforeEach(async () => {
  freezeClock();
  CardClass = await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

async function mountEditor(config, hass) {
  document.body.innerHTML = "";
  const editor = CardClass.getConfigElement();
  document.body.appendChild(editor);
  editor.setConfig(config);
  editor.hass = hass;
  await editor.settled;
  return editor;
}

describe("two schools in one integration", () => {
  it("resolves a child by its key, by its first name and by first name plus school", async () => {
    const byKey = await mountCard({ view: "today", child: OTHER_CHILDREN[1].id }, makeHass({ twoSchools: true }));
    expect(byKey.shadowRoot.querySelector(".panel-head .section-label").textContent).toBe("Robin");

    const byName = await mountCard({ view: "today", child: "kim" }, makeHass({ twoSchools: true }));
    expect(byName.shadowRoot.querySelector(".panel-head .section-label").textContent).toBe("Kim");

    const bySchool = await mountCard({ view: "today", child: "Alex (Other School)" }, makeHass({ twoSchools: true }));
    expect(bySchool.shadowRoot.querySelector(".panel-head .section-label").textContent).toBe("Alex (Other School)");
    expect(texts(bySchool.shadowRoot, ".row-title")).not.toContain("Maths");

    const first = await mountCard({ view: "today", child: "alex" }, makeHass({ twoSchools: true }));
    expect(first.shadowRoot.querySelector(".panel-head .section-label").textContent).toBe("Alex (Sample School)");
    expect(texts(first.shadowRoot, ".row-title")).toEqual(["Maths", "English", "Art"]);
  });

  it("keeps the plain first name when there is only one school", async () => {
    CardClass.resetCaches();
    const card = await mountCard({ view: "today", child: "alex" }, makeHass());
    expect(card.shadowRoot.querySelector(".panel-head .section-label").textContent).toBe("Alex");
  });

  it("lays the family view out by child, ordered by name, with the school only on a shared name and on the holiday rows", async () => {
    const card = await mountCard({ view: "family" }, makeHass({ twoSchools: true }));
    const root = card.shadowRoot;

    expect(root.querySelectorAll(".tt-school")).toHaveLength(0);
    expect(root.querySelectorAll("ha-card > .panel-head")).toHaveLength(1);
    expect(root.querySelectorAll(".tt-multi")).toHaveLength(1);
    expect([...root.querySelectorAll(".tt-multi .tt-child")].map((node) => node.dataset.child)).toEqual([CHILDREN[0].id, OTHER_CHILDREN[0].id, CHILDREN[1].id, OTHER_CHILDREN[1].id]);
    expect(texts(root, ".tt-child-head .who")).toEqual(["Alex (Sample School)", "Alex (Other School)", "Kim", "Robin"]);
    expect(root.querySelector(".tt-multi").classList.contains("scrolls")).toBe(true);
    const holidays = [...root.querySelectorAll("ha-card > .tt-hol.full")];
    expect(holidays).toHaveLength(2);
    expect(holidays.map((node) => node.querySelector(".meta").textContent.split(" · ")[0])).toEqual(["Sample School", "Other School"]);
  });

  it("shows neither a school head nor a school on the holiday row in the family view of a single school", async () => {
    CardClass.resetCaches();
    const card = await mountCard({ view: "family" }, makeHass());
    const root = card.shadowRoot;
    expect(root.querySelectorAll("ha-card > .panel-head")).toHaveLength(1);
    expect(texts(root, ".tt-child-head .who")).toEqual(["Alex", "Kim"]);
    const holiday = root.querySelector("ha-card > .tt-hol.full");
    expect(holiday.querySelector(".meta").textContent).not.toContain("Sample School");
  });

  it("labels the editor choices with the school only when two children share a first name", async () => {
    const two = await mountEditor({ view: "today", child: "kim" }, makeHass({ twoSchools: true }));
    expect(texts(two.shadowRoot, ".children label")).toEqual([
      "Alex (Sample School)",
      "Alex (Other School)",
      "Kim",
      "Robin",
    ]);
    expect([...two.shadowRoot.querySelectorAll("input[name=children]")].map((node) => node.value)).toEqual([
      "Alex (Sample School)",
      "Alex (Other School)",
      "kim",
      "robin",
    ]);
    CardClass.resetCaches();
    const one = await mountEditor({ view: "today", child: "kim" }, makeHass());
    expect(texts(one.shadowRoot, ".children label")).toEqual(["Alex", "Kim"]);
  });

  it("puts the subject code into week cells and the subject name into today rows", async () => {
    CardClass.resetCaches();
    const week = await mountCard({ view: "week", child: "alex" }, makeHass());
    const cells = texts(week.shadowRoot, ".tt-cell .sub");
    expect(cells).toContain("MA");
    expect(cells).toContain("EN");
    expect(cells).toContain("Sport");
    expect(cells).not.toContain("Maths");
    const today = await mountCard({ view: "today", child: "alex" }, makeHass());
    expect(texts(today.shadowRoot, ".row-title")).toEqual(["Maths", "English", "Art"]);
  });
});
