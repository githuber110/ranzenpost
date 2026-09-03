import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(dirname, "..");
const qrJs = fs.readFileSync(path.join(frontendDir, "qr.js"), "utf8");
const base = JSON.parse(fs.readFileSync(path.join(frontendDir, "i18n", "de.json"), "utf8"));

const FROZEN_URL = "webcal://homeassistant.local:8100/calendar/e2e-fixture-token-abcdefghijklmnopqrstuvwxyz012345.ics";
const FROZEN_DIGEST = "2fb1591565d7bee34fdea16b8ef54361b2bdc67e61a1e1a5e1598f227b4c7d5e";

const SUBSCRIPTION = {
  id: "sub-1",
  child_id: "c1",
  label: "3b",
  components: ["timetable", "school_holidays"],
  color: "#135859",
  token: "token-1",
  path: "/calendar/token-1.ics",
};

function payloadFor(region, subscriptions) {
  return {
    subscriptions,
    components: ["timetable", "school_holidays", "public_holidays"],
    holiday_region: region,
    path_template: "/calendar/{token}.ics",
    port: 8100,
  };
}

function setup({ region = "DE-NI", subscriptions = [], responses = {} } = {}) {
  const { window } = loadApp();
  const calls = [];
  window.eval("render = function () { window.__renders = (window.__renders || 0) + 1; };");
  window.eval('state.children = [{ child_id: "c1", name: "Mia", class_name: "3b" }]; state.childId = "c1";');
  window.eval('state.view = "timetable"; state.calendarHost = "ha.example";');
  window.eval(`state.calendar = { data: ${JSON.stringify(payloadFor(region, subscriptions))}, error: false };`);
  window.fetch = (url, options) => {
    const target = String(url);
    calls.push({ url: target, options: options || {} });
    for (const [fragment, answer] of Object.entries(responses)) {
      if (target.includes(fragment)) return Promise.resolve(answer());
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(payloadFor(region, subscriptions)),
    });
  };
  return { window, calls };
}

function writeCalls(calls) {
  return calls.filter(
    (entry) => entry.url.includes("api/calendar/subscriptions") && entry.options && entry.options.method
  );
}

function buttonWithText(node, text) {
  return [...node.querySelectorAll("button")].find((button) => button.textContent.includes(text)) || null;
}

describe("[P164] creating a calendar subscription", () => {
  test("submitting a new draft posts to the subscription endpoint with the picked parts", async () => {
    const { window, calls } = setup();
    window.eval("state.calendarDraft = calendarNewDraft(state.children[0]);");
    window.eval('state.calendarDraft.label = "3b"; state.calendarDraft.color = "#135859";');
    await window.eval("submitCalendarDraft(state.calendarDraft)");

    const writes = writeCalls(calls);
    expect(writes).toHaveLength(1);
    expect(writes[0].url).toMatch(/api\/calendar\/subscriptions$/);
    expect(writes[0].options.method).toBe("POST");
    expect(JSON.parse(writes[0].options.body)).toEqual({
      child_id: "c1",
      components: ["timetable"],
      label: "3b",
      color: "#135859",
    });
    expect(window.eval("state.calendarDraft")).toBeNull();
  });

  test("an existing subscription is changed through its own path, not created a second time", async () => {
    const { window, calls } = setup({ subscriptions: [SUBSCRIPTION] });
    window.eval(`state.calendarDraft = calendarEditDraft(${JSON.stringify(SUBSCRIPTION)}, state.children[0]);`);
    await window.eval("submitCalendarDraft(state.calendarDraft)");

    const writes = writeCalls(calls);
    expect(writes).toHaveLength(1);
    expect(writes[0].url).toMatch(/api\/calendar\/subscriptions\/sub-1$/);
  });
});

