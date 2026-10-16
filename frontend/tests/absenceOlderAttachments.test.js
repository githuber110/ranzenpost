import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const ENTRY = {
  id: "older:481", kind: "absence", source: "older_page", label_key: "absence.entry.kind.absence",
  from_date: "2126-09-14", till_date: "2126-09-14", student_id: "c-mia", status: "open", deletable: false,
  detail: true, locked_reason_key: "api.absence.older.locked", technical: { id: "481", created_at: "", class_code: "" },
};

async function settle(window, ticks = 8) {
  for (let tick = 0; tick < ticks; tick += 1) await new Promise((resolve) => window.setTimeout(resolve, 0));
}

function serve(window, detail, upload) {
  const sent = [];
  window.fetch = (url, options) => {
    const target = new URL(String(url));
    sent.push({ path: target.pathname, search: target.search, method: (options && options.method) || "GET", body: options && options.body });
    const body = target.pathname === "/api/absences/older-detail" ? detail : upload;
    return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve(body) });
  };
  return sent;
}

function openDetail(window, entry) {
  evalWith(window, "state.absence = { data: { source: 'older_page', children: [{ id: 'c-mia', name: 'Mia' }], rules: {} }, connectionId: 'a1' }; openAbsenceSheet(testArgs[0]);", entry);
  return window.eval("state.sheet()");
}

describe("attachments of an older absence entry", () => {
  test("lists the files the school shows and offers an upload with the privacy hint", async () => {
    const { window } = loadApp();
    const sent = serve(window, { ok: true, attachments: [{ key: "k-attest", name: "Attest.pdf" }], can_upload: true });
    const scrim = openDetail(window, ENTRY);
    await settle(window);
    const asked = sent.filter((request) => request.path === "/api/absences/older-detail");
    expect(asked).toHaveLength(1);
    expect(asked[0].search).toContain("id=older%3A481");
    const block = scrim.querySelector(".older-attachments");
    expect(block.textContent).toContain("Attest.pdf");
    expect(block.textContent).toContain(window.t("absence.attachments.add"));
    expect(block.textContent).toContain(window.t("absence.older.attachHint"));
    expect(block.querySelector("a[href]")).toBeNull();
  });

  test("an entry without attachments or upload shows no attachment block", async () => {
    const { window } = loadApp();
    serve(window, { ok: true, attachments: [], can_upload: false });
    const scrim = openDetail(window, ENTRY);
    await settle(window);
    expect(scrim.querySelector(".older-attachments")).toBeNull();
  });

  test("an entry without a detail page asks nothing", async () => {
    const { window } = loadApp();
    const sent = serve(window, { ok: true, attachments: [], can_upload: true });
    openDetail(window, Object.assign({}, ENTRY, { detail: false }));
    await settle(window);
    expect(sent.filter((request) => request.path.startsWith("/api/absences/older"))).toEqual([]);
  });

  test("an upload is sent only after the confirmation", async () => {
    const { window } = loadApp();
    const sent = serve(window, { ok: true, attachments: [], can_upload: true }, { ok: true, message_key: "api.absence.older.attached" });
    const scrim = openDetail(window, ENTRY);
    await settle(window);
    const input = scrim.querySelector(".older-attachments input[type=file]");
    const file = new window.File(["%PDF"], "brief.pdf", { type: "application/pdf" });
    Object.defineProperty(input, "files", { value: [file], configurable: true });
    input.dispatchEvent(new window.Event("change"));
    await settle(window);
    expect(sent.filter((request) => request.method === "POST")).toEqual([]);
    const confirm = window.eval("state.sheet()").querySelector(".btn-stack .btn:not(.ghost)");
    expect(confirm.textContent).toBe(window.t("absence.confirm.button"));
    confirm.click();
    await settle(window);
    const posts = sent.filter((request) => request.method === "POST");
    expect(posts).toHaveLength(1);
    expect(posts[0].path).toBe("/api/absences/older-attachment");
    expect(JSON.parse(posts[0].body.get("data"))).toEqual({ connection_id: "a1", id: "older:481" });
    expect(posts[0].body.get("files").name).toBe("brief.pdf");
    expect(window.eval("state.toast && state.toast.message")).toBe(window.t("api.absence.older.attached"));
  });
});
