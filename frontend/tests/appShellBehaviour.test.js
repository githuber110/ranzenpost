import { describe, expect, test } from "vitest";
import fs from "node:fs";
import path from "node:path";

const FRONTEND = path.resolve(__dirname, "..");

function readFrontend(name) {
  return fs.readFileSync(path.join(FRONTEND, name), "utf8");
}

function parseDeclarations(body) {
  const decls = {};
  for (const chunk of body.split(";")) {
    const at = chunk.indexOf(":");
    if (at === -1) continue;
    const prop = chunk.slice(0, at).trim().toLowerCase();
    const value = chunk.slice(at + 1).trim();
    if (!prop || prop.startsWith("--") === false && !/^[a-z-]+$/.test(prop)) continue;
    decls[prop] = value;
  }
  return decls;
}

function parseRules(css, source) {
  const rules = [];
  let depth = 0;
  let start = 0;
  let preludeStart = 0;
  const stack = [];
  for (let i = 0; i < css.length; i++) {
    const ch = css[i];
    if (ch === "{") {
      const prelude = css.slice(preludeStart, i).trim();
      stack.push({ prelude, bodyStart: i + 1 });
      depth++;
      preludeStart = i + 1;
    } else if (ch === "}") {
      const frame = stack.pop();
      depth--;
      preludeStart = i + 1;
      if (!frame) continue;
      if (frame.prelude.startsWith("@")) continue;
      const nested = css.slice(frame.bodyStart, i);
      if (nested.includes("{")) continue;
      rules.push({
        selector: frame.prelude.replace(/\s+/g, " "),
        selectors: frame.prelude.split(",").map((s) => s.replace(/\s+/g, " ").trim()),
        declarations: parseDeclarations(nested),
        source,
      });
    }
  }
  void depth;
  void start;
  return rules;
}

function scrollContainers(rules) {
  return rules.filter((rule) => {
    for (const [prop, value] of Object.entries(rule.declarations)) {
      if (!/^overflow(-x|-y)?$/.test(prop)) continue;
      if (/\b(auto|scroll)\b/.test(value)) return true;
    }
    return false;
  });
}

function hasOverscroll(rule) {
  return Object.keys(rule.declarations).some((prop) => prop.startsWith("overscroll-behavior"));
}

function findRule(rules, selector) {
  return rules.find((rule) => rule.selectors.includes(selector));
}

const PAN_ONLY = new Set(["pan-x", "pan-y", "pan-left", "pan-right", "pan-up", "pan-down"]);

const styles = readFrontend("styles.css");
const wizard = readFrontend("wizard.css");
const html = readFrontend("index.html");
const manifest = JSON.parse(readFrontend("manifest.webmanifest"));
const rules = [...parseRules(styles, "styles.css"), ...parseRules(wizard, "wizard.css")];

