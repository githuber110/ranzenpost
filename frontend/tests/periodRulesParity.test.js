import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";

const dirname = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(dirname, "..", "periods.js"), "utf8");
const shared = JSON.parse(fs.readFileSync(path.join(dirname, "..", "..", "tests", "own-entries-cases.json"), "utf8"));

function rules() {
  const context = { window: {} };
  vm.runInNewContext(source, context);
  return context.window.RanzenpostPeriods;
}

describe("own entry rules match the backend", () => {
  const P = rules();

  test("the shared cases cover cut, hidden and untouched entries", () => {
    const states = new Set(shared.cases.flatMap((entry) => entry.days.flatMap((day) => day.items.map((item) => item[3]))));
    expect([...states].sort()).toEqual([P.STATE_CUT, P.STATE_HIDDEN, P.STATE_OK].sort());
  });

  for (const entry of shared.cases) {
    test(`${entry.name} resolves every day and status like the backend`, () => {
      const rows = P.gridRows(entry.grid);
      for (const day of entry.days) {
        const spans = P.spansFor(rows, day.periods);
        const items = P.resolveDay(entry.entries, spans, day.day, day.child, day.free);
        expect(items.map((item) => [item.entry.id, item.start, item.end, item.state, item.number]), `${day.day} ${day.child}`).toEqual(day.items);
      }
      for (const item of entry.entries) {
        const status = P.entryStatus(item, rows, entry.profiles, shared.children);
        expect([status.state, status.number, status.start, status.end], item.id).toEqual(entry.statuses[item.id]);
      }
    });
  }
});
