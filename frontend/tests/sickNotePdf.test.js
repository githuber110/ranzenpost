import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function buildSheet(window, entry, rules) {
  const run = window.eval(`
    (function (entry, rules) {
      state.absence = { data: { children: [{ id: entry.student_id, name: "Mia" }], rules } };
      openAbsenceSheet(entry);
      return state.sheet();
    })
  `);
  return run(entry, rules);
}

const SICK_ENTRY = { id: 42, kind: "sick", student_id: 1, label: "Krankmeldung", locked_reason: "" };
const LEAVE_ENTRY = { id: 7, kind: "leave", student_id: 1, label: "Beurlaubungsantrag", deletable: true };
const DEREGISTER_ENTRY = { id: 8, kind: "deregister", student_id: 1, label: "Abmeldung", deletable: true };
const DAYCARE_ENTRY = { id: 9, kind: "daycare", student_id: 1, label: "Ganztagsbetreuung", deletable: true };

describe("[P139] sick-note PDF action", () => {
  test("shows the exact label and a button, not a same-tab-breaking link", () => {
    const { window } = loadApp();
    const scrim = buildSheet(window, SICK_ENTRY, {});
    expect(scrim.textContent).toContain("Schriftliche Bestätigung (PDF)");
    const button = [...scrim.querySelectorAll("button.btn")].find((node) =>
      node.textContent.includes("Schriftliche Bestätigung (PDF)")
    );
    expect(button).toBeTruthy();
    expect(button.hasAttribute("href")).toBe(false);
    expect(button.hasAttribute("target")).toBe(false);
  });

  test.each([
    ["leave", LEAVE_ENTRY],
    ["deregister", DEREGISTER_ENTRY],
    ["daycare", DAYCARE_ENTRY],
  ])("does not show the action for kind=%s", (_kind, entry) => {
    const { window } = loadApp();
    const scrim = buildSheet(window, entry, {});
    expect(scrim.textContent).not.toContain("Schriftliche Bestätigung (PDF)");
    expect(scrim.querySelector('a[href*="sick-note-pdf"]')).toBeNull();
  });

  test("carries no generic hint text about printing or signing", () => {
    const { window } = loadApp();
    const scrim = buildSheet(window, SICK_ENTRY, {});
    const text = scrim.textContent.toLowerCase();
    expect(text).not.toContain("unterschr");
    expect(text).not.toContain("drucken");
    expect(text).not.toContain("mitgeben");
  });

  test("shows the school's real duty_hint text when present", () => {
    const { window } = loadApp();
    const scrim = buildSheet(window, SICK_ENTRY, { duty_hint: "Schul-eigener Hinweis zur Meldepflicht." });
    expect(scrim.textContent).toContain("Schul-eigener Hinweis zur Meldepflicht.");
  });

  test("shows nothing extra when duty_hint is empty", () => {
    const { window } = loadApp();
    const scrim = buildSheet(window, SICK_ENTRY, { duty_hint: "" });
    const text = scrim.textContent.toLowerCase();
    expect(text).not.toContain("infektionsschutzgesetz");
    expect(text).not.toContain("meldepflicht");
  });
});

describe("[P150] sick-note PDF fetches in the current document context", () => {
  test("clicking the button fetches the relative sick-note-pdf path and downloads it", async () => {
    const { window } = loadApp();
    window.URL.createObjectURL = () => "blob:mock-url";
    window.URL.revokeObjectURL = () => {};
    const requestedUrls = [];
    window.fetch = (url) => {
      requestedUrls.push(url);
      return Promise.resolve({
        ok: true,
        headers: { get: () => "" },
        blob: () => Promise.resolve(new window.Blob(["x"])),
      });
    };
    const scrim = buildSheet(window, SICK_ENTRY, {});
    const button = [...scrim.querySelectorAll("button.btn")].find((node) =>
      node.textContent.includes("Schriftliche Bestätigung (PDF)")
    );
    button.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    for (let tick = 0; tick < 6; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(requestedUrls).toContain("http://localhost/api/absences/sick-note-pdf?id=42");
  });

  test("a 401 from a broken ingress session shows an error toast instead of a bare browser error", async () => {
    const { window } = loadApp();
    window.fetch = () => Promise.resolve({ ok: false, status: 401, headers: { get: () => "" } });
    const scrim = buildSheet(window, SICK_ENTRY, {});
    const button = [...scrim.querySelectorAll("button.btn")].find((node) =>
      node.textContent.includes("Schriftliche Bestätigung (PDF)")
    );
    button.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    for (let tick = 0; tick < 6; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(window.eval("state.toast && state.toast.kind")).toBe("bad");
  });
});

describe("[P160] a backend refusal reaches the parent as a real explanation", () => {
  test("an unsupported name shows the backend message instead of the generic failure", async () => {
    const { window } = loadApp({ url: "http://localhost/" });
    window.setLanguageBundle("de", { "api.sickNote.error.unsupportedCharacters": "Diese Zeichen können wir nicht drucken: {characters}" }, {});
    window.fetch = () =>
      Promise.resolve({
        ok: false,
        status: 422,
        headers: { get: (name) => (name === "content-type" ? "application/json" : null) },
        json: () =>
          Promise.resolve({
            message_key: "api.sickNote.error.unsupportedCharacters",
            message_vars: { characters: "أ م" },
          }),
      });
    let thrown = null;
    try {
      await window.eval('openAppFile("api/absences/sick-note-pdf?id=1", "x.pdf")');
    } catch (error) {
      thrown = error;
    }
    expect(thrown).not.toBeNull();
    expect(thrown.userMessage).toContain("أ م");
  });

  test("a plain failure without a body falls back to the generic message", async () => {
    const { window } = loadApp({ url: "http://localhost/" });
    window.fetch = () =>
      Promise.resolve({ ok: false, status: 502, headers: { get: () => "text/plain" } });
    let thrown = null;
    try {
      await window.eval('openAppFile("api/pinboard/attachment/x", "x")');
    } catch (error) {
      thrown = error;
    }
    expect(thrown).not.toBeNull();
    expect(thrown.userMessage).toBe("");
  });
});
