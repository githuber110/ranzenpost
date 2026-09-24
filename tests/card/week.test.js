import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiCallsFor, makeHass } from "./fakeHass.js";
import { freezeClock, loadCard, mountCard, texts } from "./loadCard.js";

beforeEach(async () => {
  freezeClock();
  await loadCard();
});

afterEach(() => {
  vi.useRealTimers();
});

function holidayHass(start, end, name = "Test holidays") {
  const hass = makeHass();
  const inner = hass.callApi.bind(hass);
  hass.callApi = async (method, path) => {
    if (path.startsWith("calendars/calendar.ranzenpost_school_holidays?")) {
      return [{ summary: name, uid: "holiday-test", start: { date: start }, end: { date: end }, cancelled: false, color: "" }];
    }
    return inner(method, path);
  };
  return hass;
}

describe("week view", () => {
  it("builds the timetable grid of the app with day heads, hour column and placed cells", async () => {
    const hass = makeHass();
    const card = await mountCard({ view: "week", child: "alex" }, hass);
    const root = card.shadowRoot;
    const cellOf = (uid) => root.querySelector(`.tt-cell[data-uid="${uid}"]`);

    expect(root.querySelector(".tt-child-head .avatar").textContent).toBe("A");
    expect(root.querySelector(".tt-child-head .avatar").style.background).toBe("rgb(14, 107, 112)");
    expect(root.querySelector(".tt-child-head .who").textContent).toBe("Alex");
    expect(texts(root, ".tt-head .n")).toEqual(["31", "01", "02", "03", "04"]);
    expect(texts(root, ".tt-head .d").map((label) => label.replace(/\.$/, ""))).toEqual(["Mo", "Di", "Mi", "Do", "Fr"]);
    expect([...root.querySelectorAll(".tt-head")].map((node) => node.classList.contains("today"))).toEqual([
      false,
      false,
      true,
      false,
      false,
    ]);
    expect([...root.querySelectorAll(".tt-head")].map((node) => node.style.gridColumn)).toEqual(["2", "3", "4", "5", "6"]);
    expect(texts(root, ".tt-hour b")).toEqual(["08:00", "09:00", "09:50", "11:40"]);
    expect(texts(root, ".tt-hour span")).toEqual(["08:45", "09:45", "10:35", "12:25"]);
    expect(cellOf("lesson-20260902-p1@sample").dataset.day).toBe("2026-09-02");
    expect(cellOf("lesson-20260902-p1@sample").style.gridColumn).toBe("4");
    expect(cellOf("lesson-20260902-p1@sample").style.gridRow).toBe("3");
    expect(cellOf("lesson-20260903-p1@sample").style.gridColumn).toBe("5");
    expect(cellOf("lesson-20260903-p1@sample").style.gridRow).toBe("2");
    expect(cellOf("lesson-20260904-p1@sample").style.gridColumn).toBe("6");
    expect(root.querySelectorAll(".tt-cell.free")).toHaveLength(15);
    expect(root.querySelectorAll(".tt-cell.free[data-day='2026-09-01']")).toHaveLength(4);
    expect(root.querySelector(".tt-hol")).toBeNull();
  });

  it("colours the subjects, strikes cancelled lessons with the cross and marks exams", async () => {
    const card = await mountCard({ view: "week", child: "alex" }, makeHass());
    const root = card.shadowRoot;
    const cellOf = (uid) => root.querySelector(`.tt-cell[data-uid="${uid}"]`);
    const maths = cellOf("lesson-20260902-p1@sample");
    const art = cellOf("lesson-20260902-p4@sample");
    const biology = cellOf("lesson-20260903-p1@sample");

    expect(maths.classList.contains("subject-bar")).toBe(true);
    expect(maths.classList.contains("subject")).toBe(true);
    expect(maths.style.getPropertyValue("--subject-bar")).toBe("#a3bae8");
    expect(maths.style.getPropertyValue("--subject-cell-fill")).toBe("#3366cc");
    expect(maths.style.getPropertyValue("--subject-cell-ink")).toBe("#ffffff");
    expect(maths.querySelector(".sub").textContent).toBe("MA");
    expect(maths.querySelector(".room")).toBeNull();
    expect(art.classList.contains("out")).toBe(true);
    expect(art.classList.contains("subject-bar")).toBe(false);
    expect(art.querySelector(".sub").textContent).toBe("AR");
    expect(art.querySelector(".room").textContent).toBe("Entfällt");
    expect(biology.classList.contains("marked")).toBe(true);
    expect(biology.querySelector(".exam-flag .ico")).not.toBeNull();
    expect(biology.querySelector(".exam-flag").getAttribute("title")).toBe("Prüfung");
    expect(maths.querySelector(".exam-flag")).toBeNull();
    const style = root.querySelector("style").textContent;
    expect(style).toContain('.tt-cell.out::after { content: "×";');
    expect(style).toContain(".tt-cell.out .sub { color: var(--ink-3); text-decoration: line-through;");
    expect(style).toContain(".tt-cell.subbed::after { content: \"\"; position: absolute; inset-block-start: 5px; inset-inline-end: 5px; inline-size: 9px; block-size: 9px; border-radius: 50%; background: var(--warn); }");
  });

  it("marks a substitution with the bar, the short label and no subject colour", async () => {
    const card = await mountCard({ view: "week", child: "alex" }, makeHass());
    const cell = card.shadowRoot.querySelector('.tt-cell[data-uid="lesson-20260902-p2@sample"]');

    expect(cell.classList.contains("subbed")).toBe(true);
    expect(cell.classList.contains("out")).toBe(false);
    expect(cell.classList.contains("subject-bar")).toBe(false);
    expect(cell.querySelector(".bar")).not.toBeNull();
    expect(cell.querySelector(".sub").textContent).toBe("EN");
    expect(cell.querySelector(".room").textContent).toBe("Vertr.");
    expect(cell.classList.contains("subject")).toBe(false);
    expect(cell.style.getPropertyValue("--subject-cell-fill")).toBe("");
  });

  it("closes with the legend and the stamp line", async () => {
    const card = await mountCard({ view: "week", child: "alex" }, makeHass());
    const root = card.shadowRoot;

    expect(texts(root, ".legend > span")).toEqual(["Vertretung", "×Entfällt"]);
    expect(root.querySelector(".legend i.dot").style.background).toBe("var(--warn)");
    expect(root.querySelector(".legend i.sym").textContent).toBe("×");
    expect(root.querySelector(".stamp").textContent).toBe("Stand 01.09.2026 18:30");
  });

  it("asks the calendars for the school week in the school time zone", async () => {
    const hass = makeHass();
    await mountCard({ view: "week", child: "alex" }, hass);

    const lessons = apiCallsFor(hass, "calendar.ranzenpost_alex_lessons");
    const exams = apiCallsFor(hass, "calendar.ranzenpost_alex_exams");
    const holidays = apiCallsFor(hass, "calendar.ranzenpost_school_holidays");
    expect(lessons).toHaveLength(1);
    expect(exams).toHaveLength(1);
    expect(holidays).toHaveLength(1);
    expect(lessons[0].method).toBe("GET");
    expect(decodeURIComponent(lessons[0].path)).toBe(
      "calendars/calendar.ranzenpost_alex_lessons?start=2026-08-30T22:00:00.000Z&end=2026-09-04T22:00:00.000Z"
    );
  });

  it("shows the coming week on a weekend with five empty rows", async () => {
    vi.setSystemTime(new Date("2026-09-05T10:00:00Z"));
    const card = await mountCard({ view: "week", child: "alex" }, makeHass());
    const root = card.shadowRoot;

    expect(texts(root, ".tt-head .n")).toEqual(["07", "08", "09", "10", "11"]);
    expect(root.querySelectorAll(".tt-hour")).toHaveLength(5);
    expect(root.querySelectorAll(".tt-cell.free")).toHaveLength(25);
    expect(root.querySelector(".empty")).toBeNull();
  });

  it("fills holiday days with the holiday field and dims their day numbers", async () => {
    const card = await mountCard({ view: "week", child: "alex" }, holidayHass("2026-09-03", "2026-09-05"));
    const root = card.shadowRoot;
    const field = root.querySelector(".tt-hol");

    expect(field.classList.contains("full")).toBe(false);
    expect(field.style.gridColumn).toBe("5 / span 2");
    expect(field.style.gridRow).toBe("2 / span 3");
    expect(field.querySelector(".name").textContent).toBe("Test holidays");
    expect(field.querySelector(".meta").textContent).toBe("bis 04.09.");
    expect([...root.querySelectorAll(".tt-head .n")].map((node) => node.classList.contains("off"))).toEqual([false, false, false, true, true]);
    expect(root.querySelector('.tt-cell[data-uid="lesson-20260903-p1@sample"]')).toBeNull();
    expect(root.querySelectorAll(".tt-cell.free[data-day='2026-09-03']")).toHaveLength(0);
    expect(root.querySelector(".legend")).not.toBeNull();
  });

  it("shows a full holiday week as one wide field without a legend", async () => {
    const card = await mountCard({ view: "week", child: "alex" }, holidayHass("2026-08-24", "2026-09-07", "Summer holidays"));
    const root = card.shadowRoot;
    const field = root.querySelector(".tt-hol.full");

    expect(field.style.gridColumn).toBe("2 / span 5");
    expect(field.querySelector(".ico-slot .ico")).not.toBeNull();
    expect(field.querySelector(".tt-hol-text .name").textContent).toBe("Summer holidays");
    expect(field.querySelector(".tt-hol-text .meta").textContent).toBe("24.08. – 06.09.");
    expect(root.querySelectorAll(".tt-cell")).toHaveLength(0);
    expect(root.querySelector(".legend")).toBeNull();
    expect(root.querySelector(".stamp")).not.toBeNull();
  });
});
