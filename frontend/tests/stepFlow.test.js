import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function jsonResponse(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

function makeFlow(window, extra) {
  const build = window.eval(`
    (function (extra) {
      const draft = { name: "", extra: "", want: false };
      const spec = {
        text: (name, vars) => {
          if (name === "progressTotal") return "step " + vars.n + "/" + vars.total;
          if (name === "progress") return "step " + vars.n;
          if (name === "pending") return "maybe more";
          if (name === "failed") return "boom";
          return name;
        },
        steps: () => (draft.want ? ["one", "two", "three"] : ["one", "three"]),
        pending: (id) => id === "one",
        step: (id) => {
          if (id === "one") {
            const box = document.createElement("input");
            box.type = "checkbox";
            box.className = "want";
            box.checked = draft.want;
            box.addEventListener("change", () => { draft.want = box.checked; flow.render(); });
            return { question: "one", body: [box], nextLabel: "next" };
          }
          if (id === "two") {
            const field = document.createElement("input");
            field.className = "name";
            field.value = draft.name;
            field.addEventListener("input", () => { draft.name = field.value; flow.sync(); });
            return {
              question: "two",
              body: [field],
              nextLabel: "next",
              block: () => (draft.name ? "" : "need a name"),
              blockFocus: () => field,
            };
          }
          const secret = document.createElement("input");
          secret.type = "password";
          secret.className = "secret";
          return {
            question: "three",
            body: [secret],
            nextLabel: "send",
            busyLabel: "sending",
            onNext: () => window.__flowSend(secret.value),
          };
        },
      };
      Object.assign(spec, extra || {});
      const flow = window.StepFlow.create(spec);
      document.getElementById("app").replaceChildren(flow.node);
      flow.start("one");
      window.__flowDraft = draft;
      return flow;
    })
  `);
  return build(extra || null);
}

function ui(window) {
  const node = window.document.querySelector(".sw");
  return {
    node,
    step: () => node.getAttribute("data-step"),
    status: () => node.querySelector(".sw-status").textContent,
    button: () => node.querySelector(".sw-next"),
    dots: () => Array.from(node.querySelectorAll(".sw-dot")),
    body: () => node.querySelector(".sw-body"),
    progress: () => node.querySelector(".sw-progress"),
  };
}

describe("[P180] step scaffold: conditional steps", () => {
  test("a conditional step appears and disappears with the answer that decides it", () => {
    const { window } = loadApp();
    const flow = makeFlow(window);
    const view = ui(window);
    expect(flow.path()).toEqual(["one", "three"]);
    view.body().querySelector(".want").click();
    expect(flow.path()).toEqual(["one", "two", "three"]);
    view.body().querySelector(".want").click();
    expect(flow.path()).toEqual(["one", "three"]);
  });

  test("an uncertain step shows exactly one dashed dot and no total in the spoken label", () => {
    const { window } = loadApp();
    makeFlow(window);
    const view = ui(window);
    expect(view.dots().filter((dot) => dot.classList.contains("maybe")).length).toBe(1);
    expect(view.progress().getAttribute("aria-valuetext")).toBe("step 1 maybe more");
    expect(view.progress().hasAttribute("aria-valuemax")).toBe(false);
  });

  test("a certain step speaks the total and drops the dashed dot", () => {
    const { window } = loadApp();
    const flow = makeFlow(window);
    const view = ui(window);
    flow.go("three");
    expect(view.dots().filter((dot) => dot.classList.contains("maybe")).length).toBe(0);
    expect(view.progress().getAttribute("aria-valuetext")).toBe("step 2/2");
  });

  test("the cursor falls back into the path when its step disappears", () => {
    const { window } = loadApp();
    const flow = makeFlow(window);
    const view = ui(window);
    view.body().querySelector(".want").click();
    flow.go("two");
    expect(view.step()).toBe("two");
    window.eval("window.__flowDraft.want = false");
    flow.render();
    expect(view.step()).toBe("one");
  });
});

describe("[P180] step scaffold: nothing is lost going back", () => {
  test("back and forward keep what was typed into caller state", () => {
    const { window } = loadApp();
    const flow = makeFlow(window);
    const view = ui(window);
    view.body().querySelector(".want").click();
    flow.go("two");
    const field = view.body().querySelector(".name");
    field.value = "Mia";
    field.dispatchEvent(new window.Event("input"));
    flow.back();
    expect(view.step()).toBe("one");
    flow.next();
    expect(view.step()).toBe("two");
    expect(view.body().querySelector(".name").value).toBe("Mia");
  });

  test("back on the first step never wraps around to the end", () => {
    const { window } = loadApp();
    const flow = makeFlow(window);
    flow.back();
    expect(ui(window).step()).toBe("one");
  });
});

describe("[P180] step scaffold: the forward lock says why", () => {
  test("an incomplete mandatory field keeps the button on the step and explains itself", () => {
    const { window } = loadApp();
    const flow = makeFlow(window);
    const view = ui(window);
    view.body().querySelector(".want").click();
    flow.go("two");
    expect(view.button().getAttribute("aria-disabled")).toBe("true");
    expect(view.status()).toBe("need a name");
    view.button().click();
    expect(view.step()).toBe("two");
    const field = view.body().querySelector(".name");
    field.value = "Mia";
    field.dispatchEvent(new window.Event("input"));
    expect(view.status()).toBe("");
    expect(view.button().getAttribute("aria-disabled")).toBe("false");
    view.button().click();
    expect(view.step()).toBe("three");
  });

  test("the button is never disabled, so it can always take the tap that asks why", () => {
    const { window } = loadApp();
    const flow = makeFlow(window);
    const view = ui(window);
    view.body().querySelector(".want").click();
    flow.go("two");
    expect(view.button().disabled).toBe(false);
  });
});

describe("[P180] step scaffold: a network step keeps the step and its input", () => {
  test("a rejected request shows the reason and leaves the typed value untouched", async () => {
    const { window } = loadApp();
    const flow = makeFlow(window);
    const view = ui(window);
    window.eval("window.__flowSend = () => Promise.reject(new Error('no'))");
    flow.go("three");
    const secret = view.body().querySelector(".secret");
    secret.value = "123456";
    view.button().click();
    await flush();
    expect(view.step()).toBe("three");
    expect(view.status()).toBe("boom");
    expect(view.body().querySelector(".secret")).toBe(secret);
    expect(secret.value).toBe("123456");
  });

  test("a request that answers with a reason shows that reason instead of the generic one", async () => {
    const { window } = loadApp();
    const flow = makeFlow(window);
    const view = ui(window);
    window.eval("window.__flowSend = () => Promise.resolve('rejected by the school')");
    flow.go("three");
    view.button().click();
    await flush();
    expect(view.status()).toBe("rejected by the school");
  });

  test("while the request runs the button shows the waiting label", () => {
    const { window } = loadApp();
    const flow = makeFlow(window);
    const view = ui(window);
    window.eval("window.__flowSend = () => new Promise(() => {})");
    flow.go("three");
    view.button().click();
    expect(view.button().textContent).toBe("sending");
    expect(view.button().getAttribute("aria-busy")).toBe("true");
  });
});

describe("[P180] setup wizard on the shared scaffold: password and 2FA code are never carried along", () => {
  function setupWizard(window, document, states) {
    const posts = [];
    window.fetch = (path, opts) => {
      const url = String(path);
      if (opts && opts.method === "POST") posts.push({ url, body: opts.body ? JSON.parse(opts.body) : null });
      if (url.includes("api/wizard/back")) return jsonResponse(states.back);
      if (url.includes("api/wizard/login")) return jsonResponse(states.login);
      if (url.includes("api/wizard/url")) return jsonResponse(states.url);
      if (url.includes("api/config")) return jsonResponse({});
      if (url.includes("api/wizard")) return jsonResponse(states.first);
      return Promise.reject(new Error("unexpected fetch " + url));
    };
    return { posts, start: () => window.renderWizard(document.getElementById("app"), () => {}) };
  }

  test("going back to the login step hands back an empty password field, the username survives", async () => {
    const { window, document } = loadApp();
    const first = { step: "login", school_url: "schule.example", has_2fa: false };
    const wizard = setupWizard(window, document, { first, url: first, login: first, back: first });
    await flush();
    wizard.start();
    await flush();
    await flush();

    const view = ui(window);
    expect(view.step()).toBe("login");
    const user = view.body().querySelector('input[name="username"]');
    const pass = view.body().querySelector('input[name="password"]');
    user.value = "erika.muster";
    user.dispatchEvent(new window.Event("input"));
    pass.value = "hunter2";
    pass.dispatchEvent(new window.Event("input"));

    window.document.querySelector(".sw-back").click();
    await flush();
    await flush();

    const back = ui(window);
    expect(back.step()).toBe("login");
    expect(back.body().querySelector('input[name="username"]').value).toBe("erika.muster");
    expect(back.body().querySelector('input[name="password"]').value).toBe("");
  });

  test("the wizard writes nothing to localStorage while credentials are on screen", async () => {
    const { window, document } = loadApp();
    const first = { step: "login", has_2fa: false };
    const wizard = setupWizard(window, document, { first, url: first, login: first, back: first });
    await flush();
    wizard.start();
    await flush();
    await flush();
    const before = window.localStorage.length;
    const pass = ui(window).body().querySelector('input[name="password"]');
    pass.value = "hunter2";
    pass.dispatchEvent(new window.Event("input"));
    window.document.querySelector(".sw-back").click();
    await flush();
    expect(window.localStorage.length).toBe(before);
    expect(window.localStorage.getItem("password")).toBeNull();
  });

  test("a failing login keeps the typed credentials on screen instead of throwing the user out", async () => {
    const { window, document } = loadApp();
    const first = { step: "login", has_2fa: false };
    window.fetch = (path, opts) => {
      const url = String(path);
      if (url.includes("api/wizard/login")) return Promise.reject(new Error("offline"));
      if (url.includes("api/wizard")) return jsonResponse(first);
      return Promise.reject(new Error("unexpected fetch " + url));
    };
    await flush();
    window.renderWizard(document.getElementById("app"), () => {});
    await flush();
    await flush();

    const view = ui(window);
    const user = view.body().querySelector('input[name="username"]');
    const pass = view.body().querySelector('input[name="password"]');
    user.value = "erika.muster";
    user.dispatchEvent(new window.Event("input"));
    pass.value = "hunter2";
    pass.dispatchEvent(new window.Event("input"));
    view.button().click();
    await flush();
    await flush();

    expect(ui(window).step()).toBe("login");
    expect(ui(window).body().querySelector('input[name="password"]').value).toBe("hunter2");
    expect(ui(window).status()).toBe(window.t("wizard.error.service.text"));
  });

  test("every setup step keeps the restart button reachable", async () => {
    const { window, document } = loadApp();
    for (const step of ["url", "login", "connect"]) {
      const first = { step, has_2fa: true };
      window.fetch = (path) => {
        if (String(path).includes("api/wizard")) return jsonResponse(first);
        return Promise.reject(new Error("unexpected"));
      };
      await flush();
      document.getElementById("app").replaceChildren();
      window.renderWizard(document.getElementById("app"), () => {});
      await flush();
      await flush();
      const reset = window.document.querySelector(".sw-head-actions .wz-nav.reset");
      expect(reset, step).not.toBeNull();
      expect(reset.textContent).toBe("Neu starten");
    }
  });
});
