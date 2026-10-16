import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";
import { wizard } from "./absenceWizard.js";

async function settle(window, ticks = 12) {
  for (let tick = 0; tick < ticks; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
}

function json(body) {
  return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve(body) });
}

const DATA = { source: "older_page", children: [{ id: "c-mia", name: "Mia Muster" }], types: [], rules: {}, entries: [], withheld: 0, phones: [] };
const FORM = { profiles: [{ id: "c-mia", name: "Mia Muster" }], till: false, times: false, whole_day: true, min: "", reason: null, kind: null, extras: [], files: null };
const ENTRY = {
  id: "older:481", kind: "absence", source: "older_page", label_key: "absence.entry.kind.absence", from_date: "2126-09-14", till_date: "2126-09-14",
  student_id: "c-mia", status: "open", deletable: false, detail: true, locked_reason_key: "api.absence.older.locked", technical: { id: "481" },
};

function openWizard(window, document, form) {
  evalWith(window, "state.absence = { data: testArgs[0], connectionId: '' }", DATA);
  window.eval("state.view = 'absence'; render();");
  Array.from(document.querySelectorAll(".btn")).find((node) => node.textContent.includes(window.t("absence.report"))).click();
  return settle(window);
}

describe("review findings on the older absence flow", () => {
  test("a report the school already has asks before sending again and sends only on an explicit yes", async () => {
    const { window, document } = loadApp();
    const posts = [];
    window.fetch = (url, options) => {
      const path = new URL(String(url)).pathname;
      if (path === "/api/absences/older-form") return json({ ok: true, form: FORM });
      if (path === "/api/absences" && options && options.method === "POST") {
        const body = JSON.parse(options.body);
        posts.push(body);
        return json(body.send_again ? { ok: true, message_key: "api.absence.older.sent" } : { ok: false, already_sent: true, message_key: "api.absence.older.alreadySent" });
      }
      if (path === "/api/absences") return json(DATA);
      return Promise.reject(new Error("offline"));
    };
    await openWizard(window, document);
    wizard(window).go("review");
    wizard(window).next();
    await settle(window);
    expect(posts).toHaveLength(1);
    window.eval("state.sheet()").querySelector(".btn-stack .btn:not(.ghost)").click();
    await settle(window);
    expect(posts).toHaveLength(2);
    expect(posts[1].send_again).toBe(true);
    expect(window.eval("state.absenceForm")).toBeNull();
  });

  test("an uncertain answer guards the same profile and days even with other details", async () => {
    const { window, document } = loadApp();
    const posts = [];
    window.fetch = (url, options) => {
      const path = new URL(String(url)).pathname;
      if (path === "/api/absences/older-form") return json({ ok: true, form: Object.assign({}, FORM, { reason: { name: "r", type: "textarea", label: "Kommentar", required: false, options: [] } }) });
      if (path === "/api/absences" && options && options.method === "POST") {
        posts.push(JSON.parse(options.body));
        return json({ ok: false, uncertain: true, message_key: "api.absence.older.uncertain" });
      }
      if (path === "/api/absences") return json(DATA);
      return Promise.reject(new Error("offline"));
    };
    await openWizard(window, document);
    wizard(window).go("review");
    wizard(window).next();
    await settle(window);
    expect(posts).toHaveLength(1);
    window.eval("state.view = 'absence'; render();");
    await openWizard(window, document);
    evalWith(window, "state.absenceForm.reason = 'anders'");
    wizard(window).go("review");
    wizard(window).next();
    await settle(window);
    expect(window.eval("state.sheet()").textContent).toContain(window.t("absence.older.sendAgainTitle"));
    expect(posts).toHaveLength(1);
  });

  test("files go along with the report when the school form takes them", async () => {
    const { window, document } = loadApp();
    const sent = [];
    window.fetch = (url, options) => {
      const path = new URL(String(url)).pathname;
      if (path === "/api/absences/older-form") return json({ ok: true, form: Object.assign({}, FORM, { files: { required: true, multiple: false } }) });
      if (path === "/api/absences" && options && options.method === "POST") {
        sent.push(options.body);
        return json({ ok: true, message_key: "api.absence.older.sent" });
      }
      if (path === "/api/absences") return json(DATA);
      return Promise.reject(new Error("offline"));
    };
    await openWizard(window, document);
    expect(wizard(window).path).toEqual(["olderWhen", "olderFiles", "review"]);
    expect(window.eval("absenceProblems(state.absenceForm, state.absence.data)").map((item) => item.step)).toEqual(["olderFiles"]);
    evalWith(window, "state.absenceForm.attachments = [new File(['%PDF'], 'attest.pdf', { type: 'application/pdf' })]");
    wizard(window).go("review");
    wizard(window).next();
    await settle(window);
    expect(sent).toHaveLength(1);
    expect(sent[0].get("files").name).toBe("attest.pdf");
    expect(JSON.parse(sent[0].get("data")).type).toBe("absence");
  });

  test("a failed detail load is asked again next time instead of being kept", async () => {
    const { window } = loadApp();
    let calls = 0;
    window.fetch = (url) => {
      if (new URL(String(url)).pathname !== "/api/absences/older-detail") return Promise.reject(new Error("offline"));
      calls += 1;
      return calls === 1 ? Promise.reject(new Error("offline")) : json({ ok: true, attachments: [], can_upload: false, log: ["x"] });
    };
    evalWith(window, "state.absence = { data: testArgs[0], connectionId: '' }", DATA);
    expect(await window.eval("olderDetail")(ENTRY, "")).toBeNull();
    const second = await window.eval("olderDetail")(ENTRY, "");
    expect(calls).toBe(2);
    expect(second.ok).toBe(true);
  });

  test("while one upload waits for its confirmation the button takes no second file", async () => {
    const { window } = loadApp();
    window.fetch = () => Promise.reject(new Error("offline"));
    evalWith(window, "state.absence = { data: testArgs[0], connectionId: '' }", DATA);
    const block = window.eval("olderUploadButton")(ENTRY, "");
    const input = block.querySelector("input[type=file]");
    const button = block.querySelector("button");
    let picks = 0;
    input.click = () => {
      picks += 1;
    };
    button.click();
    expect(picks).toBe(1);
    Object.defineProperty(input, "files", { value: [new window.File(["x"], "a.pdf")], configurable: true });
    input.dispatchEvent(new window.Event("change"));
    await settle(window, 3);
    expect(button.disabled).toBe(true);
    button.dispatchEvent(new window.MouseEvent("click"));
    expect(picks).toBe(1);
    const again = window.eval("olderUploadButton")(ENTRY, "");
    expect(again.querySelector("button").disabled).toBe(true);
  });

  test("the export asks for the school the absence view shows", async () => {
    const { window } = loadApp();
    const requested = [];
    window.fetch = (url) => {
      requested.push(new URL(String(url)).search);
      return Promise.resolve({ ok: true, status: 200, headers: { get: () => "" }, blob: () => Promise.resolve(new window.Blob(["a"])) });
    };
    window.eval("saveFile = async () => {}; absenceSchoolId = () => ''");
    evalWith(window, "state.absence = { data: testArgs[0], connectionId: 'b2' }", DATA);
    window.eval("olderExportButton()").click();
    await settle(window);
    expect(requested).toContain("?connection=b2");
  });
});
