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
    const links = hint.querySelectorAll("button, a");
    expect(links.length).toBe(1);
    expect(links[0].textContent).toBe(label(window, "settings.update.app.open"));
    expect(links[0].getAttribute("href")).toBe("https://my.home-assistant.io/redirect/repairs/");
    expect(view.querySelector(".ha-setting .val").textContent).toBe(label(window, "settings.ha.status.update"));
  });

  test("inside Home Assistant the repair button leaves the frame for the repairs page", async () => {
    const { window } = await setup(status({ app_version: "2609.3.0", integration_version: "2609.4.0", updates: ["app"] }));
    window.eval("embeddedInHomeAssistant = () => true");

    const link = window.eval("settingsView()").querySelector(".update-hint a");

    expect(link.getAttribute("href")).toBe("/config/repairs");
    expect(link.getAttribute("target")).toBe("_top");
    expect(link.classList.contains("ghost")).toBe(false);
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

const NEWER = { state: "newer", latest: "2609.5.0", slug: "abc123_ranzenpost" };

describe("a newer app in the Home Assistant store", () => {
  test("the settings name the waiting version with one button to the app page", async () => {
    const { window } = await setup(status({ app_version: "2609.4.1", integration_version: "2609.4.1", app_update: NEWER }));
    window.eval("embeddedInHomeAssistant = () => true");
    const hint = window.eval("settingsView()").querySelector(".update-hint");

    expect(steps(hint)).toEqual(["update-app"]);
    expect(hint.querySelector(".update-title").textContent).toBe(label(window, "settings.update.store.title", { latest: "2609.5.0" }));
    expect(hint.querySelector(".update-text").textContent).toBe(label(window, "settings.update.store.text", { app: "2609.4.1", latest: "2609.5.0" }));
    const links = hint.querySelectorAll("button, a");
    expect(links.length).toBe(1);
    expect(links[0].getAttribute("href")).toBe("/hassio/addon/abc123_ranzenpost/info");
    expect(links[0].getAttribute("target")).toBe("_top");
  });

  test("an integration ahead as well still gives only one app notice", async () => {
    const { window } = await setup(status({ app_version: "2609.3.0", integration_version: "2609.4.0", updates: ["app"], app_update: NEWER }));
    const view = window.eval("settingsView()");

    expect(view.querySelectorAll(".update-hint").length).toBe(1);
    expect(steps(view.querySelector(".update-hint"))).toEqual(["update-app"]);
    expect(view.querySelectorAll(".update-hint a").length).toBe(1);
    expect(view.querySelector(".update-hint a").getAttribute("href")).toBe("https://my.home-assistant.io/redirect/supervisor_addon/?addon=abc123_ranzenpost");
  });

  test("an unreadable slug falls back to the updates page", async () => {
    const { window } = await setup(status({ app_update: { ...NEWER, slug: "../evil" } }));
    window.eval("embeddedInHomeAssistant = () => true");

    expect(window.eval("settingsView()").querySelector(".update-hint a").getAttribute("href")).toBe("/config/updates");
  });

  test("an unknown or current check shows nothing", async () => {
    for (const check of [{ state: "unknown", latest: "", slug: "" }, { state: "current", latest: "", slug: "x_ranzenpost" }, null]) {
      const { window } = await setup(status({ app_update: check }));
      expect(window.eval("settingsView()").querySelector(".update-hint")).toBeNull();
      expect(window.eval("appUpdateBanner()")).toBeNull();
    }
  });

  test("the overview carries one notice with one button", async () => {
    const { window } = await setup(status({ app_version: "2609.4.1", app_update: NEWER }));

    const banner = window.eval("appUpdateBanner()");

    expect(banner.classList.contains("update-notice")).toBe(true);
    expect(banner.getAttribute("role")).toBe("status");
    expect(banner.querySelector(".update-notice-text").textContent).toBe(label(window, "overview.update.store", { app: "2609.4.1", latest: "2609.5.0" }));
    expect(banner.querySelectorAll("button, a").length).toBe(1);
    expect(banner.querySelector("a").classList.contains("update-open-app")).toBe(true);
  });

  test("the overview points to the repair when the integration is ahead", async () => {
    const { window } = await setup(status({ app_version: "2609.3.0", integration_version: "2609.4.0", updates: ["app"] }));

    const banner = window.eval("appUpdateBanner()");

    expect(banner.querySelector(".update-notice-text").textContent).toBe(label(window, "overview.update.app", { app: "2609.3.0", integration: "2609.4.0" }));
    expect(banner.querySelectorAll("button, a").length).toBe(1);
    expect(banner.querySelector("a").classList.contains("update-open-repairs")).toBe(true);
  });

  test("the overview shows the notice next to the school notices", async () => {
    const { readFileSync } = await import("node:fs");
    const { dirname, join } = await import("node:path");
    const { fileURLToPath } = await import("node:url");
    const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "app", "overview.js"), "utf8");

    expect(source.match(/schoolIssueBanner\(\), appUpdateBanner\(\), mailNotice\(\)/g).length).toBe(2);
  });

  test("the problem report asks for the update first and keeps saving as the second choice", async () => {
    const { window } = await setup(status({ app_version: "2609.4.1", app_update: NEWER }));

    const help = window.eval("helpPageView()");

    const warning = help.firstElementChild;
    expect(warning.classList.contains("help-update-first")).toBe(true);
    expect(warning.querySelector(".update-text").textContent).toBe(label(window, "help.update.first"));
    const update = warning.querySelector("a");
    expect(update.classList.contains("ghost")).toBe(false);
    expect(update.classList.contains("update-open-app")).toBe(true);
    expect(help.querySelector(".help-save").classList.contains("ghost")).toBe(true);
    expect(help.querySelectorAll(".update-hint").length).toBe(1);
  });

  test("the problem report stays as before without a newer app", async () => {
    for (const check of [{ state: "current", latest: "", slug: "x_ranzenpost" }, { state: "unknown", latest: "", slug: "" }]) {
      const { window } = await setup(status({ app_update: check }));
      const help = window.eval("helpPageView()");
      expect(help.querySelector(".help-update-first")).toBeNull();
      expect(help.querySelector(".help-save").classList.contains("ghost")).toBe(false);
    }
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
      expect(bundle["settings.update.store.title"], language).toContain("{latest}");
      expect(bundle["settings.update.store.text"], language).toContain("{app}");
      expect(bundle["settings.update.store.text"], language).toContain("{latest}");
      expect(bundle["overview.update.store"], language).toContain("{latest}");
      expect(bundle["overview.update.app"], language).toContain("{integration}");
      for (const key of ["settings.update.app.open", "settings.update.store.open", "help.update.first"]) {
        expect(bundle[key], `${language}.${key}`).toBeTruthy();
      }
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