describe("[P164] the at-least-one rule is explained before anything is sent", () => {
  test("an empty selection shows the backend wording and disables the confirm button", () => {
    const { window } = setup();
    window.eval("state.calendarDraft = calendarNewDraft(state.children[0]); state.calendarDraft.components = [];");
    const form = window.eval("calendarForm(state.calendarDraft)");

    expect(form.textContent).toContain(base["api.calendar.error.components"]);
    const submit = buttonWithText(form, base["calendar.subscribe.create"]);
    expect(submit).not.toBeNull();
    expect(submit.hasAttribute("disabled")).toBe(true);
    expect(submit.getAttribute("aria-disabled")).toBe("true");
  });

  test("submitting anyway sends no request and keeps the explanation on the draft", async () => {
    const { window, calls } = setup();
    window.eval("state.calendarDraft = calendarNewDraft(state.children[0]); state.calendarDraft.components = [];");
    await window.eval("submitCalendarDraft(state.calendarDraft)");

    expect(writeCalls(calls)).toHaveLength(0);
    expect(window.eval("state.calendarDraft.error")).toBe(base["api.calendar.error.components"]);
  });

  test("toggling a part updates the form in place, without re-mounting the sheet", () => {
    const { window } = setup();
    window.eval("state.calendarDraft = calendarNewDraft(state.children[0]);");
    const form = window.eval("calendarForm(state.calendarDraft)");
    window.eval("window.__renders = 0;");

    const box = form.querySelectorAll(".check input")[2];
    box.checked = true;
    box.dispatchEvent(new window.Event("change", { bubbles: true }));

    expect(window.eval("window.__renders")).toBe(0);
    expect(window.eval("state.calendarDraft.components")).toEqual(["timetable", "public_holidays"]);
    expect(buttonWithText(form, base["calendar.subscribe.create"]).hasAttribute("disabled")).toBe(false);
  });

  test("picking a colour marks it in place, without re-mounting the sheet", () => {
    const { window } = setup();
    window.eval("state.calendarDraft = calendarNewDraft(state.children[0]);");
    const form = window.eval("calendarForm(state.calendarDraft)");
    window.eval("window.__renders = 0;");

    const swatches = [...form.querySelectorAll(".cal-swatch")];
    swatches[0].click();

    expect(window.eval("window.__renders")).toBe(0);
    expect(window.eval("state.calendarDraft.color")).toBe(swatches[0].getAttribute("data-color"));
    expect(swatches[0].getAttribute("aria-pressed")).toBe("true");
    expect(swatches.filter((node) => node.getAttribute("aria-pressed") === "true")).toHaveLength(1);
  });

  test("timetable stays locked while no holiday region is set", () => {
    const { window } = setup({ region: "" });
    window.eval("state.calendarDraft = calendarNewDraft(state.children[0]);");
    const form = window.eval("calendarForm(state.calendarDraft)");

    const boxes = [...form.querySelectorAll(".check input")];
    expect(boxes[0].disabled).toBe(true);
    expect(boxes[1].disabled).toBe(false);
    expect(form.textContent).toContain(base["calendar.subscribe.region.locked"]);
    expect(buttonWithText(form, base["calendar.subscribe.region.open"])).not.toBeNull();
    expect(window.eval("state.calendarDraft.components")).toEqual(["school_holidays"]);
  });
});

describe("[P164] a rejected label shows the reason the backend gives", () => {
  test("the child-name rejection is rendered as the translated backend message", async () => {
    const { window } = setup({
      responses: {
        "api/calendar/subscriptions": () => ({
          ok: false,
          status: 400,
          json: () => Promise.resolve({ ok: false, message_key: "api.calendar.error.labelName" }),
        }),
      },
    });
    window.eval("state.calendarDraft = calendarNewDraft(state.children[0]);");
    window.eval('state.calendarDraft.label = "Mia";');
    await window.eval("submitCalendarDraft(state.calendarDraft)");

    expect(window.eval("state.calendarDraft.error")).toBe(base["api.calendar.error.labelName"]);
    const form = window.eval("calendarForm(state.calendarDraft)");
    expect(form.textContent).toContain(base["api.calendar.error.labelName"]);
  });
});

