import { describe, expect, test } from "vitest";
import fs from "node:fs";
import path from "node:path";

const FRONTEND = path.resolve(__dirname, "..");
const SOURCES = ["app.js", "wizard.js"].map((name) => ({ name, text: fs.readFileSync(path.join(FRONTEND, name), "utf8") }));

export const SCHOOL_ROUTE_PATHS = [
  "api/me",
  "api/absences",
  "api/absences/sick-note-pdf",
  "api/absences/attachment",
  "api/absences/delete",
  "api/holidays",
  "api/holidays/region-suggestion",
  "api/messenger/room",
  "api/messenger/teachers",
  "api/messenger/room/teacher/children",
  "api/messenger/room/teacher",
  "api/messenger/media",
  "api/messenger/send",
  "api/messenger/read",
  "api/letters/detail",
  "api/letters/attachment",
  "api/letters/confirm",
  "api/letters/reply",
  "api/letters/archive",
  "api/letters/restore",
  "api/pinboard/attachment",
  "api/modules/recheck",
  "api/password",
  "api/password/repair",
  "api/account/disconnect",
];

function escape(text) {
  return text.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
}

function enclosingFunction(text, index) {
  const before = text.slice(0, index);
  const start = Math.max(before.lastIndexOf("\nfunction "), before.lastIndexOf("\nasync function "), 0);
  const end = text.indexOf("\n}\n", index);
  return text.slice(start, end < 0 ? text.length : end);
}

function namesSchool(body) {
  return /connection_id|connection=|connectionQuery\(/.test(body);
}

function helperNames(body) {
  return [...body.matchAll(/([A-Za-z_$][\w$]*)\(/g)].map((match) => match[1]);
}

function helperCarriesSchool(text, name) {
  const at = text.search(new RegExp(`\\nfunction ${escape(name)}\\(`));
  if (at < 0) return false;
  const end = text.indexOf("\n}\n", at);
  return /connection_id|connection=/.test(text.slice(at, end));
}

function callsOf(route) {
  const found = [];
  const pattern = new RegExp(`["\`]${escape(route)}(?=[?"\`/$]|\\$\\{)`, "g");
  for (const source of SOURCES) {
    for (const match of source.text.matchAll(pattern)) {
      const next = source.text.slice(match.index + 1 + route.length, match.index + 2 + route.length);
      if (next === "/" && !["api/absences/attachment", "api/letters/attachment", "api/pinboard/attachment", "api/messenger/media"].includes(route)) continue;
      found.push({ source, index: match.index });
    }
  }
  return found;
}

describe("every school route the app calls names its school", () => {
  test.each(SCHOOL_ROUTE_PATHS)("%s", (route) => {
    for (const { source, index } of callsOf(route)) {
      const body = enclosingFunction(source.text, index);
      const direct = namesSchool(body);
      const helped = helperNames(body).some((name) => helperCarriesSchool(source.text, name));
      const line = source.text.slice(0, index).split("\n").length;
      expect(direct || helped, `${source.name}:${line} calls ${route} without a school`).toBe(true);
    }
  });

  test("the guard finds the calls it is meant to watch", () => {
    for (const route of ["api/messenger/teachers", "api/absences/sick-note-pdf", "api/letters/confirm", "api/modules/recheck"]) {
      expect(callsOf(route).length, route).toBeGreaterThan(0);
    }
  });

  test("a call without a school is caught", () => {
    const text = '\nasync function probe() {\n  await getJson(`api/messenger/teachers?query=${query}`);\n}\n';
    const index = text.indexOf("`api/");
    const body = enclosingFunction(text, index);
    expect(namesSchool(body)).toBe(false);
  });
});
