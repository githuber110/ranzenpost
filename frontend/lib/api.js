export const API_ERROR = "ApiError";
export const ERROR_NETWORK = "network";
export const ERROR_AUTH_FAILED = "auth_failed";
export const ERROR_NOT_CONFIGURED = "not_configured";
export const ERROR_OUTAGE = "outage";
export const REASON_TWOFACTOR_SETUP = "twofactor_required_setup";
export const REASON_LOCKED = "locked";
export const REASON_SESSION_NOT_OPENED = "session_not_opened";
export const REASON_CODE_STEP_FAILED = "code_step_failed";
const LATE_LOGIN_REASONS = Object.freeze([REASON_CODE_STEP_FAILED, REASON_SESSION_NOT_OPENED]);
export const LOGIN_REASON_KEYS = Object.freeze({
  twofactor_required_setup: "api.login.twofactorSetup",
  unknown_account: "api.login.unknownAccount",
  default_password_blocked: "api.login.defaultPassword",
  locked: "api.login.locked",
  session_not_opened: "api.login.session",
  code_step_failed: "api.login.twofactor",
});
export const REQUEST_TIMEOUT_MS = 15000;
export const UPLOAD_TIMEOUT_MS = 120000;

export function loginReasonRank(reason) {
  return LATE_LOGIN_REASONS.indexOf(reason) + 1;
}

export function documentBase(href) {
  const url = new URL(href);
  url.search = "";
  url.hash = "";
  const path = url.pathname;
  const cut = path.lastIndexOf("/") + 1;
  const last = path.slice(cut);
  url.pathname = last.includes(".") ? path.slice(0, cut) : path.endsWith("/") ? path : `${path}/`;
  return url.toString();
}

export function checkResponse(response) {
  if (!response.ok) throw new Error("http " + response.status);
  return response;
}

export function apiError(code, body) {
  const failure = new Error(code || ERROR_NETWORK);
  failure.name = API_ERROR;
  failure.code = code || ERROR_NETWORK;
  failure.body = body || null;
  return failure;
}

export function errorCode(error) {
  return error && error.name === API_ERROR && error.code ? error.code : ERROR_NETWORK;
}

export function loginReasonOf(error) {
  const key = error && error.body && error.body.message_key;
  return Object.keys(LOGIN_REASON_KEYS).find((reason) => LOGIN_REASON_KEYS[reason] === key) || "";
}

export function isTimeoutError(error) {
  const name = error && error.name;
  return name === "TimeoutError" || name === "AbortError";
}

export function raiseCarriedError(data) {
  if (data && data.error) throw apiError(data.error, data);
  return data;
}

export function createApi({ fetch: send, base, t, abortSignal, formData }) {
  const apiBase = documentBase(base);

  function apiUrl(path) {
    return new URL(path, apiBase).toString();
  }

  function apiMessage(result, fallbackKey) {
    if (result && result.message_key) return t(result.message_key, result.message_vars);
    if (result && result.message) return result.message;
    return fallbackKey ? t(fallbackKey) : "";
  }

  function requestSignal(timeout) {
    const signals = abortSignal();
    return signals && signals.timeout ? signals.timeout(timeout) : undefined;
  }

  function getJson(path, signal) {
    return send(apiUrl(path), { signal: signal || requestSignal(REQUEST_TIMEOUT_MS) })
      .then(checkResponse)
      .then((response) => response.json())
      .then(raiseCarriedError);
  }

  function postJson(path, body, timeout) {
    return send(apiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: requestSignal(timeout || REQUEST_TIMEOUT_MS),
    })
      .then(checkResponse)
      .then((response) => response.json());
  }

  function postFormData(path, body, files) {
    const form = formData();
    form.append("data", JSON.stringify(body));
    for (const file of files) form.append("files", file);
    return send(apiUrl(path), { method: "POST", body: form, signal: requestSignal(UPLOAD_TIMEOUT_MS) })
      .then(checkResponse)
      .then((response) => response.json());
  }

  return { apiUrl, apiMessage, requestSignal, getJson, postJson, postFormData };
}

export function apiGlobals() {
  return Object.freeze({
    ERROR_NETWORK,
    ERROR_AUTH_FAILED,
    ERROR_NOT_CONFIGURED,
    ERROR_OUTAGE,
    REASON_TWOFACTOR_SETUP,
    REASON_LOCKED,
    REASON_SESSION_NOT_OPENED,
    REASON_CODE_STEP_FAILED,
    LOGIN_REASON_KEYS,
    UPLOAD_TIMEOUT_MS,
    apiError,
    errorCode,
    loginReasonOf,
    loginReasonRank,
    isTimeoutError,
    createApi,
  });
}
