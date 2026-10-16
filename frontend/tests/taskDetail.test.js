import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function task(extra = {}) {
  return {
    id: "31", title: "Fractions", start: "2026-10-01", start_text: "01.10.2026", due: "2026-10-20T18:00", due_text: "20.10.2026 18:00",
    tags: ["Maths"], done: false, done_text: "", past: false, path: "/iserv/exercise/show/31", extra: [],
    connection_id: "a1b2c3d4", school: "Riverside", ...extra,
  };
}

function detail(extra = {}) {
  return {
    text: ["Solve exercises 1 to 4.", "Hand in a photo."],
    facts: [{ label: "Teacher", value: "Teacher A" }, { label: "Abgabetermin", value: "20.10.2026 18:00" }],
    start: "2026-10-01", start_text: "01.10.2026", due: "2026-10-20T18:00", due_text: "20.10.2026 18:00", tags: ["Maths"], state_text: "Started",
    files: [{ label: "worksheet.pdf", meta: "120 KB", path: "/iserv/fs/file/exercise-dl/31/worksheet.pdf" }],
    images: [],
    links: [{ label: "Video", url: "https://video.example.org/fractions" }],
    submission: { text: [], facts: [], files: [{ label: "page-12.jpg", meta: "2 MB", path: "/iserv/fs/file/exercise-submission/701/page-12.jpg" }], links: [] },
    feedback: { text: ["Well done."], facts: [{ label: "Feedback from", value: "Teacher B" }], files: [{ label: "corrections.pdf", path: "/iserv/fs/file/exercise-feedback/901/corrections.pdf" }], links: [] },
    solution: { text: [], facts: [], files: [], links: [] },
    actions: {
      upload: { form: "f-upload", multiple: true, accept: "" },
      text: { form: "f-text", text: ["My answer"], max_length: 0 },
      confirm: { form: "f-confirm" },
      delete: [{ form: "f-files", target: 0, label: "page-12.jpg", value: "701", file: 0 }],
    },
    read_at: 1,
    ...extra,
  };
}

function seed(window) {
  evalWith(window, `
    state.children = [];
    state.childrenRead = true;
    state.me = { forename: "Sam" };
    state.config = { notify_services: [], notify_events: {}, phones: [], period_times: {} };
    state.modules = applyModules({ modules: { tasks: true, news: true } });
    state.view = "tasks";
  `);
}

function answer(body, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body), headers: { get: () => "" } });
}

function stubFetch(window, route, calls) {
  window.fetch = (url, options = {}) => {
    const call = { url: String(url), method: options.method || "GET", body: options.body };
    calls.push(call);
    return route(call);
  };
}

function sheetNode(window) {
  return window.eval("state.sheet && state.sheet()");
}

function texts(nodes) {
  return [...nodes].map((node) => node.textContent);
}

function openWith(window, entry) {
  evalWith(window, "openTask(testArgs[0])", entry);
}

