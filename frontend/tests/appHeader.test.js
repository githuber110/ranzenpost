import { describe, expect, test } from "vitest";
import { createApi } from "../lib/api.js";
import { loadApp } from "./loadApp.js";

function recordingApi() {
  const seen = [];
  const api = createApi({
    fetch: (url, options) => {
      seen.push({ url, options });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    },
    base: "http://app.example/",
    t: (key) => key,
    abortSignal: () => undefined,
    formData: () => new FormData(),
  });
  return { api, seen };
}

describe("every request of the app names itself to the server", () => {
  test("reads, json writes, uploads and plain requests carry the app header", async () => {
    const { api, seen } = recordingApi();
    await api.getJson("api/me");
    await api.postJson("api/config", { a: 1 });
    await api.postFormData("api/files/upload", { path: "own" }, [new Blob(["x"])]);
    await api.requestJson("api/marks/m1", { method: "DELETE" }, "x");
    await api.postJsonSafe("api/notify-test", {}, "x");
    await api.getFile("api/files/file");
    expect(seen.map((entry) => entry.options.headers["X-Ranzenpost-App"])).toEqual(["1", "1", "1", "1", "1", "1"]);
    expect(seen[1].options.headers["Content-Type"]).toBe("application/json");
  });

  test("the setup wizard sends the header too", async () => {
    const { window, document } = loadApp();
    const seen = [];
    window.fetch = (requested, options) => {
      seen.push({ url: String(requested), options });
      return Promise.resolve({ ok: true, status: 200, headers: { get: () => "application/json" }, json: () => Promise.resolve({ step: "url" }) });
    };
    window.renderWizard(document.getElementById("app"), () => {});
    await new Promise((resolve) => setTimeout(resolve, 0));
    const wizard = seen.filter((entry) => entry.url.includes("api/wizard"));
    expect(wizard.length).toBeGreaterThan(0);
    for (const entry of wizard) expect(entry.options.headers["X-Ranzenpost-App"]).toBe("1");
  });
});