describe("[P168] the shell behaves like an app, not a web page", () => {
  test("the stylesheets really parse into rules the checks can read", () => {
    expect(rules.length).toBeGreaterThan(100);
    expect(findRule(rules, ".screen")).toBeDefined();
    expect(findRule(rules, ".app")).toBeDefined();
    expect(findRule(rules, ".tabbar")).toBeDefined();
  });

  test("every scrolling container declares overscroll-behavior", () => {
    const containers = scrollContainers(rules);
    expect(containers.length).toBeGreaterThanOrEqual(5);
    const leaking = containers
      .filter((rule) => !hasOverscroll(rule))
      .map((rule) => `${rule.source}: ${rule.selector}`);
    expect(leaking).toEqual([]);
  });

  test("the document itself cannot rubber-band or chain in any direction", () => {
    const root = findRule(rules, "html");
    expect(root, "html, body rule").toBeDefined();
    expect(root.declarations["overscroll-behavior"]).toBe("none");
    expect(root.declarations["overscroll-behavior-x"]).toBeUndefined();
    expect(root.declarations["overscroll-behavior-y"]).toBeUndefined();
  });

  test("the app surface allows panning only, so double-tap and pinch zoom do not fire inside it", () => {
    for (const selector of [".app", ".scrim", ".sheet", ".color-dialog-scrim"]) {
      const rule = findRule(rules, selector);
      expect(rule, `${selector} rule`).toBeDefined();
      const value = rule.declarations["touch-action"];
      expect(value, `${selector} touch-action`).toBeDefined();
      const tokens = value.split(/\s+/);
      for (const token of tokens) {
        expect(PAN_ONLY.has(token), `${selector} touch-action token "${token}"`).toBe(true);
      }
      expect(tokens).toContain("pan-y");
    }
  });

  test("every interactive element type declares touch-action", () => {
    for (const selector of ["button", "a[href]", "input", "select", "textarea", '[role="button"]']) {
      const rule = rules.find(
        (candidate) => candidate.selectors.includes(selector) && candidate.declarations["touch-action"]
      );
      expect(rule, `${selector} needs a touch-action declaration`).toBeDefined();
      expect(rule.declarations["touch-action"]).toBe("manipulation");
    }
  });

  test("the viewport keeps system zoom available instead of switching it off", () => {
    const viewport = /<meta\s+name="viewport"\s+content="([^"]+)"/.exec(html);
    expect(viewport, "viewport meta").not.toBeNull();
    const content = viewport[1];
    expect(content).toContain("viewport-fit=cover");
    expect(content).not.toMatch(/user-scalable\s*=\s*(no|0)/);
    expect(content).not.toMatch(/maximum-scale/);
  });

  test("safe areas are read on all four physical sides and actually consumed", () => {
    for (const side of ["top", "bottom", "left", "right"]) {
      expect(styles, `env(safe-area-inset-${side})`).toContain(`env(safe-area-inset-${side}`);
    }
    const root = rules.find((rule) => rule.selectors.includes(":root") && rule.declarations["--safe-x"]);
    expect(root, ":root --safe-x").toBeDefined();
    expect(root.declarations["--safe-x"]).toContain("safe-area-inset-left");
    expect(root.declarations["--safe-x"]).toContain("safe-area-inset-right");
    expect(root.declarations["--safe-t"]).toContain("safe-area-inset-top");
    expect(root.declarations["--safe-b"]).toContain("safe-area-inset-bottom");

    const usesSafeX = rules.filter((rule) =>
      Object.values(rule.declarations).some((value) => value.includes("var(--safe-x)"))
    );
    const selectors = usesSafeX.flatMap((rule) => rule.selectors);
    for (const selector of [".app", ".tabbar", ".sheet"]) {
      expect(selectors, `${selector} must respect the side safe areas`).toContain(selector);
    }
  });

  test("the side safe areas are applied logically, so right-to-left stays correct", () => {
    const usesSafeX = rules.filter((rule) =>
      Object.values(rule.declarations).some((value) => value.includes("var(--safe-x)"))
    );
    for (const rule of usesSafeX) {
      for (const prop of Object.keys(rule.declarations)) {
        expect(prop, `${rule.selector} uses a physical property for the safe area`).not.toMatch(
          /^(margin|padding|border|inset)-(left|right)$/
        );
      }
    }
  });

  test("the standalone shell is declared for iOS and for the manifest", () => {
    expect(html).toMatch(/<meta\s+name="apple-mobile-web-app-capable"\s+content="yes">/);
    expect(html).toMatch(/<meta\s+name="mobile-web-app-capable"\s+content="yes">/);
    const statusBar = /<meta\s+name="apple-mobile-web-app-status-bar-style"\s+content="([^"]+)">/.exec(html);
    expect(statusBar, "apple-mobile-web-app-status-bar-style").not.toBeNull();
    expect(["default", "black", "black-translucent"]).toContain(statusBar[1]);
    expect(manifest.display).toBe("standalone");
    expect(manifest.orientation).toBe("portrait");
  });

  test("text stays selectable exactly where reading happens and nowhere else", () => {
    const selectable = rules.filter((rule) => rule.declarations["user-select"] === "text");
    const locked = rules.filter((rule) => rule.declarations["user-select"] === "none");
    expect(locked.length).toBeGreaterThan(0);
    expect(selectable.flatMap((rule) => rule.selectors)).toContain(".body-html");
  });

  test("the checks would really catch a regression", () => {
    const planted = parseRules(
      ".leak { overflow-y: auto; } .ok { overflow-y: auto; overscroll-behavior: contain; }",
      "planted"
    );
    const leaking = scrollContainers(planted).filter((rule) => !hasOverscroll(rule));
    expect(leaking.map((rule) => rule.selector)).toEqual([".leak"]);

    const zoomable = parseRules(".app { touch-action: auto; }", "planted");
    const tokens = zoomable[0].declarations["touch-action"].split(/\s+/);
    expect(tokens.every((token) => PAN_ONLY.has(token))).toBe(false);
  });
});
