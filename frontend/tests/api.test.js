import { describe, expect, test } from "vitest";
import {
  API_ERROR,
  ERROR_AUTH_FAILED,
  ERROR_NETWORK,
  LOGIN_REASON_KEYS,
  REQUEST_TIMEOUT_MS,
  UPLOAD_TIMEOUT_MS,
  apiError,
  apiGlobals,
  checkResponse,
  createApi,
  documentBase,
  errorCode,
  isTimeoutError,
  loginReasonOf,
  raiseCarriedError,
} from "../lib/api.js";

const INGRESS = "http://localhost/api/hassio_ingress/TOKEN123/";

function answer(body, ok = true, status = 200) {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) });
}

function fakeForm() {
  const parts = [];
  return { parts, append: (name, value) => parts.push([name, value]) };
}

function setup({ reply = () => answer({}), signals = { timeout: (ms) => ({ ms }) }, base = INGRESS } = {}) {
  const calls = [];
  const forms = [];
  const api = createApi({
    fetch: (url, options) => {
      calls.push({ url, options });
      return reply(url, options);
    },
    base,
    t: (key, vars) => (vars ? `${key}:${JSON.stringify(vars)}` : `t:${key}`),
    abortSignal: () => signals,
    formData: () => {
      const form = fakeForm();
      forms.push(form);
      return form;
    },
  });
  return { api, calls, forms };
}

describe("the document base keeps the ingress path", () => {
  test("a path without a trailing slash counts as a directory", () => {
    expect(documentBase("http://localhost/api/hassio_ingress/TOKEN123")).toBe(INGRESS);
  });

  test("a file name, a query and a fragment are dropped", () => {
    expect(documentBase("http://localhost/api/hassio_ingress/TOKEN123/index.html?tab=a#top")).toBe(INGRESS);
    expect(documentBase(`${INGRESS}?tab=letters#top`)).toBe(INGRESS);
  });
});

describe("request helpers run without a browser", () => {
  test("apiUrl resolves below the base computed once at creation", () => {
    const { api } = setup({ base: "http://localhost/api/hassio_ingress/TOKEN123/index.html" });
    expect(api.apiUrl("api/children")).toBe(`${INGRESS}api/children`);
  });

  test("getJson sends through the injected fetch with the request timeout", async () => {
    const { api, calls } = setup({ reply: () => answer({ one: 1 }) });
    await expect(api.getJson("api/me")).resolves.toEqual({ one: 1 });
    expect(calls).toEqual([{ url: `${INGRESS}api/me`, options: { signal: { ms: REQUEST_TIMEOUT_MS } } }]);
  });

  test("getJson keeps a signal the caller hands in", async () => {
    const { api, calls } = setup();
    const signal = { own: true };
    await api.getJson("api/me", signal);
    expect(calls[0].options.signal).toBe(signal);
  });

  test("getJson turns a carried error into an ApiError and a failed status into an http error", async () => {
    const carried = setup({ reply: () => answer({ error: ERROR_AUTH_FAILED, message_key: "api.login.locked" }) });
    const failure = await carried.api.getJson("api/me").catch((error) => error);
    expect([failure.name, failure.code, loginReasonOf(failure)]).toEqual([API_ERROR, ERROR_AUTH_FAILED, "locked"]);
    const refused = setup({ reply: () => answer({}, false, 503) });
    await expect(refused.api.getJson("api/me")).rejects.toThrow("http 503");
  });

  test("postJson sends the body as JSON and passes a carried error through", async () => {
    const { api, calls } = setup({ reply: () => answer({ error: "outage" }) });
    await expect(api.postJson("api/config", { a: 1 })).resolves.toEqual({ error: "outage" });
    expect(calls[0]).toEqual({
      url: `${INGRESS}api/config`,
      options: {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ a: 1 }),
        signal: { ms: REQUEST_TIMEOUT_MS },
      },
    });
    await api.postJson("api/config", {}, 30000);
    expect(calls[1].options.signal).toEqual({ ms: 30000 });
  });

  test("postFormData builds the form with the injected factory and the upload timeout", async () => {
    const { api, calls, forms } = setup({ reply: () => answer({ ok: true }) });
    await expect(api.postFormData("api/absences", { b: 2 }, ["first", "second"])).resolves.toEqual({ ok: true });
    expect(forms[0].parts).toEqual([
      ["data", JSON.stringify({ b: 2 })],
      ["files", "first"],
      ["files", "second"],
    ]);
    expect(calls[0].options).toEqual({ method: "POST", body: forms[0], signal: { ms: UPLOAD_TIMEOUT_MS } });
  });

  test("without AbortSignal.timeout a request goes out without a signal", async () => {
    const { api, calls } = setup({ signals: null });
    expect(api.requestSignal(5)).toBeUndefined();
    await api.getJson("api/me");
    expect(calls[0].options).toEqual({ signal: undefined });
    expect(setup({ signals: {} }).api.requestSignal(5)).toBeUndefined();
  });

  test("apiMessage prefers the translated key, then the plain message, then the fallback", () => {
    const { api } = setup();
    expect(api.apiMessage({ message_key: "a.b", message_vars: { n: 1 } }, "x")).toBe('a.b:{"n":1}');
    expect(api.apiMessage({ message: "plain" }, "x")).toBe("plain");
    expect(api.apiMessage({}, "x")).toBe("t:x");
    expect(api.apiMessage(null, "")).toBe("");
  });
});

