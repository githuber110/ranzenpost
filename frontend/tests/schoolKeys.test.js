import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const CHILDREN = [
  { key: "a1b2c3d4:c1", child_id: "c1", connection_id: "a1b2c3d4", name: "Mia Example", class_name: "3b" },
  { key: "b2c3d4e5:c1", child_id: "c1", connection_id: "b2c3d4e5", name: "Mia Other", class_name: "7c" },
  { key: "b2c3d4e5:c3", child_id: "c3", connection_id: "b2c3d4e5", name: "Lena Other", class_name: "5a" },
];

function seed(window) {
  window.eval(`
    state.children = ${JSON.stringify(CHILDREN)};
    state.childId = "a1b2c3d4:c1";
    state.config = { connections: [
      { id: "a1b2c3d4", subjects: { D: { label: "German" } }, period_times: { "1": "08:00" }, holiday_region: "DE-NI" },
      { id: "b2c3d4e5", subjects: { D: { label: "Deutsch" } }, period_times: { "1": "07:45" }, holiday_region: "DE-BY" },
    ] };
  `);
}

describe("children of several schools are told apart by their key", () => {
  test("the child pills list every child of every school in order, one pill per key", () => {
    const { window } = loadApp();
    seed(window);
    const bar = window.eval('childPills("b2c3d4e5:c1", () => {})');
    const pills = bar.querySelectorAll(".chip");
    expect(pills.length).toBe(3);
    expect([...pills].map((pill) => pill.getAttribute("aria-pressed"))).toEqual(["false", "true", "false"]);
    expect(pills[0].textContent).toContain("Mia");
    expect(pills[1].textContent).toContain("Mia");
    expect(pills[2].textContent).toContain("Lena");
  });

  test("two children with the same first name and raw id keep separate colours and selection", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval('childColor("a1b2c3d4:c1")')).not.toBe(window.eval('childColor("b2c3d4e5:c1")'));
    window.eval('state.childId = "b2c3d4e5:c1"');
    expect(window.eval("currentChild().name")).toBe("Mia Other");
    expect(window.eval("currentConnectionId()")).toBe("b2c3d4e5");
  });

  test("per school settings follow the school of the shown child", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval("currentConfig().subjects.D.label")).toBe("German");
    expect(window.eval("periodTimes(null)")).toEqual({ "1": "08:00" });
    window.eval('state.childId = "b2c3d4e5:c3"');
    expect(window.eval("currentConfig().subjects.D.label")).toBe("Deutsch");
    expect(window.eval("periodTimes(null)")).toEqual({ "1": "07:45" });
  });

  test("the holiday data of the shown child's school is picked, a lone entry serves as fallback", () => {
    const { window } = loadApp();
    seed(window);
    window.eval('state.holidays = { a1b2c3d4: { status: "ok", days: { "2026-10-05": { free: true } } }, b2c3d4e5: { status: "ok", days: {} } }');
    expect(window.eval('!!holidayDay("2026-10-05")')).toBe(true);
    window.eval('state.childId = "b2c3d4e5:c3"');
    expect(window.eval('!!holidayDay("2026-10-05")')).toBe(false);
    window.eval('state.holidays = { only: { status: "ok", days: { "2026-10-05": { free: true } } } }');
    expect(window.eval('!!holidayDay("2026-10-05")')).toBe(true);
  });

  test("letter and post keys carry the school so equal ids of two schools never collide", () => {
    const { window } = loadApp();
    seed(window);
    const keyOf = window.eval("(function (letter) { return letterKey(letter); })");
    expect(keyOf({ key: "b2c3d4e5:l1:r1", letter_id: "l1", recipient_id: "r1", connection_id: "b2c3d4e5" })).toBe("b2c3d4e5:l1:r1");
    expect(keyOf({ letter_id: "l1", recipient_id: "r1", connection_id: "a1b2c3d4" })).toBe("a1b2c3d4:l1:r1");
    expect(keyOf({ letter_id: "l1", recipient_id: "r1" })).toBe("l1:r1");
    const tile = window.eval("(function (tile) { return tileKey(tile); })");
    expect(tile({ id: 7, key: "b2c3d4e5:7" })).toBe("b2c3d4e5:7");
    expect(tile({ id: 7 })).toBe("7");
    const identity = window.eval("(function (letter) { return letterIdentity(letter); })");
    expect(identity({ letter_id: "l1", recipient_id: "r1", connection_id: "b2c3d4e5" })).toEqual({
      connection_id: "b2c3d4e5",
      letter_id: "l1",
      recipient_id: "r1",
    });
  });

  test("the global config payload never carries per school settings", () => {
    const { window } = loadApp();
    seed(window);
    window.eval('state.config.language = "en"; state.config.notify_services = ["notify.phone"];');
    expect(window.eval("globalConfigPayload()")).toEqual({ language: "en", notify_services: ["notify.phone"] });
  });
});
