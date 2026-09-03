import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("[P121] timetable 'Stand' line shows the time when IServ sends one", () => {
  test("a last_updated with a time component renders date and time", () => {
    const { window } = loadApp();
    window.eval(
      "state.timetable = { lessons: [], last_updated: '22.07.2026 12:25' };"
    );
    const view = window.eval("timetableView()");
    const stamp = view.querySelector(".stamp").textContent;
    expect(stamp).toBe("Stand 22.07.2026 12:25");
  });

  test("a last_updated without a time component stays date-only", () => {
    const { window } = loadApp();
    window.eval(
      "state.timetable = { lessons: [], last_updated: '22.07.2026' };"
    );
    const view = window.eval("timetableView()");
    const stamp = view.querySelector(".stamp").textContent;
    expect(stamp).toBe("Stand 22.07.2026");
  });

  test("showDateTime never reads the value through UTC — a plain Date built from the local fields", () => {
    const { window } = loadApp();
    const result = window.eval("showDateTime('01.03.2026 23:50')");
    expect(result).toBe("01.03.2026 23:50");
  });
});
