import { describe, expect, test } from "vitest";
import { apiGlobals } from "../lib/api.js";
import { domGlobals } from "../lib/dom.js";
import { formatGlobals } from "../lib/format.js";
import { i18nGlobals } from "../lib/i18nGlobals.js";
import { SELECTION_KEYS as MODULE_SELECTION_KEYS, selectionGlobals } from "../lib/selection.js";
import { SHEET_KEYS, shellGlobals } from "../lib/shell.js";
import { storeGlobals } from "../lib/store.js";
import { loadApp } from "./loadApp.js";
import { readShipped, scriptNames } from "./shippedSources.js";

const BROWSER_GLOBAL =
  /\b(window|document|navigator|globalThis|location|localStorage|sessionStorage|FormData|AbortSignal|AbortController|Headers|Request|Response|XMLHttpRequest|Blob|File|setTimeout|clearTimeout|setInterval|clearInterval|requestAnimationFrame|cancelAnimationFrame|requestIdleCallback|queueMicrotask)\b|\b(self)\.|\b(fetch)\b(?!\s*:)/;
const AMBIENT_CLOCK = /\bDate\.now\s*\(|\bnew\s+Date\s*\(\s*\)|\bnew\s+Date\b(?!\s*\()/;
const GLOBALS_MODULE = "lib/globals.js";
const APP_ONLY_GLOBALS = ["createLanguageLoader"];
const WINDOW_LANGUAGE_FUNCTIONS = ["resolveLanguage", "applyLanguageChoice"];
const WINDOW_API_FUNCTIONS = ["apiMessage"];
const SCRIPT_API_FUNCTIONS = [
  "apiUrl",
  "requestSignal",
  "getJson",
  "postJson",
  "postFormData",
  "getFile",
  "requestJson",
  "postJsonSafe",
];
const FORMER_WINDOW_API_FUNCTIONS = ["apiUrl", "apiError", "errorCode", "loginReasonOf", "isTimeoutError", "requestSignal"];
const MODULE_ONLY_API_NAMES = ["documentBase", "API_BASE", "checkResponse", "raiseCarriedError", "API_ERROR"];
const DOM_KIT_FUNCTIONS = ["el", "iservText", "icon", "externalIcon"];
const TOAST_FUNCTIONS = ["toast", "toastNode"];
const SHELL_KEYS = [...SHEET_KEYS, "toast"];
const SELECTION_KEYS = ["lettersSelectMode", "lettersSelected", "pinboardSelectMode", "pinboardSelected"];
const STORE_KEYS = [...SHELL_KEYS, ...SELECTION_KEYS];
const ARRAY_MUTATORS = "push|pop|shift|unshift|splice|sort|reverse|fill|copyWithin";
const SHEET_FUNCTIONS = [
  "openSheet",
  "discardSheet",
  "closeSheet",
  "isSheetFormDirty",
  "sheetState",
  "sheet",
  "openNestedSheet",
  "askConfirmation",
  "placeSheet",
  "dropSheet",
  "resetSheetForm",
];
const FORMER_WINDOW_FORMAT_FUNCTIONS = [
  "showDate",
  "formatEpoch",
  "isoWeek",
  "parseAnyDate",
  "parseIsoDay",
  "timeMinutes",
  "formatWeekdayDate",
  "showDateTime",
  "showTimestamp",
  "formatIsoMoment",
  "clockText",
  "clockOf",
  "weekdayLabel",
  "isoLabel",
  "dateLabel",
  "relativeSince",
  "minutesUntilLabel",
];
const MODULE_ONLY_FORMAT_NAMES = [
  "pad2",
  "parseGermanDate",
  "parseGermanDateTime",
  "parseIsoDateTime",
  "formatDate",
  "MS_PER_WEEK",
  "ISO_DAY_PATTERN",
  "RELATIVE_STEPS",
];

function libModules() {
  return scriptNames().filter((name) => name.startsWith("lib/"));
}

function browserGlobalsIn(source) {
  return source
    .split("\n")
    .map((line, index) => ({ line: index + 1, match: BROWSER_GLOBAL.exec(line) }))
    .filter((hit) => hit.match)
    .map((hit) => `${hit.line}: ${hit.match[1] || hit.match[2] || hit.match[3]}`);
}

function ambientClockIn(source) {
  return source
    .split("\n")
    .map((line, index) => ({ line: index + 1, match: AMBIENT_CLOCK.exec(line) }))
    .filter((hit) => hit.match)
    .map((hit) => hit.line);
}

function skipString(source, start) {
  const quote = source[start];
  let index = start + 1;
  while (index < source.length && source[index] !== quote) index += source[index] === "\\" ? 2 : 1;
  return index;
}

function topLevelAwaits(source) {
  const lines = [];
  let depth = 0;
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (char === '"' || char === "'" || char === "`") {
      index = skipString(source, index);
    } else if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
    } else if (
      depth === 0 &&
      source.startsWith("await", index) &&
      !/[\w$]/.test(source[index - 1] || "") &&
      !/[\w$]/.test(source[index + 5] || "")
    ) {
      lines.push(source.slice(0, index).split("\n").length);
    }
  }
  return lines;
}

function destructuredNames(source, keyword, from = "window\\.RanzenpostI18n") {
  const pattern = new RegExp(`\\b${keyword}\\s*\\{([^}]*)\\}\\s*=\\s*${from};`, "g");
  return [...source.matchAll(pattern)].flatMap((match) =>
    match[1].split(",").map((name) => name.trim()).filter(Boolean)
  );
}

