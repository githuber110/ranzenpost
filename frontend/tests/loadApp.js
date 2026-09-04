import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(dirname, "..");

const indexHtml = fs.readFileSync(path.join(frontendDir, "index.html"), "utf8");
const stepsJs = fs.readFileSync(path.join(frontendDir, "steps.js"), "utf8");
const wizardJs = fs.readFileSync(path.join(frontendDir, "wizard.js"), "utf8");
const pdfViewerJs = fs.readFileSync(path.join(frontendDir, "pdfviewer.js"), "utf8");
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
  inject(stepsJs);
  inject(wizardJs);
  inject(pdfViewerJs);
  inject(appJs);
  window.setLanguageBundle("de", JSON.parse(baseMessages), JSON.parse(baseMessages));

  return { window, document: window.document };
}
