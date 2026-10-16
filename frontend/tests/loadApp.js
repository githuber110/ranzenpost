import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";
import { apiGlobals } from "../lib/api.js";
import { domGlobals } from "../lib/dom.js";
import { formatGlobals } from "../lib/format.js";
import { i18nGlobals } from "../lib/i18nGlobals.js";
import { selectionGlobals } from "../lib/selection.js";
import { shellGlobals } from "../lib/shell.js";
import { storeGlobals } from "../lib/store.js";
import { pageBodyScripts, readShipped } from "./shippedSources.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(dirname, "..");

const indexHtml = fs.readFileSync(path.join(frontendDir, "index.html"), "utf8");
export const ON_DEMAND_SCRIPTS = ["qr.js"];
export const LOADED_SCRIPTS = pageBodyScripts(frontendDir).filter((script) => !ON_DEMAND_SCRIPTS.includes(script.name));
const scriptSources = new Map(
  LOADED_SCRIPTS.filter((script) => !script.module).map((script) => [script.name, readShipped(script.name, frontendDir)])
);
const baseMessages = fs.readFileSync(path.join(frontendDir, "i18n", "de.json"), "utf8");

export function evalWith(window, code, ...values) {
  const own = values.map((value) =>
    value === undefined || typeof value === "function" ? value : window.JSON.parse(JSON.stringify(value))
  );
  const run = window.eval("(function (testArgs, testCode) { return eval(testCode); })");
  return run(own, code);
}

function extractHead(html) {
  const match = /<head>([\s\S]*?)<\/head>/.exec(html);
  return match ? match[1] : "";
}

export function loadApp({ url = "http://localhost/" } = {}) {
  const dom = new JSDOM(
    `<!doctype html><html><head>${extractHead(indexHtml)}</head><body><div id="app"></div></body></html>`,
    { runScripts: "dangerously", url }
  );
  const { window } = dom;
  window.fetch = () => Promise.reject(new Error("network disabled in tests"));
  Object.defineProperty(window.navigator, "language", { value: "de-DE", configurable: true });
  Object.defineProperty(window.navigator, "languages", { value: ["de-DE", "de"], configurable: true });
  if (!window.matchMedia) {
    window.matchMedia = () => ({
      matches: false,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
    });
  }

  const inject = (source) => {
    const script = window.document.createElement("script");
    script.textContent = source;
    window.document.body.appendChild(script);
  };
  const installGlobals = () => {
    window.RanzenpostI18n = i18nGlobals();
    window.RanzenpostApi = apiGlobals();
    window.RanzenpostFormat = formatGlobals();
    window.RanzenpostDom = domGlobals();
    window.RanzenpostShell = shellGlobals();
    window.RanzenpostStore = storeGlobals();
    window.RanzenpostSelection = selectionGlobals();
  };
  const loadErrors = [];
  const noteLoadError = (event) => loadErrors.push(event.error || event.message);
  window.addEventListener("error", noteLoadError);
  for (const script of LOADED_SCRIPTS) {
    if (script.module) installGlobals();
    else inject(scriptSources.get(script.name));
    if (loadErrors.length) {
      throw new Error(`${script.name} failed while the page loaded: ${loadErrors.map(String).join("; ")}`);
    }
  }
  window.removeEventListener("error", noteLoadError);
  const renderNotice = window.renderNotice;
  window.renderNotice = (...args) => {
    renderNotice(...args);
    window.eval("state.detached = false");
  };
  window.setLanguageBundle("de", JSON.parse(baseMessages), JSON.parse(baseMessages));

  return { window, document: window.document };
}
