import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const stylesCss = fs.readFileSync(path.join(dirname, "..", "styles.css"), "utf8");

function spacingScale(css) {
  const scale = {};
  const re = /--(s-\d+):\s*(\d+)px/g;
  let hit;
  while ((hit = re.exec(css)) !== null) scale[hit[1]] = Number(hit[2]);
  return scale;
}

describe("[P132] pinboard header: chip row / search field spacing", () => {
  test("search field keeps a spacing-scale gap above it in the sticky list head", () => {
    const match = /\.list-head \.search-field\s*\{([^}]*)\}/.exec(stylesCss);
    expect(match).not.toBeNull();
    const token = /margin-top:\s*var\(--(s-\d+)\)/.exec(match[1]);
    expect(token, "margin-top must come from the spacing scale").not.toBeNull();
    const scale = spacingScale(stylesCss);
    expect(scale[token[1]], `--${token[1]} must be defined in :root`).toBeGreaterThanOrEqual(12);
  });

  test("uses the shared spacing token, not a hardcoded pixel value", () => {
    const match = /\.list-head \.search-field\s*\{([^}]*)\}/.exec(stylesCss);
    expect(match[1]).not.toMatch(/margin-top:\s*\d+px/);
  });
});
