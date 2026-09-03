import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

describe("[P150] request base URL survives an ingress path without a trailing slash", () => {
  test("apiUrl anchors relative paths under the full document path, keeping the ingress token", () => {
    const { window } = loadApp({ url: "http://localhost/api/hassio_ingress/TOKEN123" });
    expect(window.document.baseURI.endsWith("/")).toBe(false);
    const resolved = window.eval('apiUrl("api/children")');
    expect(resolved).toBe("http://localhost/api/hassio_ingress/TOKEN123/api/children");
  });

  test("apiUrl is unaffected when the base already ends with a slash", () => {
    const { window } = loadApp({ url: "http://localhost/api/hassio_ingress/TOKEN123/" });
    const resolved = window.eval('apiUrl("api/children")');
    expect(resolved).toBe("http://localhost/api/hassio_ingress/TOKEN123/api/children");
  });

  test("apiUrl drops a document filename instead of treating it as a directory", () => {
    const { window } = loadApp({ url: "http://localhost/api/hassio_ingress/TOKEN123/index.html" });
    const resolved = window.eval('apiUrl("api/children")');
    expect(resolved).toBe("http://localhost/api/hassio_ingress/TOKEN123/api/children");
  });

  test("apiUrl ignores query and fragment on the document url", () => {
    const { window } = loadApp({ url: "http://localhost/api/hassio_ingress/TOKEN123/?tab=letters#top" });
    const resolved = window.eval('apiUrl("api/children")');
    expect(resolved).toBe("http://localhost/api/hassio_ingress/TOKEN123/api/children");
  });

  test("getJson resolves against the same anchored base, not document root", async () => {
    const { window } = loadApp({ url: "http://localhost/api/hassio_ingress/TOKEN123" });
    let requestedUrl = null;
    window.fetch = (url) => {
      requestedUrl = url;
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    };
    await window.eval('getJson("api/children")');
    expect(requestedUrl).toBe("http://localhost/api/hassio_ingress/TOKEN123/api/children");
  });
});

describe("[P150] the setup wizard resolves its own requests, independently of app.js", () => {
  const runWizard = async (url) => {
    const { window } = loadApp({ url });
    const requested = [];
    window.fetch = (target) => {
      requested.push(String(target));
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ step: "url" }) });
    };
    window.renderWizard(window.document.getElementById("app"), () => {});
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    return { window, requested };
  };

  test("keeps the ingress token when the document url has no trailing slash", async () => {
    const { requested } = await runWizard("http://localhost/api/hassio_ingress/TOKEN123");
    expect(requested).toContain("http://localhost/api/hassio_ingress/TOKEN123/api/wizard");
  });

  test("drops a document filename instead of nesting below it", async () => {
    const { requested } = await runWizard("http://localhost/api/hassio_ingress/TOKEN123/index.html");
    expect(requested).toContain("http://localhost/api/hassio_ingress/TOKEN123/api/wizard");
  });

  test("does not fall back to a bare relative path", async () => {
    const { requested } = await runWizard("http://localhost/api/hassio_ingress/TOKEN123");
    expect(requested.length).toBeGreaterThan(0);
    for (const target of requested) expect(target.startsWith("http")).toBe(true);
  });

  test("resolves exactly like the main app, so the two cannot drift apart", async () => {
    const { window, requested } = await runWizard("http://localhost/api/hassio_ingress/TOKEN123/index.html");
    const wizardTarget = requested.find((target) => target.endsWith("api/wizard"));
    expect(wizardTarget).toBe(window.eval('apiUrl("api/wizard")'));
  });
});
