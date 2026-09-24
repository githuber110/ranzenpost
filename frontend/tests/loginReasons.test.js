import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function jsonResponse(body) {
  return Promise.resolve({
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    json: () => Promise.resolve(body),
  });
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function quiet(window) {
  window.clearTimeout(window.eval("bootWatchdog"));
  for (let round = 0; round < 6; round += 1) await flush();
  window.clearTimeout(window.eval("bootWatchdog"));
}

function label(window, key) {
  return window.eval(`t(${JSON.stringify(key)})`);
}

const SETUP_STEP = {
  step: "connect",
  school_url: "https://myschool.example",
  has_2fa: true,
  needs_2fa_setup: true,
  verified_2fa: false,
};

async function openWizard(states) {
  const { window, document } = loadApp();
  window.fetch = (path) => {
    if (String(path).includes("api/wizard")) return jsonResponse(states.length > 1 ? states.shift() : states[0]);
    return Promise.reject(new Error("unexpected fetch " + path));
  };
  const app = document.getElementById("app");
  await flush();
  window.renderWizard(app, () => {});
  await flush();
  return { app, window };
}

describe("a school that forces two-factor later", () => {
  test("the connect step explains the setup in the browser instead of showing an error", async () => {
    const { app, window } = await openWizard([SETUP_STEP]);
    const text = app.textContent;
    expect(text).toContain(label(window, "wizard.connect.setupRequired"));
    expect(text).not.toContain(label(window, "wizard.connect.text"));
    expect(text).not.toContain(label(window, "wizard.connect.privacy"));
    expect(app.querySelector(".wz-error")).toBeNull();
    expect(app.querySelector('input[name="code"]')).toBeTruthy();
  });

  test("a normal two-factor login keeps the usual connect text", async () => {
    const { app, window } = await openWizard([{ ...SETUP_STEP, needs_2fa_setup: false }]);
    expect(app.textContent).toContain(label(window, "wizard.connect.text"));
    expect(app.textContent).not.toContain(label(window, "wizard.connect.setupRequired"));
  });

  test("a code while IServ still waits for the setup names that and keeps the explanation", async () => {
    const { app, window } = await openWizard([
      { ...SETUP_STEP, error: { code: "twofactor_required_setup", message_key: "api.wizard.twofactorSetupPending" } },
    ]);
    expect(app.querySelector(".wz-error").textContent).toContain(label(window, "api.wizard.twofactorSetupPending"));
    expect(app.textContent).toContain(label(window, "wizard.connect.setupRequired"));
  });

  test("the wizard names an unknown account and a blocked default password", async () => {
    for (const [code, key] of [
      ["unknown_account", "api.lockout.unknownAccount"],
      ["default_password_blocked", "api.lockout.defaultPassword"],
    ]) {
      const { app, window } = await openWizard([
        { step: "login", school_url: "https://myschool.example", error: { code, message_key: key } },
      ]);
      expect(app.querySelector(".wz-error").textContent).toContain(label(window, key));
    }
  });
});

describe("the reconnect page names why IServ refused", () => {
  test("a forced two-factor setup offers the setup as the one main action", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    const posted = [];
    window.fetch = (path, options) => {
      posted.push(String(path));
      if (String(path).includes("api/wizard")) return jsonResponse({ step: "url" });
      return Promise.reject(new Error("unexpected fetch " + path));
    };
    const app = document.getElementById("app");
    window.renderReconnect(app, "parent.one", "c1", "twofactor_required_setup");
    expect(app.textContent).toContain(label(window, "api.login.twofactorSetup"));
    expect(app.querySelector('input[name="password"]')).toBeNull();
    const buttons = [...app.querySelectorAll("button")];
    expect(buttons.filter((button) => !button.classList.contains("ghost"))).toHaveLength(1);
    const setup = buttons.find((button) => button.textContent === label(window, "account.reconnect.setupTwofactor"));
    expect(setup).toBeTruthy();
    setup.click();
    await flush();
    expect(posted.some((path) => path.includes("api/wizard/reset"))).toBe(false);
    const panel = app.querySelector(".sheet-confirm");
    expect(panel).toBeTruthy();
    expect(panel.textContent).toContain(label(window, "account.reconnect.setupNote"));
    panel.querySelector(".btn.ghost").click();
    expect(app.querySelector(".sheet-confirm")).toBeNull();
    setup.click();
    app.querySelector(".sheet-confirm .btn.destructive").click();
    await flush();
    expect(posted.some((path) => path.includes("api/wizard/reset"))).toBe(true);
  });

  test("a refused confirmation code offers the new setup as the one main action and no password form", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    const posted = [];
    window.fetch = (path) => {
      posted.push(String(path));
      if (String(path).includes("api/wizard")) return jsonResponse({ step: "url" });
      return Promise.reject(new Error("unexpected fetch " + path));
    };
    const app = document.getElementById("app");
    window.renderReconnect(app, "parent.one", "c1", "code_step_failed");
    expect(app.querySelector(".reconnect-reason").textContent).toBe(label(window, "api.login.twofactor"));
    expect(app.querySelector('input[name="password"]')).toBeNull();
    expect(app.textContent).not.toContain(label(window, "account.reconnect.submit"));
    expect(app.textContent).not.toContain(label(window, "account.reconnect.resetText"));
    const buttons = [...app.querySelectorAll("button")];
    const main = buttons.filter((button) => !button.classList.contains("ghost"));
    expect(main).toHaveLength(1);
    expect(main[0].textContent).toBe(label(window, "account.reconnect.reset"));
    expect(buttons.filter((button) => button.textContent === label(window, "account.reconnect.reset"))).toHaveLength(1);
    main[0].click();
    await flush();
    const panel = app.querySelector(".sheet-confirm");
    expect(panel.textContent).toContain(label(window, "account.reconnect.resetNote"));
    expect(posted.some((path) => path.includes("api/wizard/reset"))).toBe(false);
    panel.querySelector(".btn.destructive").click();
    await flush();
    expect(posted.some((path) => path.includes("api/wizard/reset"))).toBe(true);
    expect(posted.some((path) => path.includes("api/password/repair"))).toBe(false);
  });

  test("an unknown account and a default password keep the password form and name the reason", async () => {
    for (const [reason, key] of [
      ["unknown_account", "api.login.unknownAccount"],
      ["default_password_blocked", "api.login.defaultPassword"],
      ["session_not_opened", "api.login.session"],
    ]) {
      const { window, document } = loadApp();
      await quiet(window);
      const app = document.getElementById("app");
      window.renderReconnect(app, "parent.one", "c1", reason);
      expect(app.querySelector(".reconnect-reason").textContent).toBe(label(window, key));
      expect(app.querySelector('input[name="password"]')).toBeTruthy();
    }
  });

  test("a school whose sign-in opened no session shows that at start and not an unreachable IServ", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    window.fetch = (path) => {
      if (String(path).includes("api/health")) {
        return jsonResponse({
          status: "ok",
          configured: true,
          connection: "auth_failed",
          auth_reason: "session_not_opened",
          username: "parent.one",
          connection_id: "c1",
          language: "de",
        });
      }
      return Promise.reject(new Error("unexpected fetch " + path));
    };
    await window.eval("boot")();
    const app = document.getElementById("app");
    expect(app.querySelector(".reconnect-reason").textContent).toBe(label(window, "api.login.session"));
    expect(app.textContent).not.toContain(label(window, "app.error.unreachable.title"));
  });

  test("without a reason the page reads as before", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    const app = document.getElementById("app");
    window.renderReconnect(app, "parent.one", "c1", "");
    expect(app.querySelector(".reconnect-reason").textContent).toBe(label(window, "account.reconnect.text"));
  });

  test("a read that fails because no session opened names that and not a changed password", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    window.eval("state.account = 'parent.one';");
    const error = window.eval('apiError("auth_failed", { error: "auth_failed", message_key: "api.login.session" })');
    expect(window.eval("loginReasonOf")(error)).toBe("session_not_opened");
    window.eval("handleApiFailure")(error, "c1");
    const reason = document.getElementById("app").querySelector(".reconnect-reason").textContent;
    expect(reason).toBe(label(window, "api.login.session"));
    expect(reason).not.toBe(label(window, "account.reconnect.text"));
  });

  test("a refused confirmation code names the code and not a changed password, at start and on a read", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    window.fetch = (path) => {
      if (String(path).includes("api/health")) {
        return jsonResponse({
          status: "ok",
          configured: true,
          connection: "auth_failed",
          auth_reason: "code_step_failed",
          username: "parent.one",
          connection_id: "c1",
          language: "de",
        });
      }
      return Promise.reject(new Error("unexpected fetch " + path));
    };
    await window.eval("boot")();
    const app = document.getElementById("app");
    expect(app.querySelector(".reconnect-reason").textContent).toBe(label(window, "api.login.twofactor"));
    const error = window.eval('apiError("auth_failed", { error: "auth_failed", message_key: "api.login.twofactor" })');
    expect(window.eval("loginReasonOf")(error)).toBe("code_step_failed");
  });

  test("a read that fails with the setup message routes to the setup page", async () => {
    const { window, document } = loadApp();
    await quiet(window);
    window.eval("state.account = 'parent.one';");
    const error = window.eval(
      'apiError("auth_failed", { error: "auth_failed", message_key: "api.login.twofactorSetup" })'
    );
    expect(window.eval("loginReasonOf")(error)).toBe("twofactor_required_setup");
    window.eval("handleApiFailure")(error, "c1");
    expect(document.getElementById("app").textContent).toContain(label(window, "account.reconnect.setupTwofactor"));
  });
});