describe("a task opens with what IServ shows on its page", () => {
  test("opening reads the task page on demand and shows text, facts, files, the hand-in and feedback without links out", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    stubFetch(window, () => answer(detail()), calls);
    openWith(window, task());
    expect(calls.map((call) => call.url)).toEqual(["http://localhost/api/tasks/detail?connection=a1b2c3d4&task=31"]);
    expect(sheetNode(window).querySelector(".loading")).not.toBeNull();
    await settle();
    await settle();
    const node = sheetNode(window);
    expect(node.querySelector(".loading")).toBeNull();
    expect(texts(node.querySelectorAll(".news-text p")).slice(0, 2)).toEqual(["Solve exercises 1 to 4.", "Hand in a photo."]);
    expect(texts(node.querySelectorAll(".task-facts .field-label"))).toContain("Teacher");
    expect(texts(node.querySelectorAll(".task-facts .field-label"))).not.toContain("Abgabetermin");
    expect(node.querySelector(".row-meta").textContent).toContain("Started");
    expect(texts(node.querySelectorAll(".section-head .overline"))).toEqual(["Dateien", "Links", "Abgabe", "Rückmeldung"]);
    expect(texts(node.querySelectorAll("button.row .row-title"))).toEqual(["worksheet.pdf", "page-12.jpg", "corrections.pdf"]);
    expect(texts(node.querySelectorAll("button.row .row-sub"))).toEqual(["120 KB", "2 MB"]);
    expect(texts(node.querySelectorAll(".task-own-text .news-text p"))).toEqual(["My answer"]);
    const buttons = [...node.querySelectorAll(".task-actions .btn")];
    expect(buttons.map((button) => button.textContent)).toEqual(["Dateien abgeben", "Text bearbeiten", "Als erledigt markieren", "Abgegebene Datei entfernen"]);
    expect(buttons.filter((button) => !button.classList.contains("ghost")).length).toBe(1);
    expect(node.querySelectorAll("[href], [target]").length).toBe(0);
    expect(node.textContent).not.toContain("noch nicht");
  });

  test("files go through Ranzenpost by task, kind and position", async () => {
    const { window } = loadApp();
    seed(window);
    stubFetch(window, () => answer(detail()), []);
    const files = evalWith(window, `(() => {
      const captured = [];
      const original = attachmentRows;
      attachmentRows = (list) => { captured.push(...list); return original(list); };
      keepTaskDetail(testArgs[0], testArgs[1]);
      taskDetailParts(testArgs[0]);
      attachmentRows = original;
      return captured.map((file) => file.url);
    })()`, task(), detail());
    expect(files).toEqual([
      "api/tasks/file?connection=a1b2c3d4&task=31&kind=files&index=0",
      "api/tasks/file?connection=a1b2c3d4&task=31&kind=submission&index=0",
      "api/tasks/file?connection=a1b2c3d4&task=31&kind=feedback&index=0",
    ]);
  });

  test("a detail kept from the last open shows at once and is read again", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    stubFetch(window, () => new Promise(() => {}), calls);
    openWith(window, task({ detail: detail({ text: ["Earlier text."] }) }));
    const node = sheetNode(window);
    expect(texts(node.querySelectorAll(".news-text p"))[0]).toBe("Earlier text.");
    expect(node.querySelector(".stamp").textContent).toBe("Aufgabe wird neu gelesen …");
    expect([...node.querySelectorAll(".task-actions .btn")].every((button) => button.disabled)).toBe(true);
    expect(calls.filter((call) => call.url.includes("api/tasks/detail")).length).toBe(1);
  });

  test("a failed read says so, keeps the earlier detail and offers a retry", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    stubFetch(window, () => answer({ error: "network", message_key: "api.tasks.unknown" }), calls);
    openWith(window, task({ detail: detail() }));
    await settle();
    await settle();
    const node = sheetNode(window);
    expect(node.querySelector(".task-failed .note").textContent).toBe("Diese Aufgabe ist nicht mehr in der Liste. Zu sehen ist der zuletzt gelesene Stand.");
    node.querySelector(".task-failed .btn").click();
    expect(calls.filter((call) => call.url.includes("api/tasks/detail")).length).toBe(2);
  });

  test("a task without its own page is never requested", () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    stubFetch(window, () => answer(detail()), calls);
    openWith(window, task({ path: "", extra: [{ label: "Fach", value: "Mathe" }] }));
    expect(calls).toEqual([]);
    const node = sheetNode(window);
    expect(node.querySelector(".note").textContent).toBe("IServ zeigt zu dieser Aufgabe keine eigene Seite.");
    expect(texts(node.querySelectorAll(".task-facts .fact"))).toEqual(["Mathe"]);
  });

  test("taking back or removing is never the loud button of the hand-in block", () => {
    const { window } = loadApp();
    seed(window);
    const quiet = detail({ actions: { undo: { form: "f-undo" }, delete: [{ form: "f-files", target: 0, label: "page-12.jpg", file: 0 }] } });
    evalWith(window, "keepTaskDetail(testArgs[0], testArgs[1]); state.taskOpen = { key: taskKey(testArgs[0]), loading: false, failed: '', busy: '', outcome: null };", task(), quiet);
    const parts = evalWith(window, "taskDetailParts(testArgs[0])", task());
    const body = window.document.createElement("div");
    body.append(...parts.body.filter(Boolean));
    const buttons = [...body.querySelectorAll(".task-actions .btn")];
    expect(buttons.map((button) => button.textContent)).toEqual(["Als nicht erledigt markieren", "Abgegebene Datei entfernen"]);
    expect(buttons.every((button) => button.classList.contains("ghost"))).toBe(true);
  });

  test("a form Ranzenpost does not recognise is named without sending anyone to IServ", () => {
    const { window } = loadApp();
    seed(window);
    evalWith(window, "keepTaskDetail(testArgs[0], testArgs[1]); state.taskOpen = { key: taskKey(testArgs[0]), loading: false, failed: '', busy: '', outcome: null };", task(), detail({ actions: {}, unrecognised: 1 }));
    const parts = evalWith(window, "taskDetailParts(testArgs[0])", task());
    const body = window.document.createElement("div");
    body.append(...parts.body.filter(Boolean));
    expect(body.querySelector(".task-unrecognised").textContent).toBe("Die Seite enthält ein Formular, das Ranzenpost noch nicht erkennt. Der Problembericht hält seinen Aufbau fest.");
  });

  test("a page without any hand-in form says that IServ offers none", () => {
    const { window } = loadApp();
    seed(window);
    evalWith(window, "keepTaskDetail(testArgs[0], testArgs[1]); state.taskOpen = { key: taskKey(testArgs[0]), loading: false, failed: '', busy: '', outcome: null };", task({ past: true }), detail({ actions: {} }));
    const parts = evalWith(window, "taskDetailParts(testArgs[0])", task({ past: true }));
    const body = window.document.createElement("div");
    body.append(...parts.body.filter(Boolean));
    expect(body.querySelector(".task-actions")).toBeNull();
    expect(body.querySelector(".sheet-hint").textContent).toBe("IServ bietet bei dieser Aufgabe gerade keine Abgabe an.");
  });
});

