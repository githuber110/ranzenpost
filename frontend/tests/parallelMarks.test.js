import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const MATHS = { date: "2026-09-02", period: 3, subject_code: "MA", subject_label: "Mathe" };
const GERMAN = { date: "2026-09-02", period: 3, subject_code: "D", subject_label: "Deutsch" };

function withEntries(marks, cancellations) {
  const { window } = loadApp();
  window.testMarks = marks;
  window.testCancellations = cancellations;
  window.eval(`
    state.marks = { data: { marks: window.testMarks } };
    state.cancellations = { data: { cancellations: window.testCancellations } };
  `);
  return window;
}

function lookUp(window, name, lesson) {
  window.testLesson = lesson;
  return window.eval(`${name}(window.testLesson, "c1")`);
}

describe("two subjects in one period", () => {
  test("an exam mark belongs only to its subject", () => {
    const window = withEntries([{ id: "m1", child_key: "c1", date: "2026-09-02", period: 3, subject_code: "MA", name: "Test" }], []);
    expect(lookUp(window, "markOfLesson", MATHS)).not.toBeNull();
    expect(lookUp(window, "markOfLesson", GERMAN)).toBeNull();
  });

  test("an own cancellation belongs only to its subject", () => {
    const window = withEntries([], [{ id: "c1", child_key: "c1", date: "2026-09-02", period: 3, subject_code: "D" }]);
    expect(lookUp(window, "lessonDropped", GERMAN)).toBe(true);
    expect(lookUp(window, "lessonDropped", MATHS)).toBe(false);
  });

  test("an older cancellation without a subject still covers the whole period", () => {
    const window = withEntries([], [{ id: "c1", child_key: "c1", date: "2026-09-02", period: 3 }]);
    expect(lookUp(window, "lessonDropped", GERMAN)).toBe(true);
    expect(lookUp(window, "lessonDropped", MATHS)).toBe(true);
  });
});

describe("marks survive a renamed subject code", () => {
  test("a mark stored with the school's code still finds the lesson after the code was renamed", () => {
    const window = withEntries([{ id: "m1", child_key: "c1", date: "2026-09-02", period: 3, subject_code: "MA", name: "Test" }], []);
    expect(lookUp(window, "markOfLesson", { ...MATHS, subject_key: "MA", subject_code: "M" })).not.toBeNull();
    expect(lookUp(window, "markOfLesson", { ...GERMAN, subject_key: "D" })).toBeNull();
  });

  test("an own cancellation is sent with the school's code of the lesson", async () => {
    const window = withEntries([], []);
    const sent = [];
    window.fetch = (url, options) => {
      sent.push({ url: String(url), body: options && options.body });
      const body = { ok: true, cancellations: [] };
      return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: async () => body, text: async () => JSON.stringify(body) });
    };
    window.testLesson = { ...MATHS, subject_key: "MA", subject_code: "M" };
    window.eval('state.childId = "c1"; addCancellation("c1", window.testLesson);');
    await new Promise((resolve) => setTimeout(resolve, 0));
    const post = sent.find((request) => request.url.endsWith("api/cancellations") && request.body);
    expect(JSON.parse(post.body)).toEqual({ child_key: "c1", date: "2026-09-02", period: 3, subject_code: "MA" });
  });
});