describe("the lib folder stays free of the browser", () => {
  test("the lib folder holds the translation core, the language loader and the globals bridge", () => {
    expect(libModules()).toEqual(
      expect.arrayContaining([
        "lib/i18n.js",
        "lib/language.js",
        "lib/i18nGlobals.js",
        "lib/api.js",
        "lib/format.js",
        "lib/dom.js",
        "lib/shell.js",
        "lib/store.js",
        "lib/selection.js",
        GLOBALS_MODULE,
      ])
    );
  });

  test("the translation core imports nothing, so the loader depends on the core and never the other way", () => {
    expect(readShipped("lib/i18n.js")).not.toMatch(/^\s*import\b/m);
    expect(readShipped("lib/language.js")).toMatch(/from "\.\/i18n\.js";/);
  });

  test("only the globals bridge touches window, document, navigator, storage, location, fetch or the request globals", () => {
    const offenders = libModules()
      .filter((name) => name !== GLOBALS_MODULE)
      .flatMap((name) => browserGlobalsIn(readShipped(name)).map((hit) => `${name}:${hit}`));
    expect(offenders).toEqual([]);
  });

  test("the boundary check sees every browser global", () => {
    expect(browserGlobalsIn("const a = 1;\nconst b = window.x;")).toEqual(["2: window"]);
    expect(browserGlobalsIn("document.title = 1;")).toEqual(["1: document"]);
    expect(browserGlobalsIn("const c = navigator.language;")).toEqual(["1: navigator"]);
    expect(browserGlobalsIn("globalThis.x = 1;")).toEqual(["1: globalThis"]);
    expect(browserGlobalsIn("const a = location.href;")).toEqual(["1: location"]);
    expect(browserGlobalsIn("localStorage.getItem(a);")).toEqual(["1: localStorage"]);
    expect(browserGlobalsIn("sessionStorage.clear();")).toEqual(["1: sessionStorage"]);
    expect(browserGlobalsIn("const a = self.origin;")).toEqual(["1: self"]);
    expect(browserGlobalsIn("const a = fetch (url);")).toEqual(["1: fetch"]);
    expect(browserGlobalsIn("const documentTitle = windowSize;")).toEqual([]);
    expect(browserGlobalsIn("const selfish = prefetch(itself);")).toEqual([]);
  });

  test("the boundary check sees the request globals a module could use without injection", () => {
    expect(browserGlobalsIn("const form = new FormData();")).toEqual(["1: FormData"]);
    expect(browserGlobalsIn("const a = AbortSignal.timeout(5);")).toEqual(["1: AbortSignal"]);
    expect(browserGlobalsIn("const a = new AbortController();")).toEqual(["1: AbortController"]);
    expect(browserGlobalsIn("const a = new Headers();")).toEqual(["1: Headers"]);
    expect(browserGlobalsIn("const a = new Request(url);")).toEqual(["1: Request"]);
    expect(browserGlobalsIn("const a = Response.json({});")).toEqual(["1: Response"]);
    expect(browserGlobalsIn("const a = new XMLHttpRequest();")).toEqual(["1: XMLHttpRequest"]);
    expect(browserGlobalsIn("const a = new Blob([]);")).toEqual(["1: Blob"]);
    expect(browserGlobalsIn("const a = new File([], name);")).toEqual(["1: File"]);
    expect(browserGlobalsIn("const send = fetch;")).toEqual(["1: fetch"]);
    expect(browserGlobalsIn("return fetch\n(url);")).toEqual(["1: fetch"]);
    expect(browserGlobalsIn("const { fetch } = dependencies;")).toEqual(["1: fetch"]);
  });

  test("the boundary check sees the ambient timers a module could schedule with instead of injected ones", () => {
    expect(browserGlobalsIn("const id = setTimeout(run, 5);")).toEqual(["1: setTimeout"]);
    expect(browserGlobalsIn("clearTimeout(id);")).toEqual(["1: clearTimeout"]);
    expect(browserGlobalsIn("const id = setInterval(run, 5);")).toEqual(["1: setInterval"]);
    expect(browserGlobalsIn("clearInterval(id);")).toEqual(["1: clearInterval"]);
    expect(browserGlobalsIn("requestAnimationFrame(run);")).toEqual(["1: requestAnimationFrame"]);
    expect(browserGlobalsIn("cancelAnimationFrame(id);")).toEqual(["1: cancelAnimationFrame"]);
    expect(browserGlobalsIn("requestIdleCallback(run);")).toEqual(["1: requestIdleCallback"]);
    expect(browserGlobalsIn("queueMicrotask(run);")).toEqual(["1: queueMicrotask"]);
    expect(browserGlobalsIn("timer = timers.set(run, 5);\ntimers.clear(timer);")).toEqual([]);
    expect(browserGlobalsIn("const later = scheduleTimeout;")).toEqual([]);
  });

  test("the boundary check leaves injected names and look-alikes alone", () => {
    expect(browserGlobalsIn("export function createApi({ fetch: send, abortSignal, formData }) {")).toEqual([]);
    expect(browserGlobalsIn("const api = createApi({ fetch : (url) => send(url) });")).toEqual([]);
    expect(browserGlobalsIn("const form = formData();")).toEqual([]);
    expect(browserGlobalsIn("const signal = abortSignal();")).toEqual([]);
    expect(browserGlobalsIn('const a = { headers: { "Content-Type": "x" } };')).toEqual([]);
    expect(browserGlobalsIn("const a = response.json();")).toEqual([]);
    expect(browserGlobalsIn("const a = requestSignal(5);")).toEqual([]);
    expect(browserGlobalsIn("const a = new FileReader();")).toEqual([]);
    expect(browserGlobalsIn("const a = files.map(Blobby);")).toEqual([]);
    expect(browserGlobalsIn("const a = fetchBundle(language);")).toEqual([]);
    expect(browserGlobalsIn("const a = prefetched;")).toEqual([]);
  });

  test("no lib module reads the clock itself, so a replaced page clock still reaches every helper", () => {
    const offenders = libModules().flatMap((name) => ambientClockIn(readShipped(name)).map((line) => `${name}:${line}`));
    expect(offenders).toEqual([]);
  });

  test("the clock check sees the ambient clock and leaves dates built from a value alone", () => {
    expect(ambientClockIn("const a = 1;\nconst b = Date.now();")).toEqual([2]);
    expect(ambientClockIn("const a = Date.now ();")).toEqual([1]);
    expect(ambientClockIn("const a = new Date();")).toEqual([1]);
    expect(ambientClockIn("const a = new Date( );")).toEqual([1]);
    expect(ambientClockIn("const a = new Date;")).toEqual([1]);
    expect(ambientClockIn("const a = new Date(value);")).toEqual([]);
    expect(ambientClockIn("const a = new Date(year, 0, 4);")).toEqual([]);
    expect(ambientClockIn("const a = new Date (n * 1000);")).toEqual([]);
    expect(ambientClockIn("const a = new Intl.DateTimeFormat(language);")).toEqual([]);
    expect(ambientClockIn("const a = nowMs();\nconst b = now();")).toEqual([]);
    expect(ambientClockIn("const a = myDate.now();\nconst b = Date.nowish();")).toEqual([]);
  });

  test("no lib module waits at its top level, so app.js never runs before the globals exist", () => {
    const offenders = libModules().flatMap((name) => topLevelAwaits(readShipped(name)).map((line) => `${name}:${line}`));
    expect(offenders).toEqual([]);
  });

  test("the top level await check sees an await outside every function and only there", () => {
    expect(topLevelAwaits('const a = await load("x");')).toEqual([1]);
    expect(topLevelAwaits("const a = 1;\nfor await (const b of c) d(b);")).toEqual([2]);
    expect(topLevelAwaits("export const a = foo(await b);")).toEqual([1]);
    expect(topLevelAwaits("async function a() {\n  await b();\n}")).toEqual([]);
    expect(topLevelAwaits("const a = { b: async () => { await c(); } };")).toEqual([]);
    expect(topLevelAwaits('const a = "await b";\nconst c = `${d} await {`;')).toEqual([]);
    expect(topLevelAwaits("const awaited = 1;")).toEqual([]);
  });

  test("window.RanzenpostI18n is written by the globals bridge alone", () => {
    const writers = scriptNames().filter((name) => /\bRanzenpostI18n\s*=[^=]/.test(readShipped(name)));
    expect(writers).toEqual([GLOBALS_MODULE]);
  });

  test("window.RanzenpostApi is written by the globals bridge alone", () => {
    const writers = scriptNames().filter((name) => /\bRanzenpostApi\s*=[^=]/.test(readShipped(name)));
    expect(writers).toEqual([GLOBALS_MODULE]);
  });

  test("window.RanzenpostFormat is written by the globals bridge alone", () => {
    const writers = scriptNames().filter((name) => /\bRanzenpostFormat\s*=[^=]/.test(readShipped(name)));
    expect(writers).toEqual([GLOBALS_MODULE]);
  });

  test("app.js binds every format global and nothing that is not there", () => {
    const bound = destructuredNames(readShipped("app.js"), "const", "window\\.RanzenpostFormat");
    expect([...bound].sort()).toEqual(Object.keys(formatGlobals()).sort());
  });

  test("app.js builds the format helpers once and leaves none of them on window", () => {
    const source = readShipped("app.js");
    expect(source.match(/\bcreateFormat\(/g)).toHaveLength(1);
    expect(destructuredNames(source, "var", "formats")).toEqual([]);
    const scriptNamesBound = destructuredNames(source, "const", "formats");
    const { window } = loadApp();
    for (const name of [...scriptNamesBound, "createFormat", "formats"]) {
      expect(window.eval(`typeof ${name}`), name).not.toBe("undefined");
      expect(Object.prototype.hasOwnProperty.call(window, name), name).toBe(false);
    }
    for (const name of FORMER_WINDOW_FORMAT_FUNCTIONS) {
      expect(Object.prototype.hasOwnProperty.call(window, name), name).toBe(false);
    }
    for (const name of MODULE_ONLY_FORMAT_NAMES) expect(window.eval(`typeof ${name}`), name).toBe("undefined");
  });

  test("the format helpers read the page clock when they run, not when app.js loads", () => {
    const { window } = loadApp();
    const nowMs = new Date(2026, 8, 24, 10).getTime();
    window.Date.now = () => nowMs;
    expect(window.eval(`relativeSince(${nowMs / 1000 - 7200})`)).toBe(window.eval("relativeFormatter().format(-2, 'hour')"));
    window.eval(`
      window.__realDate = Date;
      Date = class extends window.__realDate {
        constructor(...args) {
          if (args.length) super(...args);
          else super(2026, 8, 30, 10);
        }
      };
    `);
    const monday = window.eval("weekdayLabel(0)");
    const sunday = window.eval("weekdayLabel(6)");
    window.eval("Date = window.__realDate;");
    expect(monday).toBe(window.eval("dateFormatter({ weekday: 'short' }).format(new Date(2026, 8, 28))"));
    expect(sunday).toBe(window.eval("dateFormatter({ weekday: 'short' }).format(new Date(2026, 9, 4))"));
  });

  test("window.RanzenpostDom is written by the globals bridge alone", () => {
    const writers = scriptNames().filter((name) => /\bRanzenpostDom\s*=[^=]/.test(readShipped(name)));
    expect(writers).toEqual([GLOBALS_MODULE]);
  });

  test("window.RanzenpostShell is written by the globals bridge alone", () => {
    const writers = scriptNames().filter((name) => /\bRanzenpostShell\s*=[^=]/.test(readShipped(name)));
    expect(writers).toEqual([GLOBALS_MODULE]);
  });

  test("window.RanzenpostStore is written by the globals bridge alone", () => {
    const writers = scriptNames().filter((name) => /\bRanzenpostStore\s*=[^=]/.test(readShipped(name)));
    expect(writers).toEqual([GLOBALS_MODULE]);
    expect(Object.keys(storeGlobals())).toEqual(["createStore"]);
  });

  test("window.RanzenpostSelection is written by the globals bridge alone", () => {
    const writers = scriptNames().filter((name) => /\bRanzenpostSelection\s*=[^=]/.test(readShipped(name)));
    expect(writers).toEqual([GLOBALS_MODULE]);
    expect(Object.keys(selectionGlobals())).toEqual(["createSelection"]);
    expect([...MODULE_SELECTION_KEYS]).toEqual(SELECTION_KEYS);
  });

  test("app.js builds the selection once over store slots, binds both areas and keeps them off window", () => {
    const source = readShipped("app.js");
    const bound = destructuredNames(source, "const", "window\\.RanzenpostSelection");
    expect([...bound].sort()).toEqual(Object.keys(selectionGlobals()).sort());
    expect(source.match(/\bcreateSelection\(/g)).toEqual(["createSelection("]);
    expect(destructuredNames(source, "const", "selection")).toEqual(["letters: letterSelection", "pinboard: pinboardSelection"]);
    const start = source.indexOf("createSelection({\n");
    expect(start).toBeGreaterThan(-1);
    const block = source.slice(start, source.indexOf("\n});\n", start));
    expect(block).toMatch(/\bslot: \{ read: \(key\) => stateStore\.get\(key\), patch: \(partial\) => stateStore\.patch\(partial\) \}/);
    expect(block).not.toMatch(/(?<![\w$.])state\b(?!\s*:)/);
    expect(source).not.toMatch(/\bfunction\s+(createSelectionController|keepSelectionVisible|selectionBar|bulkLabel)\b/);
    const { window } = loadApp();
    for (const name of ["createSelection", "selection", "letterSelection", "pinboardSelection"]) {
      expect(window.eval(`typeof ${name}`), name).toBe(name === "createSelection" ? "function" : "object");
      expect(Object.prototype.hasOwnProperty.call(window, name), name).toBe(false);
    }
  });

  test("only the selection module writes the selection keys, app.js never hands one to the store by name", () => {
    const keys = SELECTION_KEYS.join("|");
    const namesKeyInStoreCall = new RegExp(`\\bstateStore\\s*\\.\\s*(?:set|patch)\\s*\\([^\\n]*\\b(?:${keys})\\b`);
    expect(namesKeyInStoreCall.test("stateStore.patch({ lettersSelectMode: false, lettersSelected: [] });")).toBe(true);
    expect(namesKeyInStoreCall.test('stateStore.set("pinboardSelected", kept);')).toBe(true);
    expect(namesKeyInStoreCall.test("stateStore.patch(fresh);")).toBe(false);
    expect(namesKeyInStoreCall.test('stateStore.set("toast", value);')).toBe(false);
    const offenders = readShipped("app.js")
      .split("\n")
      .map((line, index) => ({ line: index + 1, text: line.trim() }))
      .filter((hit) => namesKeyInStoreCall.test(hit.text))
      .map((hit) => `${hit.line}: ${hit.text}`);
    expect(offenders).toEqual([]);
  });

  test("app.js builds one store around the state object right after it and keeps it off window", () => {
    const source = readShipped("app.js");
    const bound = destructuredNames(source, "const", "window\\.RanzenpostStore");
    expect([...bound].sort()).toEqual(Object.keys(storeGlobals()).sort());
    expect(source.match(/\bcreateStore\(/g)).toEqual(["createStore("]);
    expect(source).toMatch(/\nconst state = \{\n[^]*?\n\};\nconst stateStore = createStore\(state, \{\n  reportError: [^\n]+\n\}\);\n/);
    const { window } = loadApp();
    for (const name of ["stateStore", "createStore"]) {
      expect(window.eval(`typeof ${name}`), name).not.toBe("undefined");
      expect(Object.prototype.hasOwnProperty.call(window, name), name).toBe(false);
    }
    expect(window.eval("stateStore.get('view') === state.view")).toBe(true);
    window.eval("stateStore.set('storeProbe', { a: 1 })");
    expect(window.eval("state.storeProbe")).toEqual({ a: 1 });
    window.eval("state.storeProbe = 'direct'");
    expect(window.eval("stateStore.get('storeProbe')")).toBe("direct");
  });

  test("a failing store listener in the app reaches the page error report and stops neither the caller nor the others", () => {
    const { window } = loadApp();
    const reported = [];
    window.reportError = (error) => reported.push(["report", error.message]);
    window.eval("stateStore.subscribe(() => { throw new Error('first'); }); stateStore.subscribe((keys) => { state.heardAfter = keys; });");
    window.eval("toast('still shown')");
    expect(window.eval("[state.toast.message, state.heardAfter]")).toEqual(["still shown", ["toast"]]);
    expect(reported).toEqual([["report", "first"]]);
    delete window.reportError;
    const logged = [];
    window.console.error = (error) => logged.push(error.message);
    window.eval("toggleLetterSelectMode()");
    expect(window.eval("[state.lettersSelectMode, state.heardAfter]")).toEqual([true, ["lettersSelectMode", "lettersSelected"]]);
    expect(logged).toEqual(["first"]);
  });

  test("a store write changes state and never repaints by itself", () => {
    const { window } = loadApp();
    window.eval("state.renderProbe = 0; render = () => { state.renderProbe += 1; }; rerender = () => { state.renderProbe += 1; };");
    const html = window.document.getElementById("app").innerHTML;
    window.eval("stateStore.subscribe(() => { state.heardProbe = (state.heardProbe || 0) + 1; })");
    window.eval("stateStore.set('toast', { message: 'quiet', kind: 'good' }); stateStore.patch({ sheet: null, sheetFocused: true })");
    expect(window.eval("[state.toast.message, state.sheetFocused, state.heardProbe, state.renderProbe]")).toEqual(["quiet", true, 2, 0]);
    expect(window.document.getElementById("app").innerHTML).toBe(html);
  });

  test("app.js binds every shell global and builds the toast once over state.toast", () => {
    const source = readShipped("app.js");
    const bound = destructuredNames(source, "const", "window\\.RanzenpostShell");
    expect([...bound].sort()).toEqual(Object.keys(shellGlobals()).sort());
    expect(source.match(/\bcreateToast\(/g)).toEqual(["createToast("]);
    expect(destructuredNames(source, "const", "toasts")).toEqual(TOAST_FUNCTIONS);
    expect(source).not.toMatch(/\bfunction\s+(toast|toastNode)\b|\btoastTimer\b/);
    const { window } = loadApp();
    for (const name of [...TOAST_FUNCTIONS, ...bound, "toasts"]) {
      expect(window.eval(`typeof ${name}`), name).toBe(name === "toasts" ? "object" : "function");
      expect(Object.prototype.hasOwnProperty.call(window, name), name).toBe(false);
    }
    window.eval('toast("probe", "bad")');
    expect(window.eval("state.toast")).toEqual({ message: "probe", kind: "bad" });
    expect(window.eval("toastNode()").ownerDocument).toBe(window.document);
  });

  test("the toast schedules with window.setTimeout when it runs, not when app.js loads", () => {
    const { window } = loadApp();
    const scheduled = [];
    const cleared = [];
    const realSet = window.setTimeout;
    const realClear = window.clearTimeout;
    window.setTimeout = (run, ms) => {
      const id = 42 + scheduled.length;
      scheduled.push({ run, ms, id });
      return id;
    };
    window.clearTimeout = (id) => cleared.push(id);
    try {
      window.eval('toast("first")');
      window.eval('toast("second")');
    } finally {
      window.setTimeout = realSet;
      window.clearTimeout = realClear;
    }
    const holds = scheduled.filter((entry) => entry.ms === 3200);
    expect(holds).toHaveLength(2);
    expect(cleared).toEqual(expect.arrayContaining([0, holds[0].id]));
    expect(cleared).not.toContain(holds[1].id);
    holds[1].run();
    expect(window.eval("state.toast")).toBe(null);
  });

  test("app.js builds the sheets once over the six sheet keys in state", () => {
    const source = readShipped("app.js");
    expect(source.match(/\bcreateSheets\(/g)).toEqual(["createSheets("]);
    expect(destructuredNames(source, "const", "sheets")).toEqual(SHEET_FUNCTIONS);
    expect(source).not.toMatch(/\bfunction\s+(openSheet|discardSheet|closeSheet|isSheetFormDirty|sheetState|sheet|sheetDiscardPanel|openNestedSheet|confirmAction)\b/);
    expect(source).toMatch(/\bfunction\s+copy\b/);
    const { window } = loadApp();
    for (const name of [...SHEET_FUNCTIONS, "confirmAction", "sheets"]) {
      expect(window.eval(`typeof ${name}`), name).toBe(name === "sheets" ? "object" : "function");
      expect(Object.prototype.hasOwnProperty.call(window, name), name).toBe(false);
    }
    for (const key of SHEET_KEYS) expect(window.eval(`"${key}" in state`), key).toBe(true);
    window.eval("state.sheetFocused = true; openSheet(() => sheet('Probe', ['body']))");
    expect(window.eval("typeof state.sheet")).toBe("function");
    expect(window.eval("state.sheetFocused")).toBe(false);
    expect(window.document.querySelector(".scrim .sheet-title").textContent).toBe("Probe");
    window.eval("sheetState(() => ({ label: 'a' })).label = 'b'; closeSheet()");
    expect(window.eval("state.sheetDiscardAsk")).toBe(true);
    expect(window.document.querySelector(".sheet-confirm")).not.toBe(null);
    window.eval("discardSheet()");
    expect(window.eval("[state.sheet, state.sheetForm, state.sheetFormDefault, state.sheetDiscardAsk]")).toEqual([null, null, null, false]);
    expect(window.document.querySelector(".scrim")).toBe(null);
  });

  test("confirmAction still resolves through onSheetClose when the sheet is closed", async () => {
    const { window } = loadApp();
    const answer = window.eval("confirmAction({ title: 'Sure?', text: 'x', confirmLabel: 'Yes' })");
    expect(window.document.querySelector(".scrim .sheet-title").textContent).toBe("Sure?");
    window.eval("closeSheet()");
    await expect(answer).resolves.toBe(false);
    expect(window.eval("[state.sheet, state.onSheetClose]")).toEqual([null, null]);
  });

  test("app.js writes the sheet, toast and selection keys only through the store and never by a computed key", () => {
    const keys = STORE_KEYS.join("|");
    const sheetKey = `\\bstate\\s*(?:\\.\\s*(?:${keys})\\b|\\[\\s*["'\`](?:${keys})["'\`]\\s*\\])`;
    const computedKey = `(?<![\\w$.])state\\s*\\[(?!\\s*(["'\`])[\\w$]*\\1\\s*\\])[^\\]]*\\]`;
    const patterns = [
      new RegExp(`${sheetKey}\\s*(?:[-+*/%&|^?]{0,3})=(?!=)`),
      new RegExp(`\\bdelete\\s+${sheetKey}(?!\\s*[.[])`),
      new RegExp(`${sheetKey}\\s*\\.\\s*(?:${ARRAY_MUTATORS})\\s*\\(`),
      new RegExp(`${computedKey}\\s*(?:[-+*/%&|^?]{0,3})=(?!=)`),
      new RegExp(`\\bdelete\\s+${computedKey}`),
      new RegExp(`${computedKey}\\s*\\.\\s*(?:${ARRAY_MUTATORS})\\s*\\(`),
      /\b(?:Object\s*\.\s*(?:assign|defineProperty|defineProperties)|Reflect\s*\.\s*(?:set|deleteProperty|defineProperty))\s*\(\s*state\s*[,)]/,
    ];
    const writesIn = (source) =>
      source
        .split("\n")
        .map((line, index) => ({ line: index + 1, text: line.trim() }))
        .filter((hit) => patterns.some((pattern) => pattern.test(hit.text)))
        .map((hit) => `${hit.line}: ${hit.text}`);
    expect(writesIn("state.sheet = null;\nstate.onSheetClose = () => {};\nstate['sheetForm'] = {};\nstate.sheetFocused ||= true;\nstate.toast = null;")).toHaveLength(5);
    expect(writesIn("if (state.sheet === periodsDetailSheet) dropSheet();\nconst a = state.sheetFormDefault == null;\nstate.sheetsSeen = 1;\nif (state.toast) nodes.push(toastNode());\nstate.toastSeen = 1;")).toEqual([]);
    const sneaky = [
      "Object.assign(state, { sheet: null });",
      "Object.assign( state ,patch);",
      "delete state.onSheetClose;",
      "delete state [ 'sheetForm' ];",
      "if (x) delete state.sheetDiscardAsk",
      "Object.defineProperty(state, 'sheet', { value: null });",
      "Reflect.set(state, 'sheetFocused', true);",
      "Reflect.deleteProperty(state, 'sheet');",
      "delete state.toast;",
      'state["toast"] = { message };',
      "state.lettersSelectMode = false;",
      "state.pinboardSelected = [];",
      "state.lettersSelected.push(key);",
      "state.pinboardSelected .splice(idx, 1);",
      "state['lettersSelected'].sort();",
      "state[key] = value;",
      "state[modeKey] = !state[modeKey];",
      "state[ selectedKey ].push(key);",
      "delete state[key];",
      "if (x) state[`${area}Selected`] = [];",
      "state[`sheet`] = null;",
    ];
    expect(writesIn(sneaky.join("\n"))).toHaveLength(sneaky.length);
    const allowed = [
      "Object.assign(state.config, patch);",
      "Object.assign({}, state, extra);",
      "delete state.refreshFailed[key];",
      "delete state.sheetForm.draft;",
      "delete state.sheetsSeen;",
      "const onSheetClose = state.onSheetClose;",
      "const keys = state.lettersSelected.slice();",
      "const selected = state.pinboardSelected.includes(key);",
      "const value = state[key];",
      "if (state[key] === 1) run();",
      "fresh[key] = value;",
      "detail.state[key] = 1;",
      "state.refreshFailed[key] = true;",
      "state.lettersSelectedSeen = [];",
      "state['view'] = 'post';",
    ];
    expect(writesIn(allowed.join("\n"))).toEqual([]);
    expect(writesIn(readShipped("app.js"))).toEqual([]);
  });

  test("entering a view writes every entry default through the store and hands out fresh lists", () => {
    const { window } = loadApp();
    const views = window.eval("Object.keys(VIEW_ENTRY_DEFAULTS)");
    expect(views.length).toBeGreaterThan(0);
    window.eval("state.heardKeys = []; stateStore.subscribe((keys) => state.heardKeys.push(...keys));");
    for (const view of views) {
      window.eval("state.heardKeys = []");
      window.eval(`applyViewEntryDefaults(${JSON.stringify(view)})`);
      expect(window.eval("state.heardKeys"), view).toEqual(window.eval(`Object.keys(VIEW_ENTRY_DEFAULTS[${JSON.stringify(view)}])`));
    }
    expect(window.eval("Object.keys(VIEW_ENTRY_DEFAULTS.post)")).toEqual(expect.arrayContaining(SELECTION_KEYS));
    window.eval("state.lettersSelected = ['1:2']; applyViewEntryDefaults('post')");
    expect(window.eval("state.lettersSelected")).toEqual([]);
    expect(window.eval("state.lettersSelected === VIEW_ENTRY_DEFAULTS.post.lettersSelected")).toBe(false);
  });

  test("the letter and noticeboard selection goes through the store and replaces the list instead of changing it", () => {
    const { window } = loadApp();
    window.eval("state.heardKeys = []; stateStore.subscribe((keys) => state.heardKeys.push(...keys));");
    const heard = () => window.eval("state.heardKeys.splice(0)");
    const steps = [
      ["toggleLetterSelectMode()", ["lettersSelectMode", "lettersSelected"], [true, []]],
      ["toggleLetterSelected('a'); toggleLetterSelected('b'); toggleLetterSelected('c')", ["lettersSelected", "lettersSelected", "lettersSelected"], [true, ["a", "b", "c"]]],
      ["toggleLetterSelected('b')", ["lettersSelected"], [true, ["a", "c"]]],
      ["letterSelection.keepVisible(['c', 'z'])", ["lettersSelected"], [true, ["c"]]],
      ["letterSelection.keepVisible(['c'])", [], [true, ["c"]]],
      ["exitLetterSelectMode()", ["lettersSelectMode", "lettersSelected"], [false, []]],
      ["enterLetterSelectMode('d')", ["lettersSelectMode", "lettersSelected"], [true, ["d"]]],
      ["enterLetterSelectMode('e')", [], [true, ["d"]]],
      ["setLettersFolder('archive')", ["lettersSelectMode", "lettersSelected"], [false, []]],
    ];
    for (const [code, keys, after] of steps) {
      window.eval("state.listBefore = state.lettersSelected; state.copyBefore = state.lettersSelected.slice()");
      window.eval(code);
      expect(heard(), code).toEqual(keys);
      expect(window.eval("[state.lettersSelectMode, state.lettersSelected]"), code).toEqual(after);
      expect(window.eval("state.listBefore"), code).toEqual(window.eval("state.copyBefore"));
    }
    window.eval("togglePinboardSelectMode(); togglePinboardSelected(1); togglePinboardSelected(2)");
    expect(heard()).toEqual(["pinboardSelectMode", "pinboardSelected", "pinboardSelected", "pinboardSelected"]);
    expect(window.eval("[state.pinboardSelectMode, state.pinboardSelected]")).toEqual([true, [1, 2]]);
    window.eval("state.postTab = 'pinboard'");
    window.eval("switchPostTab('letters')");
    expect(heard()).toEqual(expect.arrayContaining(SELECTION_KEYS));
    expect(window.eval("[state.lettersSelectMode, state.lettersSelected, state.pinboardSelectMode, state.pinboardSelected]")).toEqual([false, [], false, []]);
  });

  test("app.js hands the sheets and the toast slots that go through the store and never touch state", () => {
    const source = readShipped("app.js");
    const wiring = (factory) => {
      const start = source.indexOf(`${factory}({\n`);
      expect(start, factory).toBeGreaterThan(-1);
      return source.slice(start, source.indexOf("\n});\n", start));
    };
    for (const factory of ["createSheets", "createToast"]) {
      const block = wiring(factory);
      expect(block, factory).toMatch(/\bslot: \{ read: .*stateStore\.get\(.*write: .*stateStore\.set\(/);
      expect(block, factory).not.toMatch(/\bstate\b/);
    }
    const { window } = loadApp();
    window.eval("state.heardKeys = []; stateStore.subscribe((keys) => state.heardKeys.push(...keys));");
    window.eval("toast('probe'); openSheet(() => sheet('Probe', ['body'])); sheetState(() => ({ a: 1 })).a = 2; closeSheet(); discardSheet();");
    const heard = new Set(window.eval("state.heardKeys"));
    expect([...heard].sort()).toEqual([...SHELL_KEYS].sort());
    expect(window.eval("[state.toast.message, state.sheet, state.sheetDiscardAsk]")).toEqual(["probe", null, false]);
  });

  test("no lib module names the app state, so the shell reaches it only through the slots it is handed", () => {
    const namesState = (text) => /(?<![\w$.])state\b(?!\s*:)/.test(text);
    expect(["state.sheet = null;", "const a = state[key];", "run(state);", "return state;"].filter(namesState)).toHaveLength(4);
    expect(["const sheetState = 1;", "slot.read(key);", "options.state;", "{ state: 1 }", "const stateful = 1;"].filter(namesState)).toEqual([]);
    const offenders = libModules().flatMap((name) =>
      readShipped(name)
        .split("\n")
        .map((line, index) => ({ line: index + 1, text: line }))
        .filter((hit) => namesState(hit.text))
        .map((hit) => `${name}:${hit.line}`)
    );
    expect(offenders).toEqual([]);
  });

  test("the sheets read the layout, the repaint and the page timers when they run, not when app.js loads", () => {
    const { window } = loadApp();
    const realMatch = window.matchMedia;
    const realSet = window.setTimeout;
    const scheduled = [];
    let phone = null;
    let wide = null;
    try {
      window.eval("state.renderProbe = 0; rerender = () => { state.renderProbe += 1; };");
      window.eval("openSheet(() => null)");
      expect(window.eval("state.renderProbe")).toBe(1);
      window.setTimeout = (run, ms) => {
        scheduled.push({ run, ms });
        return 7;
      };
      window.matchMedia = () => ({ matches: false });
      phone = window.eval("sheet('Phone', [])");
      window.matchMedia = (query) => ({ matches: query.includes("900") });
      wide = window.eval("sheet('Wide', [])");
    } finally {
      window.matchMedia = realMatch;
      window.setTimeout = realSet;
    }
    expect(phone.className).toBe("scrim");
    expect(wide.className).toBe("scrim dialog");
    expect(scheduled.map((entry) => entry.ms)).toEqual([0, 0]);
    window.document.body.append(wide);
    window.eval("state.sheetFocused = false");
    scheduled[1].run();
    expect(window.document.activeElement).toBe(wide.querySelector(".sheet-title"));
    expect(window.eval("state.sheetFocused")).toBe(true);
  });

  test("app.js binds every DOM kit global and builds the kit once on its own document", () => {
    const source = readShipped("app.js");
    const bound = destructuredNames(source, "const", "window\\.RanzenpostDom");
    expect([...bound].sort()).toEqual(Object.keys(domGlobals()).sort());
    expect(source.match(/\bcreateDom\(/g)).toEqual(["createDom("]);
    expect(source).toMatch(/\bcreateDom\(\{ page: document \}\)/);
    expect(destructuredNames(source, "const", "dom")).toEqual(DOM_KIT_FUNCTIONS);
    const { window } = loadApp();
    for (const name of [...DOM_KIT_FUNCTIONS, ...bound, "dom"]) {
      expect(window.eval(`typeof ${name}`), name).not.toBe("undefined");
      expect(Object.prototype.hasOwnProperty.call(window, name), name).toBe(false);
    }
    expect(window.eval('el("div")').ownerDocument).toBe(window.document);
  });

  test("app.js binds every request global and nothing that is not there", () => {
    const bound = destructuredNames(readShipped("app.js"), "const", "window\\.RanzenpostApi");
    expect([...bound].sort()).toEqual(Object.keys(apiGlobals()).sort());
  });

  test("app.js builds the request helpers once and leaves on window only what the tests call", () => {
    const source = readShipped("app.js");
    expect(source.match(/\bcreateApi\(/g)).toHaveLength(1);
    expect(destructuredNames(source, "var", "requests")).toEqual(WINDOW_API_FUNCTIONS);
    expect(destructuredNames(source, "const", "requests")).toEqual(SCRIPT_API_FUNCTIONS);
    const { window } = loadApp();
    for (const name of WINDOW_API_FUNCTIONS) expect(typeof window[name], name).toBe("function");
    for (const name of [...SCRIPT_API_FUNCTIONS, "createApi", "requests"]) {
      expect(window.eval(`typeof ${name}`), name).not.toBe("undefined");
      expect(Object.prototype.hasOwnProperty.call(window, name), name).toBe(false);
    }
    for (const name of FORMER_WINDOW_API_FUNCTIONS) {
      expect(Object.prototype.hasOwnProperty.call(window, name), name).toBe(false);
    }
    for (const name of MODULE_ONLY_API_NAMES) expect(window.eval(`typeof ${name}`), name).toBe("undefined");
  });

  test("app.js never calls fetch directly, only through the request helpers", () => {
    const RAW_FETCH = /(?<!\.)\bfetch\s*\(/;
    const offenders = readShipped("app.js")
      .split("\n")
      .map((line, index) => ({ line: index + 1, text: line }))
      .filter((hit) => RAW_FETCH.test(hit.text) && !hit.text.includes("window.fetch"))
      .map((hit) => `${hit.line}: ${hit.text.trim()}`);
    expect(offenders).toEqual([]);
  });

  test("the boundary check sees a bare fetch call and leaves the window.fetch wiring alone", () => {
    const RAW_FETCH = /(?<!\.)\bfetch\s*\(/;
    expect(RAW_FETCH.test('const response = await fetch(apiUrl(path));')).toBe(true);
    expect(RAW_FETCH.test('  fetch: (...args) => window.fetch(...args),')).toBe(false);
    expect(RAW_FETCH.test('const requested = fetchAppFile(path);')).toBe(false);
  });

  test("the request helpers read window.fetch when they run, not when app.js loads", async () => {
    const { window } = loadApp({ url: "http://localhost/api/hassio_ingress/TOKEN123/index.html" });
    const requested = [];
    window.fetch = (url, options) => {
      requested.push({ url, body: options.body });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) });
    };
    await window.eval('postJson("api/config", { a: 1 })');
    await window.eval('postFormData("api/absences", { b: 2 }, [])');
    const sent = (path) => requested.find((entry) => entry.url === `http://localhost/api/hassio_ingress/TOKEN123/${path}`);
    expect(sent("api/config").body).toBe('{"a":1}');
    expect(sent("api/absences").body instanceof window.FormData).toBe(true);
  });

  test("app.js binds every translation global and nothing that is not there", () => {
    const source = readShipped("app.js");
    const bound = [...destructuredNames(source, "const"), ...destructuredNames(source, "var")];
    expect(bound.length).toBeGreaterThan(0);
    expect([...bound].sort()).toEqual(Object.keys(i18nGlobals()).sort());
  });

  test("app.js keeps the translation functions as window properties for the other scripts", () => {
    const functions = destructuredNames(readShipped("app.js"), "var");
    const exposed = Object.entries(i18nGlobals())
      .filter(([name, value]) => typeof value === "function" && !APP_ONLY_GLOBALS.includes(name))
      .map(([name]) => name);
    expect([...functions].sort()).toEqual(exposed.sort());
  });

  test("after boot the other scripts find the same translation functions on window", () => {
    const { window } = loadApp();
    const globals = window.RanzenpostI18n;
    const functions = destructuredNames(readShipped("app.js"), "var");
    for (const name of functions) expect(window[name], name).toBe(globals[name]);
    expect(window.eval("LANGUAGES")).toBe(globals.LANGUAGES);
    expect(window.eval("typeof i18n")).toBe("undefined");
    expect(window.eval("typeof setLanguageChoice")).toBe("undefined");
    for (const name of APP_ONLY_GLOBALS) expect(Object.prototype.hasOwnProperty.call(window, name), name).toBe(false);
    expect(window.t("common.loading")).not.toBe("common.loading");
  });

  test("app.js reads and changes the translation state only through the core functions", () => {
    expect(readShipped("app.js")).not.toMatch(/\bi18n\.(language|choice|base|messages)\b/);
  });

  test("the language loader leaves on window only what the wizard and the tests call", () => {
    const { window } = loadApp();
    for (const name of WINDOW_LANGUAGE_FUNCTIONS) expect(typeof window[name], name).toBe("function");
    expect(window.eval("typeof loadBaseLanguage")).toBe("function");
    expect(Object.prototype.hasOwnProperty.call(window, "loadBaseLanguage")).toBe(false);
    for (const name of ["applyDocumentLanguage", "fetchBundle", "normalizeLanguage", "preferredLanguages"]) {
      expect(window.eval(`typeof ${name}`), name).toBe("undefined");
    }
  });
});
