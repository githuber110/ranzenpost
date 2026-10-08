import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const ONE = "a1b2c3d4";
const TWO = "b2c3d4e5";

const SCHOOL_SUBSCRIPTION = {
  id: "sub-school",
  child_key: "",
  school_id: ONE,
  label: "",
  components: ["school_holidays", "school_events"],
  color: "#135859",
  token: "token-school",
  path: "/calendar/token-school.ics",
};

function payload(subscriptions, schoolEvents) {
  return {
    subscriptions,
    components: ["timetable", "school_holidays", "public_holidays", "marks", "absences", "own_entries", "school_events"],
    holiday_regions: { [ONE]: "DE-NI", [TWO]: "DE-NI" },
    school_events: schoolEvents,
    port: 8100,
    host: "ha.example",
    host_source: "config_entry",
    supervisor: true,
    port_open: true,
  };
}

function label(window, key, vars) {
  return evalWith(window, "t(testArgs[0], testArgs[1])", key, vars || {});
}

function setup({ children = [], subscriptions = [], schoolEvents = { [ONE]: true }, failure = false, disabled = [] } = {}) {
  const { window } = loadApp();
  const calls = [];
  window.eval("render = function () {};");
  const connections = [
    { id: ONE, school_name: "School One", setup_complete: true, phones: [], subjects: {}, teachers: {} },
  ];
  evalWith(window, `
    state.config = { connections: testArgs[0], notify_services: [], notify_events: {}, modules_disabled: testArgs[4] };
    state.children = testArgs[1];
    state.childId = testArgs[1].length ? testArgs[1][0].key : null;
    state.childrenRead = true;
    state.childrenFailure = testArgs[3];
    state.calendar = { data: testArgs[2], error: false };
  `, connections, children, payload(subscriptions, schoolEvents), failure, disabled);
  window.fetch = (url, options) => {
    const target = String(url);
    calls.push({ url: target, options: options || {} });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload(subscriptions, schoolEvents)) });
  };
  return { window, calls };
}

function filledButtons(node) {
  return [...node.querySelectorAll(".btn")].filter(
    (button) => !button.classList.contains("ghost") && !button.classList.contains("destructive")
  );
}

function componentTexts(form) {
  return [...form.querySelectorAll(".check:not(.cal-variant) > span")].map((node) => node.firstChild.textContent);
}

describe("a school subscription for an account without a linked person", () => {
  test("the page offers the school instead of saying nobody is selected", () => {
    const { window } = setup();
    const page = window.eval("calendarPageView()");
    const cards = [...page.querySelectorAll(".cal-card")];

    expect(cards).toHaveLength(1);
    expect(cards[0].classList.contains("cal-school-card")).toBe(true);
    expect(cards[0].querySelector(".overline").textContent).toBe(label(window, "calendar.subscribe.forSchool", { name: "School One" }));
    expect(cards[0].textContent).toContain(label(window, "calendar.subscribe.school.hint"));
    expect(page.textContent).not.toContain(label(window, "overview.noChild"));
    expect(filledButtons(cards[0]).map((node) => node.textContent)).toEqual([label(window, "calendar.subscribe.create")]);
  });

  test("the form offers only holidays and school events and starts with both", () => {
    const { window } = setup();
    window.eval(`state.calendarDraft = calendarSchoolDraft("${ONE}");`);
    const form = window.eval("calendarForm(state.calendarDraft)");

    expect(window.eval("state.calendarDraft.components")).toEqual(["school_holidays", "school_events"]);
    expect(componentTexts(form)).toEqual([
      label(window, "calendar.subscribe.component.school_holidays"),
      label(window, "calendar.subscribe.component.public_holidays"),
      label(window, "calendar.subscribe.component.school_events"),
    ]);
    expect(form.textContent).not.toContain(label(window, "calendar.subscribe.region.locked"));
    expect(window.eval("state.calendarDraft.placeholder")).toBe(label(window, "calendar.name", { name: "School One" }));
    expect(filledButtons(form)).toHaveLength(1);
  });

  test("without the school calendar module the school events stay out", () => {
    const { window } = setup({ schoolEvents: { [ONE]: false } });
    window.eval(`state.calendarDraft = calendarSchoolDraft("${ONE}");`);
    const form = window.eval("calendarForm(state.calendarDraft)");

    expect(window.eval("state.calendarDraft.components")).toEqual(["school_holidays"]);
    expect(componentTexts(form)).not.toContain(label(window, "calendar.subscribe.component.school_events"));
  });

  test("a module switched off in the settings hides the school events", () => {
    const { window } = setup({ disabled: ["calendar"] });

    expect(window.eval(`calendarSchoolEventsOn("${ONE}")`)).toBe(false);
  });

  test("saving posts the school and no person", async () => {
    const { window, calls } = setup();
    window.eval(`state.calendarDraft = calendarSchoolDraft("${ONE}");`);
    await window.eval("submitCalendarDraft(state.calendarDraft)");

    const writes = calls.filter((entry) => entry.options.method === "POST" && entry.url.includes("api/calendar/subscriptions"));
    expect(writes).toHaveLength(1);
    expect(JSON.parse(writes[0].options.body)).toEqual({
      school_id: ONE,
      components: ["school_holidays", "school_events"],
      label: "",
      color: window.eval("CALENDAR_DEFAULT_COLOR"),
      online: false,
    });
  });

  test("an existing school subscription carries the school name and one filled button", () => {
    const { window } = setup({ subscriptions: [SCHOOL_SUBSCRIPTION] });
    const card = window.eval("calendarPageView()").querySelector(".cal-school-card");

    expect(card.querySelector(".cal-name").textContent).toBe(label(window, "calendar.name", { name: "School One" }));
    expect([...card.querySelectorAll(".cal-parts .tag")].map((node) => node.textContent)).toEqual([
      label(window, "calendar.subscribe.component.school_holidays"),
      label(window, "calendar.subscribe.component.school_events"),
    ]);
    expect(filledButtons(card).length).toBeLessThanOrEqual(1);

    evalWith(window, "state.calendarDraft = calendarEditDraft(testArgs[0], null);", SCHOOL_SUBSCRIPTION);
    expect(window.eval("state.calendarDraft.schoolId")).toBe(ONE);
    const form = window.eval("calendarPageView()").querySelector(".cal-school-card .cal-form");
    expect(componentTexts(form)).not.toContain(label(window, "calendar.subscribe.component.timetable"));
  });

  test("an unreadable list of persons offers no school subscription", () => {
    const { window } = setup({ failure: true });
    const page = window.eval("calendarPageView()");

    expect(page.querySelector(".cal-school-card")).toBeNull();
    expect(page.textContent).toContain(label(window, "overview.noChild"));
  });
});

