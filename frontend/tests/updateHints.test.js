import { describe, expect, test } from "vitest";
import { evalWith, loadApp } from "./loadApp.js";

const TOKEN = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG";
const LANGUAGES = ["de", "en", "ar", "tr", "ru", "uk"];

function status(overrides = {}) {
  return {
    connected: true,
    last_request: "2026-09-02T08:10:00+02:00",
    token: TOKEN,
    port: 8099,
    app_version: "2609.4.1",
    integration_version: "2609.4.1",
    integration_installed: "",
    updates: [],
    ...overrides,
  };
}

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function setup(answer = status()) {
  const app = loadApp();
  const { window } = app;
  for (let round = 0; round < 8; round += 1) await tick();
  window.eval("state.config = { notify_services: [], notify_events: {}, phones: [], period_times: {}, reported_modules: [] }; state.haStatus = null; state.haStatusLoading = false;");
  window.fetch = (url) => {
    const target = String(url);
    if (target.includes("api/integration-status")) {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(answer) });
    }
    return Promise.reject(new Error(`unexpected request ${target}`));
  };
  window.eval("settingsView()");
  await tick();
  await tick();
  return app;
}

function label(window, key, vars) {
  return evalWith(window, "t(testArgs[0], testArgs[1])", key, vars || null);
}

function steps(root) {
  return [...root.querySelectorAll(".update-step")].map((node) => [...node.classList].find((name) => name.startsWith("update-") && name !== "update-step"));
}

describe("the settings tell which side still needs its update", () => {
  test("matching versions show no hint and the row stays on the connection state", async () => {
    const { window } = await setup();
    const view = window.eval("settingsView()");

    expect(view.querySelector(".update-hint")).toBeNull();
    expect(view.querySelector(".ha-setting .val").textContent).toBe(label(window, "settings.ha.status.connected"));
  });

  test("an app behind the integration leads the settings with the app update path", async () => {
    const { window } = await setup(status({ app_version: "2609.3.0", integration_version: "2609.4.0", updates: ["app"] }));
    const view = window.eval("settingsView()");

    const hint = view.firstElementChild;
    expect(hint.classList.contains("update-hint")).toBe(true);
    expect(hint.getAttribute("role")).toBe("status");
    expect(steps(hint)).toEqual(["update-app"]);
    expect(hint.querySelector(".update-title").textContent).toBe(label(window, "settings.update.app.title"));
    expect(hint.querySelector(".update-text").textContent).toBe(
      label(window, "settings.update.app.text", { app: "2609.3.0", integration: "2609.4.0", installed: "" })
    );
    expect(hint.querySelectorAll("button, a").length).toBe(0);
    expect(view.querySelector(".ha-setting .val").textContent).toBe(label(window, "settings.ha.status.update"));
  });

  test("an integration behind the app and a pending restart show both steps in order", async () => {
    const { window } = await setup(
      status({ app_version: "2609.4.1", integration_version: "2609.3.0", integration_installed: "2609.4.0", updates: ["restart", "integration"] })
    );
    const view = window.eval("settingsView()");
    const hint = view.querySelector(".update-hint");

    expect(steps(hint)).toEqual(["update-integration", "update-restart"]);
    const texts = [...hint.querySelectorAll(".update-text")].map((node) => node.textContent);
    expect(texts[1]).toBe(label(window, "settings.update.restart.text", { app: "2609.4.1", integration: "2609.3.0", installed: "2609.4.0" }));
    expect(texts[1]).toContain("2609.4.0");
    expect(texts[1]).toContain("2609.3.0");
  });

  test("the app step names the installed integration while a restart is still pending", async () => {
    const { window } = await setup(
      status({ app_version: "2609.3.0", integration_version: "2609.3.0", integration_installed: "2609.4.0", updates: ["app", "restart"] })
    );
    const hint = window.eval("settingsView()").querySelector(".update-hint");

    expect(steps(hint)).toEqual(["update-app", "update-restart"]);
    expect(hint.querySelector(".update-app .update-text").textContent).toContain("2609.4.0");
  });

  test("an integration too old to name its version is still asked to update", async () => {
    const { window } = await setup(status({ app_version: "2609.4.1", integration_version: "", updates: ["integration"] }));
    const hint = window.eval("settingsView()").querySelector(".update-hint");

    expect(steps(hint)).toEqual(["update-integration"]);
    expect(hint.querySelector(".update-text").textContent).toBe(label(window, "settings.update.integration.older", { app: "2609.4.1" }));
  });

  test("unknown steps from a newer app are ignored", async () => {
    const { window } = await setup(status({ updates: ["something-new"] }));

    expect(window.eval("settingsView()").querySelector(".update-hint")).toBeNull();
  });

  test("the Home Assistant sheet and the help page repeat the hint", async () => {
    const app = await setup(status({ app_version: "2609.3.0", integration_version: "2609.4.0", updates: ["app"] }));
    const { window, document } = app;

    await window.eval("openHomeAssistantSheet()");
    await tick();
    await tick();
    const sheet = document.querySelector(".sheet");
    expect(steps(sheet.querySelector(".update-hint"))).toEqual(["update-app"]);

    window.eval("dropSheet()");
    const help = window.eval("helpPageView()");
    expect(help.firstElementChild.classList.contains("update-hint")).toBe(true);
  });

  test("the problem report issue names the integration version", async () => {
    const { window } = await setup();
    window.eval('state.helpFacts = { app: "2609.4.1", integration: "2609.4.0", home_assistant: "2026.9.1", iserv: "3.9.1" };');

    expect(window.eval("helpIssueBody()")).toContain("integration 2609.4.0");
  });
});

describe("the update texts in every language", () => {
  test("carry the versions and the Home Assistant path", async () => {
    const { readFileSync } = await import("node:fs");
    const { dirname, join } = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const here = dirname(fileURLToPath(import.meta.url));
    for (const language of LANGUAGES) {
      const bundle = JSON.parse(readFileSync(join(here, "..", "i18n", `${language}.json`), "utf8"));
      expect(bundle["settings.update.app.text"], language).toContain("{app}");
      expect(bundle["settings.update.app.text"], language).toContain("{integration}");
      expect(bundle["settings.update.app.text"], language).toContain("Ranzenpost");
      expect(bundle["settings.update.integration.text"], language).toContain("HACS");
      expect(bundle["settings.update.restart.text"], language).toContain("{installed}");
      expect(bundle["settings.update.restart.text"], language).toContain("Home Assistant");
      expect(bundle["settings.update.restart.text"].split(/[.。]\s+/).at(-1), language).toContain("Home Assistant");
      for (const key of ["help.noStart", "help.report.failed", "settings.notify.noSupervisor"]) {
        expect(bundle[key].toLowerCase(), `${language}.${key}`).not.toContain("add-on");
      }
    }
    const english = JSON.parse(readFileSync(join(here, "..", "i18n", "en.json"), "utf8"));
    expect(english["settings.update.app.text"]).toContain("Settings → Apps");
    expect(english["settings.update.app.text"]).toContain("Check for updates");
    expect(english["settings.update.restart.text"]).toContain("Home Assistant also offers the restart as a repair in its Settings.");
    const german = JSON.parse(readFileSync(join(here, "..", "i18n", "de.json"), "utf8"));
    expect(german["settings.update.app.text"]).toContain("Einstellungen → Apps");
    expect(german["settings.update.app.text"]).toContain("„Nach Updates suchen“");
  });
});
