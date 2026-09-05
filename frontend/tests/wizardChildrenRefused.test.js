import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function jsonResponse(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

const REFUSED = {
  error: "network",
  message_key: "api.children.forbidden",
  diagnosis: { status: 403, child_select: false, login_form: false },
};

function wizardAt(childrenAnswer, onSkip) {
  const { window, document } = loadApp();
  window.fetch = (path) => {
    const url = String(path);
    if (url.includes("api/wizard/skip-child")) {
      onSkip();
      return jsonResponse({ step: "done" });
    }
    if (url.includes("api/children")) return jsonResponse(childrenAnswer);
    if (url.includes("api/config")) return jsonResponse({});
    if (url.includes("api/wizard")) return jsonResponse({ step: "child", has_2fa: false });
    return Promise.reject(new Error("unexpected fetch " + path));
  };
  const app = document.getElementById("app");
  window.renderWizard(app, () => {});
  return { window, app };
}

describe("[P238] wizard: the school server refuses the area the children are listed in", () => {
  test("the reason is named instead of claiming the account has no child", async () => {
    let skipped = false;
    const { window, app } = wizardAt(REFUSED, () => { skipped = true; });
    await flush();
    await flush();

    expect(app.textContent).toContain(window.eval('t("api.children.forbidden")'));
    expect(app.textContent).not.toContain(window.eval('t("wizard.child.none.text")'));
    expect(skipped).toBe(false);
  });

  test("setting up can still be finished, which is the whole point", async () => {
    let skipped = false;
    const { window, app } = wizardAt(REFUSED, () => { skipped = true; });
    await flush();
    await flush();

    const finish = [...app.querySelectorAll("button")].find(
      (button) => button.textContent === window.eval('t("wizard.child.none.finish")')
    );
    expect(finish).toBeTruthy();
    finish.click();
    await flush();
    await flush();

    expect(skipped).toBe(true);
  });

  test("an account that really has no child keeps the wording it had", async () => {
    const { window, app } = wizardAt([], () => {});
    await flush();
    await flush();

    expect(app.textContent).toContain(window.eval('t("wizard.child.none.text")'));
    expect(app.textContent).not.toContain(window.eval('t("api.children.forbidden")'));
  });

  test("a child list that arrives is still offered for picking", async () => {
    const { window, app } = wizardAt(
      [{ child_id: "c1", name: "Kim", class_name: "3b" }],
      () => {}
    );
    await flush();
    await flush();

    expect(app.textContent).toContain("Kim");
    expect(app.textContent).not.toContain(window.eval('t("wizard.child.failed.title")'));
  });
});