describe("error helpers", () => {
  test("an ApiError carries code and body, anything else counts as a network failure", () => {
    const failure = apiError("", undefined);
    expect([failure.name, failure.code, failure.body]).toEqual([API_ERROR, ERROR_NETWORK, null]);
    expect(errorCode(apiError(ERROR_AUTH_FAILED, {}))).toBe(ERROR_AUTH_FAILED);
    expect(errorCode(new Error(ERROR_AUTH_FAILED))).toBe(ERROR_NETWORK);
    expect(errorCode(null)).toBe(ERROR_NETWORK);
  });

  test("a login reason is read from the message key, an unknown key gives none", () => {
    expect(loginReasonOf(apiError(ERROR_AUTH_FAILED, { message_key: "api.login.session" }))).toBe("session_not_opened");
    expect(loginReasonOf(apiError(ERROR_AUTH_FAILED, { message_key: "api.other" }))).toBe("");
    expect(loginReasonOf(null)).toBe("");
  });

  test("timeouts and aborts count as timeouts", () => {
    expect(isTimeoutError({ name: "TimeoutError" })).toBe(true);
    expect(isTimeoutError({ name: "AbortError" })).toBe(true);
    expect(isTimeoutError(new Error("x"))).toBe(false);
    expect(isTimeoutError(null)).toBe(false);
  });

  test("checkResponse and raiseCarriedError pass good answers through", () => {
    const response = { ok: true };
    expect(checkResponse(response)).toBe(response);
    expect(() => checkResponse({ ok: false, status: 404 })).toThrow("http 404");
    expect(raiseCarriedError({ a: 1 })).toEqual({ a: 1 });
    expect(raiseCarriedError(null)).toBe(null);
    expect(() => raiseCarriedError({ error: "outage" })).toThrow("outage");
  });

  test("the globals hand app.js a frozen set that includes the factory", () => {
    const globals = apiGlobals();
    expect(Object.isFrozen(globals)).toBe(true);
    expect(globals.createApi).toBe(createApi);
    expect(globals.apiError).toBe(apiError);
  });

  test("the login reason table cannot be changed by a caller", () => {
    expect(Object.isFrozen(LOGIN_REASON_KEYS)).toBe(true);
    expect(apiGlobals().LOGIN_REASON_KEYS).toBe(LOGIN_REASON_KEYS);
  });
});