async function opened(window, route, calls, entry = task()) {
  stubFetch(window, (call) => (call.url.includes("api/tasks/detail") ? answer(detail()) : route(call)), calls);
  openWith(window, entry);
  await settle();
  await settle();
}

describe("handing in happens in the app after a confirmation", () => {
  test("files are chosen, shown again and only then sent as one multipart request", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    const after = detail({ submission: { text: [], facts: [], files: [{ label: "page-12.jpg", path: "/a" }, { label: "essay.pdf", path: "/b" }], links: [] } });
    await opened(window, () => answer({ ok: true, outcome: "done", message_key: "api.tasks.act.done", detail: after }), calls);
    sheetNode(window).querySelector(".task-act-upload").click();
    let node = sheetNode(window);
    expect(node.querySelector(".sheet-title").textContent).toBe("Dateien abgeben");
    expect(node.querySelector(".task-upload-next").disabled).toBe(true);
    const file = new window.File(["%PDF"], "essay.pdf", { type: "application/pdf" });
    window.eval("(file) => { state.taskOpen.upload.files = [file]; rerender(); }")(file);
    node = sheetNode(window);
    expect(node.querySelector(".task-upload-next").disabled).toBe(false);
    node.querySelector(".task-upload-next").click();
    node = sheetNode(window);
    expect(node.querySelector(".dlg-text").textContent).toBe("Diese Dateien gehen als Abgabe zu „Fractions“ an die Schule.");
    expect(calls.filter((call) => call.url.includes("api/tasks/act"))).toEqual([]);
    node.querySelector(".task-upload-send").click();
    await settle();
    await settle();
    const sent = calls.filter((call) => call.url.includes("api/tasks/act"));
    expect(sent.length).toBe(1);
    expect(sent[0].method).toBe("POST");
    const body = JSON.parse(sent[0].body.get("data"));
    expect(body).toEqual({ connection_id: "a1b2c3d4", task_id: "31", action: "upload", form: "f-upload", confirmed: true });
    expect(sent[0].body.getAll("files").map((entry) => entry.name)).toEqual(["essay.pdf"]);
    node = sheetNode(window);
    expect(node.querySelector(".sheet-title").textContent).toBe("Fractions");
    expect(node.querySelector(".task-outcome").classList.contains("info")).toBe(true);
    expect(texts(node.querySelectorAll("button.row .row-title"))).toContain("essay.pdf");
  });

  test("a text is written, previewed and sent with the confirmation", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    await opened(window, () => answer({ ok: true, outcome: "done", message_key: "api.tasks.act.done", detail: detail() }), calls);
    sheetNode(window).querySelector(".task-act-text").click();
    let node = sheetNode(window);
    const field = node.querySelector("textarea");
    expect(field.value).toBe("My answer");
    field.value = "  New answer\nsecond line ";
    field.dispatchEvent(new window.Event("input"));
    node.querySelector(".task-text-next").click();
    node = sheetNode(window);
    expect(node.querySelector(".task-text-quote").textContent).toBe("New answer\nsecond line");
    node.querySelector(".task-text-send").click();
    await settle();
    await settle();
    const sent = calls.filter((call) => call.url.includes("api/tasks/act"));
    expect(JSON.parse(sent[0].body)).toEqual({ connection_id: "a1b2c3d4", task_id: "31", action: "text", form: "f-text", text: "New answer\nsecond line", confirmed: true });
  });

  test("a rejected hand-in shows the school's own error texts", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    await opened(window, () => answer({ ok: false, outcome: "rejected", message_key: "api.tasks.act.rejected", errors: ["Die Datei ist zu groß."], detail: detail() }), calls);
    sheetNode(window).querySelector(".task-act-confirm").click();
    sheetNode(window).querySelector(".task-confirm-send").click();
    await settle();
    await settle();
    const node = sheetNode(window);
    expect(node.querySelector(".task-outcome").classList.contains("info")).toBe(false);
    expect(node.querySelector(".task-outcome-text > span").textContent).toBe("Die Schule hat die Abgabe nicht angenommen.");
    expect(texts(node.querySelectorAll(".task-outcome-error"))).toEqual(["Die Datei ist zu groß."]);
    expect(node.querySelector(".task-outcome-error").getAttribute("dir")).toBe("auto");
  });

  test("a lost answer is uncertain, is never sent again and the task is read again", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    await opened(window, () => Promise.reject(new Error("offline")), calls);
    sheetNode(window).querySelector(".task-act-confirm").click();
    sheetNode(window).querySelector(".task-confirm-send").click();
    await settle();
    await settle();
    await settle();
    expect(calls.filter((call) => call.url.includes("api/tasks/act")).length).toBe(1);
    expect(calls.filter((call) => call.url.includes("api/tasks/detail")).length).toBe(2);
    const node = sheetNode(window);
    expect(node.querySelector(".task-outcome-text > span").textContent).toBe("Unklar, ob die Schule die Änderung übernommen hat. Unten steht, was die Aufgabenseite jetzt zeigt.");
  });

  test("an answer without a reason after sending is uncertain, never \"nothing was sent\"", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    await opened(window, () => answer({ ok: false, error: "act_failed" }), calls);
    sheetNode(window).querySelector(".task-act-confirm").click();
    sheetNode(window).querySelector(".task-confirm-send").click();
    await settle();
    await settle();
    const node = sheetNode(window);
    expect(node.querySelector(".sheet-title").textContent).toBe("Fractions");
    expect(node.querySelector(".task-outcome-text > span").textContent).toBe("Unklar, ob die Schule die Änderung übernommen hat. Unten steht, was die Aufgabenseite jetzt zeigt.");
    expect(node.textContent).not.toContain("Es wurde nichts");
  });

  test("too many or too large files are stopped before sending", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    await opened(window, () => answer({ ok: true }), calls);
    sheetNode(window).querySelector(".task-act-upload").click();
    const many = Array.from({ length: 21 }, (_, index) => new window.File(["x"], `f${index}.pdf`));
    window.eval("(files) => { state.taskOpen.upload.files = files; rerender(); }")(many);
    let node = sheetNode(window);
    expect(node.querySelector(".task-upload-next").disabled).toBe(true);
    expect(node.querySelector(".note").textContent).toBe("Höchstens 20 Dateien auf einmal. Es wurde nichts gesendet.");
    const big = Array.from({ length: 3 }, (_, index) => {
      const file = new window.File(["x"], `big${index}.pdf`);
      Object.defineProperty(file, "size", { value: 40 * 1024 * 1024 });
      return file;
    });
    window.eval("(files) => { state.taskOpen.upload.files = files; rerender(); }")(big);
    node = sheetNode(window);
    expect(node.querySelector(".task-upload-next").disabled).toBe(true);
    expect(node.querySelector(".note").textContent).toBe("Die Dateien sind zusammen größer als 100 MB. Es wurde nichts gesendet.");
    expect(calls.filter((call) => call.url.includes("api/tasks/act"))).toEqual([]);
  });

  test("an input refusal keeps the confirmation sheet open with the reason", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    await opened(window, () => answer({ ok: false, message_key: "api.tasks.act.busy" }), calls);
    sheetNode(window).querySelector(".task-act-confirm").click();
    sheetNode(window).querySelector(".task-confirm-send").click();
    await settle();
    await settle();
    const node = sheetNode(window);
    expect(node.querySelector(".sheet-title").textContent).toBe("Als erledigt markieren");
    expect(node.querySelector(".note").textContent).toBe("Bei dieser Aufgabe läuft gerade schon eine Abgabe.");
  });

  test("removing a handed-in file asks first and names the file", async () => {
    const { window } = loadApp();
    seed(window);
    const calls = [];
    await opened(window, () => answer({ ok: true, outcome: "done", message_key: "api.tasks.act.done", detail: detail() }), calls);
    sheetNode(window).querySelector(".task-act-delete").click();
    const node = sheetNode(window);
    expect(node.querySelector(".dlg-text").textContent).toBe("„page-12.jpg“ wird aus der Abgabe in IServ gelöscht.");
    expect(node.querySelector(".task-remove-send").classList.contains("destructive")).toBe(true);
    node.querySelector(".task-remove-send").click();
    await settle();
    const sent = calls.filter((call) => call.url.includes("api/tasks/act"));
    expect(JSON.parse(sent[0].body)).toEqual({
      connection_id: "a1b2c3d4", task_id: "31", action: "delete", form: "f-files", target: 0, target_label: "page-12.jpg", target_value: "701", confirmed: true,
    });
  });
});
