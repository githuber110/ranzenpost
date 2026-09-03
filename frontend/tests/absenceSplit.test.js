import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderAbsenceView(window, box) {
  const run = window.eval(
    "(function (box) { state.absence = box; return absenceView(); })"
  );
  return run(box);
}

describe("absence view current/past split", () => {
  test("splits entries by till_date against today", () => {
    const { window } = loadApp();
    const today = new Date();
    const past = new Date(today);
    past.setDate(past.getDate() - 10);
    const future = new Date(today);
    future.setDate(future.getDate() + 10);
    const pad2 = (value) => String(value).padStart(2, "0");
    const isoDate = (date) =>
      `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;

    const box = {
      data: {
        entries: [
          { id: "current", till_date: isoDate(future), from_date: isoDate(future) },
          { id: "past", till_date: isoDate(past), from_date: isoDate(past) },
        ],
        phones: [],
      },
    };

    const view = renderAbsenceView(window, box);
    const text = view.textContent;
    expect(text).toContain("Gemeldet");
    expect(text).toContain("Vergangene Abwesenheiten (1)");
    expect(view.querySelectorAll(".rows").length).toBeGreaterThan(0);
  });

  test("an entry whose till_date equals today counts as current, not past", () => {
    const { window } = loadApp();
    const today = new Date();
    const pad2 = (value) => String(value).padStart(2, "0");
    const isoDate = (date) =>
      `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;

    const box = {
      data: {
        entries: [{ id: "today", till_date: isoDate(today), from_date: isoDate(today) }],
        phones: [],
      },
    };

    const view = renderAbsenceView(window, box);
    expect(view.querySelector(".rows")).not.toBeNull();
    expect(view.textContent).not.toContain("Vergangen");
  });
});

describe("[P122] absence history-sourced entries", () => {
  test("a history-sourced past entry is tagged distinct from a live one", () => {
    const { window } = loadApp();
    const today = new Date();
    const past = new Date(today);
    past.setDate(past.getDate() - 10);
    const pad2 = (value) => String(value).padStart(2, "0");
    const isoDate = (date) => `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;

    const box = {
      data: {
        entries: [
          {
            id: "vanished",
            till_date: isoDate(past),
            from_date: isoDate(past),
            label: "Krankmeldung",
            from_history: true,
            deletable: false,
            locked_reason: "IServ liefert diese Meldung nicht mehr.",
          },
        ],
        phones: [],
      },
    };

    const view = renderAbsenceView(window, box);
    window.eval("state.absenceHistoryOpen = true;");
    const reopened = renderAbsenceView(window, box);
    expect(reopened.textContent).toContain("Aus App-Verlauf");
  });
});

describe("[P96] absence empty state honesty", () => {
  test("no entries at all shows the honest empty block", () => {
    const { window } = loadApp();
    const box = { data: { entries: [], phones: [] } };
    const view = renderAbsenceView(window, box);
    expect(view.textContent).toContain("Nichts Aktuelles gemeldet");
    expect(view.textContent).toContain("blendet IServ für Eltern automatisch aus");
    expect(view.textContent).not.toContain("erscheinen hier, sobald du sie eingereicht hast");
  });

  test("only past entries shows a short hint plus the history section, not the full empty block", () => {
    const { window } = loadApp();
    const today = new Date();
    const past = new Date(today);
    past.setDate(past.getDate() - 10);
    const pad2 = (value) => String(value).padStart(2, "0");
    const isoDate = (date) => `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
    const box = {
      data: {
        entries: [{ id: "past", till_date: isoDate(past), from_date: isoDate(past) }],
        phones: [],
      },
    };
    const view = renderAbsenceView(window, box);
    expect(view.textContent).toContain("Nichts Aktuelles gemeldet");
    expect(view.textContent).toContain("Vergangene Abwesenheiten (1)");
    expect(view.querySelector(".empty")).toBeNull();
  });
});
