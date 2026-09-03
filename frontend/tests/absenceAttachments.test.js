import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";
import { openWizard } from "./absenceWizard.js";

function setFiles(window, input, files) {
  Object.defineProperty(input, "files", { value: files, configurable: true });
  input.dispatchEvent(new window.Event("change"));
}

const DATA = { children: [{ id: 1 }], types: ["leave"], rules: {} };

function openAttachments(window) {
  const wz = openWizard(window, "leave", DATA);
  wz.go("leaveAttachments");
  return wz;
}

describe("[P116] Beurlaubung: attachment picker lives on a branch off the review page", () => {
  test("attachments are not a forward step but reachable from the review page", () => {
    const { window } = loadApp();
    const wz = openWizard(window, "leave", DATA);
    expect(wz.path).not.toContain("leaveAttachments");
    wz.form.body = "Begruendung";
    wz.go("review");
    expect(wz.step).toBe("review");
    const row = Array.from(wz.body.querySelectorAll(".sw-fact")).find((node) =>
      node.textContent.includes("Anlagen")
    );
    expect(row).toBeTruthy();
    expect(row.textContent).toContain("keine Angabe");
    row.click();
    expect(wz.step).toBe("leaveAttachments");
    expect(wz.nextButton.textContent).toBe("Zur Prüfung");
  });

  test("adding a file lists it with a remove-X button", () => {
    const { window } = loadApp();
    const wz = openAttachments(window);
    const input = wz.body.querySelector('input[type="file"]');
    expect(input.multiple).toBe(true);
    setFiles(window, input, [new window.File(["x"], "beleg.pdf", { type: "application/pdf" })]);
    expect(wz.body.textContent).toContain("beleg.pdf");
    expect(wz.body.querySelector(".search-clear")).not.toBeNull();
  });

  test("clicking remove-X drops the file from form.attachments and the list", () => {
    const { window } = loadApp();
    const wz = openAttachments(window);
    const input = wz.body.querySelector('input[type="file"]');
    setFiles(window, input, [new window.File(["x"], "beleg.pdf", { type: "application/pdf" })]);
    wz.body.querySelector(".search-clear").click();
    expect(wz.form.attachments.length).toBe(0);
    expect(wz.body.textContent).not.toContain("beleg.pdf");
  });

  test("multiple files can be chosen, each with its own remove-X", () => {
    const { window } = loadApp();
    const wz = openAttachments(window);
    const input = wz.body.querySelector('input[type="file"]');
    setFiles(window, input, [
      new window.File(["x"], "a.pdf", { type: "application/pdf" }),
      new window.File(["y"], "b.pdf", { type: "application/pdf" }),
    ]);
    expect(wz.form.attachments.length).toBe(2);
    expect(wz.body.querySelectorAll(".search-clear").length).toBe(2);
  });

  test("a file over 10MB warns next to the file and locks the branch step with a short reason", () => {
    const { window } = loadApp();
    const wz = openAttachments(window);
    const input = wz.body.querySelector('input[type="file"]');
    setFiles(window, input, [
      new window.File([new Uint8Array(11 * 1024 * 1024)], "big.pdf", { type: "application/pdf" }),
    ]);
    expect(wz.body.textContent).toContain("Größer als 10 MB");
    expect(wz.form.attachments.length).toBe(1);
    expect(wz.status).toBe("Datei über 10 MB");
    expect(wz.nextButton.getAttribute("aria-disabled")).toBe("true");
    expect(window.eval("absenceProblem(state.absenceForm, state.absence.data)")).toContain("Größer als 10 MB");
  });

  test("attachments together over 40MB are caught here, before the send", () => {
    const { window } = loadApp();
    const wz = openAttachments(window);
    const input = wz.body.querySelector('input[type="file"]');
    setFiles(
      window,
      input,
      [1, 2, 3, 4, 5].map(
        (index) => new window.File([new Uint8Array(9 * 1024 * 1024)], `f${index}.pdf`, { type: "application/pdf" })
      )
    );
    expect(wz.status).toBe("Anlagen über 40 MB");
    expect(window.eval("absenceProblem(state.absenceForm, state.absence.data)")).toContain("40 MB");
  });

  test("the file input carries no accept restriction", () => {
    const { window } = loadApp();
    const wz = openAttachments(window);
    expect(wz.body.querySelector('input[type="file"]').hasAttribute("accept")).toBe(false);
  });

  test("the file input carries no capture attribute (keeps iOS system chooser)", () => {
    const { window } = loadApp();
    const wz = openAttachments(window);
    expect(wz.body.querySelector('input[type="file"]').hasAttribute("capture")).toBe(false);
  });
});

describe("[P116] Beurlaubung: multipart submit path", () => {
  test("submitting without attachments still posts plain JSON", async () => {
    const { window } = loadApp();
    const wz = openWizard(window, "leave", DATA);
    wz.form.subject = "Test";
    wz.form.body = "Text";
    const calls = [];
    window.fetch = (url, opts) => {
      calls.push({ url, opts });
      return Promise.resolve({ json: () => Promise.resolve({ ok: true, message: "ok" }) });
    };
    await window.eval("submitAbsence()");
    const posts = calls.filter((c) => c.opts && c.opts.method === "POST");
    expect(posts.length).toBe(1);
    expect(posts[0].opts.body instanceof window.FormData).toBe(false);
    expect(JSON.parse(posts[0].opts.body).subject).toBe("Test");
  });

  test("submitting with attachments posts multipart/form-data instead of JSON", async () => {
    const { window } = loadApp();
    const wz = openAttachments(window);
    wz.form.subject = "Test";
    wz.form.body = "Text";
    const input = wz.body.querySelector('input[type="file"]');
    setFiles(window, input, [new window.File(["x"], "beleg.pdf", { type: "application/pdf" })]);

    const calls = [];
    window.fetch = (url, opts) => {
      calls.push({ url, opts });
      return Promise.resolve({ json: () => Promise.resolve({ ok: true, message: "ok" }) });
    };
    await window.eval("submitAbsence()");
    const posts = calls.filter((c) => c.opts && c.opts.method === "POST");
    expect(posts.length).toBe(1);
    expect(posts[0].url).toBe("http://localhost/api/absences");
    expect(posts[0].opts.body instanceof window.FormData).toBe(true);
    const files = posts[0].opts.body.getAll("files");
    expect(files.length).toBe(1);
    expect(files[0].name).toBe("beleg.pdf");
    const payload = JSON.parse(posts[0].opts.body.get("data"));
    expect(payload.subject).toBe("Test");
    expect(payload.attachments).toBeUndefined();
  });
});
