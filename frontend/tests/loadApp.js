import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";
import { apiGlobals } from "../lib/api.js";
import { domGlobals } from "../lib/dom.js";
import { formatGlobals } from "../lib/format.js";
import { i18nGlobals } from "../lib/i18nGlobals.js";
import { shellGlobals } from "../lib/shell.js";
import { storeGlobals } from "../lib/store.js";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(dirname, "..");

const indexHtml = fs.readFileSync(path.join(frontendDir, "index.html"), "utf8");
const blocksJs = fs.readFileSync(path.join(frontendDir, "blocks.js"), "utf8");
const periodsJs = fs.readFileSync(path.join(frontendDir, "periods.js"), "utf8");
const stepsJs = fs.readFileSync(path.join(frontendDir, "steps.js"), "utf8");
const wizardJs = fs.readFileSync(path.join(frontendDir, "wizard.js"), "utf8");
const pdfViewerJs = fs.readFileSync(path.join(frontendDir, "pdfviewer.js"), "utf8");
const colourJs = fs.readFileSync(path.join(frontendDir, "colour.js"), "utf8");
const appJs = fs.readFileSync(path.join(frontendDir, "app.js"), "utf8");
const baseMessages = fs.readFileSync(path.join(frontendDir, "i18n", "de.json"), "utf8");

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
  inject(blocksJs);
  inject(periodsJs);
  inject(stepsJs);
  inject(wizardJs);
  inject(pdfViewerJs);
  inject(colourJs);
  window.RanzenpostI18n = i18nGlobals();
  window.RanzenpostApi = apiGlobals();
  window.RanzenpostFormat = formatGlobals();
  window.RanzenpostDom = domGlobals();
  window.RanzenpostShell = shellGlobals();
  window.RanzenpostStore = storeGlobals();
  inject(appJs);
  const renderNotice = window.renderNotice;
  window.renderNotice = (...args) => {
    renderNotice(...args);
    window.eval("state.detached = false");
  };
  window.setLanguageBundle("de", JSON.parse(baseMessages), JSON.parse(baseMessages));

  return { window, document: window.document };
}
