import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const base = JSON.parse(fs.readFileSync(path.join(path.resolve(dirname, ".."), "i18n", "de.json"), "utf8"));

function draftForm(window) {
  window.eval('state.children = [{ child_id: "c1", name: "Mia", class_name: "3b" }]; state.childId = "c1";');
  window.eval('state.calendar = { data: { subscriptions: [], holiday_region: "DE-NI", port: 8100 }, error: false };');
  window.eval("state.calendarDraft = calendarNewDraft(state.children[0]);");
  return window.eval("calendarForm(state.calendarDraft)");
}

describe("[P179] the subscription offers the two new parts", () => {
  test("marks and absences stand next to the three existing parts, in backend order", () => {
    const { window } = loadApp();
    const form = draftForm(window);
    const labels = [...form.querySelectorAll(".check span > :first-child")];
    const texts = [...form.querySelectorAll(".check span")].map((node) => node.firstChild.textContent);
    expect(labels.length).toBeGreaterThan(0);
    expect(texts).toEqual([
      base["calendar.subscribe.component.timetable"],
      base["calendar.subscribe.component.school_holidays"],
      base["calendar.subscribe.component.public_holidays"],
      base["calendar.subscribe.component.marks"],
      base["calendar.subscribe.component.absences"],
    ]);
    expect(window.eval("CALENDAR_COMPONENTS")).toEqual([
      "timetable",
      "school_holidays",
      "public_holidays",
      "marks",
      "absences",
    ]);
  });

  test("each new part explains itself in one line", () => {
    const { window } = loadApp();
    const form = draftForm(window);
    const hints = [...form.querySelectorAll(".check small")].map((node) => node.textContent);
    expect(hints).toContain(base["calendar.subscribe.component.marks.hint"]);
    expect(hints).toContain(base["calendar.subscribe.component.absences.hint"]);
  });

  test("ticking the exam part keeps the backend order in the draft", () => {
    const { window } = loadApp();
    const form = draftForm(window);
    const boxes = form.querySelectorAll(".check input");
    boxes[4].checked = true;
    boxes[4].dispatchEvent(new window.Event("change", { bubbles: true }));
    boxes[3].checked = true;
    boxes[3].dispatchEvent(new window.Event("change", { bubbles: true }));
    expect(window.eval("state.calendarDraft.components")).toEqual(["timetable", "marks", "absences"]);
  });
});