describe("[P164] renewing the token asks first", () => {
  test("no request goes out until the confirmation is accepted", async () => {
    const { window, calls } = setup({ subscriptions: [SUBSCRIPTION] });
    const pending = window.eval(`rotateCalendarSubscription(${JSON.stringify(SUBSCRIPTION)})`);

    const dialog = window.eval("state.sheet()");
    expect(dialog.querySelector(".sheet-title").textContent).toBe(base["calendar.subscribe.rotate.title"]);
    expect(dialog.textContent).toContain(base["calendar.subscribe.rotate.text"]);
    expect(writeCalls(calls)).toHaveLength(0);

    buttonWithText(dialog, base["calendar.subscribe.rotate.confirm"]).click();
    await pending;

    const writes = writeCalls(calls);
    expect(writes).toHaveLength(1);
    expect(writes[0].url).toMatch(/api\/calendar\/subscriptions\/sub-1\/rotate$/);
    expect(writes[0].options.method).toBe("POST");
  });

  test("declining the confirmation leaves the token alone", async () => {
    const { window, calls } = setup({ subscriptions: [SUBSCRIPTION] });
    const pending = window.eval(`rotateCalendarSubscription(${JSON.stringify(SUBSCRIPTION)})`);
    const dialog = window.eval("state.sheet()");
    buttonWithText(dialog, base["common.cancel"]).click();
    await pending;

    expect(writeCalls(calls)).toHaveLength(0);
  });

  test("deleting asks with its own wording and then calls DELETE", async () => {
    const { window, calls } = setup({ subscriptions: [SUBSCRIPTION] });
    const pending = window.eval(`revokeCalendarSubscription(${JSON.stringify(SUBSCRIPTION)})`);
    const dialog = window.eval("state.sheet()");
    expect(dialog.querySelector(".sheet-title").textContent).toBe(base["calendar.subscribe.delete.title"]);
    buttonWithText(dialog, base["calendar.subscribe.delete.confirm"]).click();
    await pending;

    const writes = writeCalls(calls);
    expect(writes).toHaveLength(1);
    expect(writes[0].options.method).toBe("DELETE");
  });
});

describe("[P164] the subscription address is built from the host of this device", () => {
  test("the sheet shows the feed address and offers webcal, copy and QR", () => {
    const { window } = setup({ subscriptions: [SUBSCRIPTION] });
    window.eval(qrJs);
    const sheetNode = window.eval("calendarSheet()");

    expect(sheetNode.querySelector(".cal-url").textContent).toBe("http://ha.example:8100/calendar/token-1.ics");
    const link = sheetNode.querySelector("a.cal-add");
    expect(link.getAttribute("href")).toBe("webcal://ha.example:8100/calendar/token-1.ics");
    expect(buttonWithText(sheetNode, base["calendar.subscribe.copy"])).not.toBeNull();
    expect(buttonWithText(sheetNode, base["calendar.subscribe.qr.show"])).not.toBeNull();
    expect(sheetNode.textContent).toContain(base["calendar.subscribe.warning"]);
  });

  test("without a usable host the address is withheld and the host field is asked for", () => {
    const { window } = setup({ subscriptions: [SUBSCRIPTION] });
    window.eval('state.calendarHost = "";');
    const sheetNode = window.eval("calendarSheet()");

    expect(sheetNode.querySelector(".cal-url")).toBeNull();
    expect(sheetNode.textContent).toContain(base["calendar.subscribe.host.missing"]);
    expect(sheetNode.querySelector("a.cal-add")).toBeNull();
  });
});

describe("[P164] the QR encoder is deterministic", () => {
  test("a known address always produces the same matrix", () => {
    const { window } = loadApp();
    window.eval(qrJs);
    const matrix = window.eval(`qrMatrix(${JSON.stringify(FROZEN_URL)})`);
    const rows = [...matrix.rows].map((row) => [...row].join(""));

    expect(matrix.version).toBe(6);
    expect(matrix.size).toBe(41);
    expect(crypto.createHash("sha256").update(rows.join("\n")).digest("hex")).toBe(FROZEN_DIGEST);
  });

  test("the three finder patterns and the quiet zone are where a scanner expects them", () => {
    const { window } = loadApp();
    window.eval(qrJs);
    const matrix = window.eval(`qrMatrix(${JSON.stringify(FROZEN_URL)})`);
    const rows = [...matrix.rows].map((row) => [...row].join(""));
    const size = matrix.size;

    expect(rows[0].slice(0, 7)).toBe("1111111");
    expect(rows[0].slice(size - 7)).toBe("1111111");
    expect(rows[size - 7].slice(0, 7)).toBe("1111111");
    expect(rows[1].slice(0, 7)).toBe("1000001");
    expect(window.eval(`qrCanvasSize(qrMatrix(${JSON.stringify(FROZEN_URL)}))`)).toBe(size + 8);
  });

  test("empty and oversized input yield no matrix instead of a broken one", () => {
    const { window } = loadApp();
    window.eval(qrJs);
    expect(window.eval('qrMatrix("")')).toBeNull();
    expect(window.eval('qrMatrix("x".repeat(300))')).toBeNull();
  });
});
