import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const FRONTEND = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export const VENDOR_EXEMPT_PATHS = ["vendor"];
export const TEST_TREE_PATHS = ["tests"];

export const SCRIPT_SUFFIXES = [".js", ".mjs"];
export const STYLE_SUFFIXES = [".css"];
export const MARKUP_SUFFIXES = [".html"];
export const GUARDED_SUFFIXES = [...SCRIPT_SUFFIXES, ...STYLE_SUFFIXES, ...MARKUP_SUFFIXES];

function under(relative, prefixes) {
  return prefixes.some((prefix) => relative === prefix || relative.startsWith(`${prefix}/`));
}

export function isShipped(relative) {
  return !under(relative, VENDOR_EXEMPT_PATHS) && !under(relative, TEST_TREE_PATHS);
}

function walk(directory, relative, found) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const name = relative ? `${relative}/${entry.name}` : entry.name;
    if (entry.isDirectory()) walk(path.join(directory, entry.name), name, found);
    else if (entry.isFile()) found.push(name);
  }
  return found;
}

export function shippedNames(suffixes = GUARDED_SUFFIXES, root = FRONTEND) {
  return walk(root, "", [])
    .filter((name) => suffixes.includes(path.posix.extname(name)) && isShipped(name))
    .sort();
}

export function scriptNames(root = FRONTEND) {
  return shippedNames(SCRIPT_SUFFIXES, root);
}

export function readShipped(name, root = FRONTEND) {
  return fs.readFileSync(path.join(root, ...name.split("/")), "utf8");
}

export function shippedScripts(root = FRONTEND) {
  return scriptNames(root).map((name) => ({ name, source: readShipped(name, root) }));
}

export function shippedScriptText(root = FRONTEND) {
  return shippedScripts(root).map((script) => script.source).join("\n");
}

export const APP_PARTS_DIR = "app";

export function pageBodyScripts(root = FRONTEND) {
  const html = readShipped("index.html", root);
  const body = /<body>([\s\S]*?)<\/body>/.exec(html);
  return [...(body ? body[1] : "").matchAll(/<script\b([^>]*)>\s*<\/script[^>]*>/gi)].map((match) => {
    const src = /\bsrc="\.\/([\w./-]+)\?v=\d+"/.exec(match[1]);
    return { name: src ? src[1] : "", module: /\stype="module"/.test(match[1]) };
  });
}

export function appSourceNames(root = FRONTEND) {
  return pageBodyScripts(root)
    .filter((script) => !script.module)
    .map((script) => script.name)
    .filter((name) => name === "app.js" || name.startsWith(`${APP_PARTS_DIR}/`));
}

export function appSources(root = FRONTEND) {
  return appSourceNames(root).map((name) => ({ name, source: readShipped(name, root) }));
}

export function appSourceText(root = FRONTEND) {
  return appSources(root).map((script) => script.source).join("\n");
}