describe("school events in a person's subscription", () => {
  const CHILD = { key: `${ONE}:c1`, child_id: "c1", connection_id: ONE, name: "Mia Example", class_name: "7b" };

  test("a school with a linked person shows only the person card", () => {
    const { window } = setup({ children: [CHILD] });
    const cards = [...window.eval("calendarPageView()").querySelectorAll(".cal-card")];

    expect(cards).toHaveLength(1);
    expect(cards[0].classList.contains("cal-school-card")).toBe(false);
  });

  test("the school events part appears when that school has the calendar module", () => {
    const { window } = setup({ children: [CHILD] });
    window.eval("state.calendarDraft = calendarNewDraft(state.children[0]);");
    const form = window.eval("calendarForm(state.calendarDraft)");

    expect(componentTexts(form)).toContain(label(window, "calendar.subscribe.component.school_events"));
    expect(componentTexts(form)).toContain(label(window, "calendar.subscribe.component.timetable"));
    expect(window.eval("state.calendarDraft.components")).not.toContain("school_events");
  });

  test("the school events part stays hidden without the module", () => {
    const { window } = setup({ children: [CHILD], schoolEvents: { [ONE]: false } });
    window.eval("state.calendarDraft = calendarNewDraft(state.children[0]);");
    const form = window.eval("calendarForm(state.calendarDraft)");

    expect(componentTexts(form)).not.toContain(label(window, "calendar.subscribe.component.school_events"));
  });
});

describe("the holiday region on a school subscription", () => {
  test("a school without a federal state says the subscription has no holidays and offers the setting", () => {
    const { window } = setup();
    window.eval(`state.calendar.data.holiday_regions["${ONE}"] = ""; state.calendarDraft = calendarSchoolDraft("${ONE}");`);
    const form = window.eval("calendarForm(state.calendarDraft)");
    expect(form.textContent).toContain(label(window, "calendar.subscribe.school.region"));
    expect(form.textContent).toContain(label(window, "calendar.subscribe.region.open"));
    expect(form.textContent).not.toContain(label(window, "calendar.subscribe.region.locked"));
  });

  test("a school with a federal state shows no region hint", () => {
    const { window } = setup();
    window.eval(`state.calendarDraft = calendarSchoolDraft("${ONE}");`);
    const form = window.eval("calendarForm(state.calendarDraft)");
    expect(form.textContent).not.toContain(label(window, "calendar.subscribe.school.region"));
  });

  test("the page warning speaks of events, not of the timetable", () => {
    const { window } = setup();
    const page = window.eval("calendarPageView()");
    expect(page.textContent).toContain(label(window, "calendar.subscribe.warning"));
    expect(label(window, "calendar.subscribe.warning")).not.toContain(label(window, "nav.timetable"));
  });
});

describe("the holiday region hint with public holidays only", () => {
  test("public holidays alone also need the federal state", () => {
    const { window } = setup();
    window.eval(`state.calendar.data.holiday_regions["${ONE}"] = ""; state.calendarDraft = calendarSchoolDraft("${ONE}"); state.calendarDraft.components = ["public_holidays"];`);
    const form = window.eval("calendarForm(state.calendarDraft)");
    expect(form.textContent).toContain(label(window, "calendar.subscribe.school.region"));
  });

  test("school events alone need no federal state", () => {
    const { window } = setup();
    window.eval(`state.calendar.data.holiday_regions["${ONE}"] = ""; state.calendarDraft = calendarSchoolDraft("${ONE}"); state.calendarDraft.components = ["school_events"];`);
    const form = window.eval("calendarForm(state.calendarDraft)");
    expect(form.textContent).not.toContain(label(window, "calendar.subscribe.school.region"));
  });
});
