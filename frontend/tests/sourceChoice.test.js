import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const CHILD = "s1:c1";

function week(fields) {
  return Object.assign(
    {
      lessons: [],
      start_date: "16.11.2026",
      end_date: "22.11.2026",
      week_offset: 0,
      source: "school-app",
      source_choice: "school-app",
      source_choice_missing: false,
      sources: { "school-app": { changes: 0 }, "time-table": { changes: 26, last_updated: "18.11.2026 13:40" } },
    },
    fields || {}
  );
}

function withSchool(window, data, entry) {
  evalWith(
    window,
    `state.config = { connections: [Object.assign({ id: "s1", course_filters: {}, timetable_both: true, timetable_choice: "" }, testArgs[2] || {})] };
     state.children = [{ key: testArgs[0], child_id: "c1", connection_id: "s1", name: "Kim Muster" }];
     state.childId = testArgs[0];
     state.weekOffset = 0;
     state.timetable = testArgs[1];
     state.overviewWeeks = { [testArgs[0]]: { 0: testArgs[1] } };`,
    CHILD,
    data,
    entry
  );
}

function notice(window) {
  return window.eval("timetableView()").querySelector(".source-note");
}

function posting(window) {
  const posts = [];
  window.fetch = (url, options) => {
    if (options && options.method === "POST") {
      posts.push({ url: String(url), body: JSON.parse(options.body) });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ saved: true }) });
    }
    return Promise.reject(new Error("network disabled in tests"));
  };
  return posts;
}

describe("timetable source setting", () => {
  test("appears for a school with both plans and shows the facts of each", () => {
    const { window } = loadApp();
    withSchool(window, week());
    const rows = window.eval("sourceChoiceSettingRows('s1')");
    expect(rows.length).toBe(1);
    expect(rows[0].querySelector(".lbl").textContent).toBe("Stundenplan aus");
    expect(rows[0].querySelector(".val").textContent).toBe("Neuer Plan");
    const sheet = window.eval("sourceSheet('s1')");
    const options = [...sheet.querySelectorAll(".source-opt")];
    expect(options.map((option) => option.dataset.source)).toEqual(["school-app", "time-table"]);
    expect(options[0].getAttribute("aria-pressed")).toBe("true");
    expect(options[0].textContent).toContain("Diese Woche 0 Änderungen");
    expect(options[1].textContent).toContain("Diese Woche 26 Änderungen");
    expect(options[1].textContent).toContain("aktualisiert");
  });

  test("stays hidden for a school with only one plan", () => {
    const { window } = loadApp();
    withSchool(window, week({ sources: null }), { timetable_both: false });
    expect(window.eval("sourceChoiceSettingRows('s1')")).toEqual([]);
  });

  test("stays visible from the stored school facts when no week is loaded", () => {
    const { window } = loadApp();
    withSchool(window, null, { timetable_choice: "time-table" });
    const rows = window.eval("sourceChoiceSettingRows('s1')");
    expect(rows[0].querySelector(".val").textContent).toBe("Alter Plan (veraltet)");
  });

  test("an unknown count is named unknown, never zero, and gives no hint", () => {
    const { window } = loadApp();
    withSchool(window, week({ sources: { "school-app": { changes: null }, "time-table": { changes: 26 } } }));
    const option = window.eval("sourceSheet('s1')").querySelector('[data-source="school-app"]');
    expect(option.textContent).toContain("Änderungen diese Woche unbekannt");
    expect(option.textContent).not.toContain("0 Änderungen");
    expect(notice(window)).toBeNull();
  });

  test("picking the old plan saves it for the school", async () => {
    const { window } = loadApp();
    withSchool(window, week());
    const posts = posting(window);
    await window.eval("chooseSource('s1', 'time-table')");
    expect(posts[0].url.endsWith("/api/connections/s1")).toBe(true);
    expect(posts[0].body).toEqual({ timetable_choice: "time-table" });
  });
});

describe("timetable source hint", () => {
  test("offers to switch when only the other plan has changes this week", async () => {
    const { window } = loadApp();
    withSchool(window, week());
    const node = notice(window);
    expect(node.textContent).toContain("Im alten Plan stehen diese Woche 26 Änderungen, im gewählten keine.");
    const posts = posting(window);
    node.querySelector(".source-switch").click();
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(posts[0].body).toEqual({ timetable_choice: "time-table" });
  });

  test("stays away while the chosen plan has changes or for another week", () => {
    const { window } = loadApp();
    withSchool(window, week({ sources: { "school-app": { changes: 3 }, "time-table": { changes: 26 } } }));
    expect(notice(window)).toBeNull();
    withSchool(window, week({ week_offset: 1 }));
    expect(notice(window)).toBeNull();
  });

  test("not now at one school leaves the hint of another school alone", () => {
    const { window } = loadApp();
    withSchool(window, week());
    window.eval("writeStoredText('sourceHintDismissed:s2', '16.11.2026')");
    expect(notice(window)).not.toBeNull();
  });

  test("not now hides it for this week only", () => {
    const { window } = loadApp();
    withSchool(window, week());
    notice(window).querySelector(".source-later").click();
    expect(notice(window)).toBeNull();
    withSchool(window, week({ start_date: "23.11.2026" }));
    expect(notice(window)).not.toBeNull();
  });

  test("says so when the chosen old plan cannot be read", () => {
    const { window } = loadApp();
    withSchool(window, week({ source_choice: "time-table", source_choice_missing: true, sources: null }), { timetable_choice: "time-table" });
    expect(notice(window).textContent).toContain("Der gewählte alte Plan ist gerade nicht lesbar");
    expect(window.eval("sourceChoiceSettingRows('s1')")[0].querySelector(".val").textContent).toBe("Alter Plan (veraltet)");
  });
});
