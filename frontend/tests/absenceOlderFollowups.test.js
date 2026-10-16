import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";
import { wizard } from "./absenceWizard.js";

async function settle(window, ticks = 8) {
  for (let tick = 0; tick < ticks; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
}

function olderData(extra) {
  return Object.assign(
    { source: "older_page", children: [{ id: "c-mia", name: "Mia Muster" }], types: [], rules: {}, entries: [], withheld: 0, phones: [] },
    extra || {}
  );
}

const FORM = { profiles: [{ id: "c-mia", name: "Mia Muster" }], till: false, times: false, whole_day: true, min: "", reason: null, kind: null, extras: [] };

function json(body) {
  return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve(body) });
}

function render(window, data) {
  return window.eval("(function (box) { state.absence = box; return absenceView(); })")({ data, connectionId: "" });
}

describe("follow-ups for schools on the older absence page", () => {
  test("the empty list explains itself without the school app wording", () => {
    const { window } = loadApp();
    const text = render(window, olderData()).textContent;
    expect(text).toContain(window.t("absence.empty.olderText"));
    expect(text).not.toContain(window.t("absence.empty.text"));
    expect(window.t("absence.empty.olderText")).not.toMatch(/IServ/);
  });

  test("the export is offered only when the school has one and arrives as a file from the app", async () => {
    const { window } = loadApp();
    expect(render(window, olderData()).textContent).not.toContain(window.t("absence.older.export"));
    const view = render(window, olderData({ export: true }));
    const requested = [];
    window.fetch = (url) => {
      requested.push(new URL(String(url)).pathname + new URL(String(url)).search);
      return Promise.resolve({ ok: true, status: 200, headers: { get: () => 'attachment; filename="absences.csv"' }, blob: () => Promise.resolve(new window.Blob(["a;b"])) });
    };
    window.eval("saveFile = async (blob, name) => { window.savedName = name; }");
    const button = Array.from(view.querySelectorAll("button")).find((node) => node.textContent.includes(window.t("absence.older.export")));
    expect(button.classList.contains("ghost")).toBe(true);
    button.click();
    await settle(window);
    expect(requested).toContain("/api/absences/older-export");
    expect(window.savedName).toBe("absences.csv");
    expect(view.querySelectorAll("a[href]").length).toBe(0);
  });

  test("the change log and the remove control of an own attachment appear in the entry", async () => {
    const { window } = loadApp();
    const posted = [];
    window.fetch = (url, options) => {
      const path = new URL(String(url)).pathname;
      if (options && options.method === "POST") {
        posted.push({ path, body: JSON.parse(options.body) });
        return json({ ok: true, message_key: "api.absence.older.attachmentRemoved" });
      }
      if (path === "/api/absences/older-detail") {
        return json({ ok: true, attachments: [{ key: "k-attest", name: "Attest.pdf", deletable: true }], can_upload: false, log: ["13.09.2026 · Erstellt"] });
      }
      return Promise.reject(new Error("offline"));
    };
    const entry = { id: "older:481", kind: "absence", source: "older_page", label_key: "absence.entry.kind.absence", from_date: "2126-09-14", till_date: "2126-09-14", student_id: "c-mia", status: "open", deletable: false, detail: true, locked_reason_key: "api.absence.older.locked", technical: { id: "481" } };
    evalWith(window, "state.absence = { data: testArgs[0], connectionId: '' }", olderData());
    const parts = window.eval("absenceDetailParts")(entry);
    const block = parts.body.find((node) => node && node.classList && node.classList.contains("older-attachments"));
    await settle(window, 12);
    expect(block.textContent).toContain(window.t("absence.older.log"));
    expect(block.textContent).toContain("13.09.2026 · Erstellt");
    const remove = Array.from(block.querySelectorAll("button")).find((node) => node.textContent.includes(window.t("absence.older.removeAttachment", { name: "Attest.pdf" })));
    remove.click();
    await settle(window);
    expect(posted).toEqual([]);
    const confirm = window.eval("state.sheet()").querySelector(".btn-stack .btn.destructive");
    confirm.click();
    await settle(window);
    expect(posted).toEqual([{ path: "/api/absences/older-attachment/delete", body: { connection_id: "", id: "older:481", key: "k-attest" } }]);
    expect(window.eval("state.toast.message")).toBe(window.t("api.absence.older.attachmentRemoved"));
  });

  test("a send that runs out of time is kept as unconfirmed and the same values cannot be sent again until the list shows them", async () => {
    const { window, document } = loadApp();
    let listed = [];
    const posts = [];
    window.fetch = (url, options) => {
      const path = new URL(String(url)).pathname;
      if (path === "/api/absences/older-form") return json({ ok: true, form: FORM });
      if (path === "/api/absences" && options && options.method === "POST") {
        posts.push(JSON.parse(options.body));
        return Promise.reject(new Error("timeout"));
      }
      if (path === "/api/absences") return json(olderData({ entries: listed }));
      return Promise.reject(new Error("offline"));
    };
    evalWith(window, "state.absence = { data: testArgs[0], connectionId: '' }", olderData());
    window.eval("state.view = 'absence'; render();");
    const report = () => Array.from(document.querySelectorAll(".btn")).find((node) => node.textContent.includes(window.t("absence.report"))).click();
    report();
    await settle(window);
    wizard(window).go("review");
    wizard(window).next();
    await settle(window, 12);
    expect(posts).toHaveLength(1);
    expect(window.eval("state.absenceForm")).toBeNull();
    expect(window.eval("state.toast.message")).toBe(window.t("absence.older.sendUnclear"));
    const day = posts[0].from_date;
    const shown = render(window, window.eval("state.absence.data"));
    expect(shown.querySelector(".row .tag.warn").textContent).toBe(window.t("absence.status.unconfirmed"));
    window.eval("state.view = 'absence'; render();");
    report();
    await settle(window);
    evalWith(window, "state.absenceForm.reason = 'anders'");
    wizard(window).go("review");
    wizard(window).next();
    await settle(window, 12);
    const dialog = window.eval("state.sheet()");
    expect(dialog.textContent).toContain(window.t("absence.older.sendAgainTitle"));
    dialog.querySelector(".btn-stack .btn.ghost").click();
    await settle(window, 12);
    expect(posts).toHaveLength(1);
    expect(wizard(window).status).toBe(window.t("api.absence.older.alreadySent"));
    window.eval("closeAbsenceForm()");
    listed = [{ id: "older:pending:x", kind: "absence", source: "older_page", from_date: day, till_date: day, student_id: "c-mia", status: "unconfirmed", unconfirmed: true }];
    await window.eval("loadAbsences()");
    await settle(window);
    expect(window.eval("olderLiveSends().length")).toBe(1);
    expect(render(window, window.eval("state.absence.data")).querySelectorAll(".row .tag.warn").length).toBe(1);
    listed = [{ id: "older:990", kind: "absence", source: "older_page", from_date: day, till_date: day, student_id: "c-mia", status: "open" }];
    await window.eval("loadAbsences()");
    await settle(window);
    expect(window.eval("olderLiveSends().length")).toBe(0);
  });
});
