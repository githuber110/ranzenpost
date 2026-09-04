import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

describe("[P155] compact header: screen title sits level with the settings gear", () => {
  test("timetable with a single child shows the title in the .header bar", () => {
    const { window } = loadApp();
    window.eval("state.children = [{ child_id: 'c1', name: 'Mia' }]; state.childId = 'c1';");
    const bar = window.eval("header('timetable')");
    expect(bar.querySelector(".header-title")).not.toBeNull();
    expect(bar.querySelector(".header-title").textContent).not.toBe("");
    expect(bar.querySelector(".child-switch")).toBeNull();
  });

  test("timetable with several children keeps the child switch and drops the redundant title", () => {
    const { window } = loadApp();
    window.eval(
      "state.children = [{ child_id: 'c1', name: 'Mia' }, { child_id: 'c2', name: 'Ben' }]; state.childId = 'c1';"
    );
    const bar = window.eval("header('timetable')");
    expect(bar.querySelector(".header-title-row")).toBeNull();
    expect(bar.querySelector(".child-switch")).not.toBeNull();
    expect(bar.querySelector(".header-actions .child-switch")).not.toBeNull();
  });

  test("post always shows a title, no back button", () => {
    const { window } = loadApp();
    const bar = window.eval("header('post')");
    expect(bar.querySelector(".header-title")).not.toBeNull();
    expect(bar.querySelector(".header-back")).toBeNull();
  });

  test("letters detail shows back + title + tech-details button in one row", () => {
    const { window } = loadApp();
    window.eval(
      "state.letterDetail = { letter: { title: 'Infobrief', letter_id: '1', recipient_id: '2' }, loading: false };"
    );
    const bar = window.eval("header('post')");
    const row = bar.querySelector(".header-title-row");
    expect(row).not.toBeNull();
    expect(row.querySelector(".header-back")).not.toBeNull();
    expect(row.querySelector(".header-title").textContent).toBe("Infobrief");
    expect(row.querySelector(".tech-btn")).not.toBeNull();
  });

  test("settings gear is present on every screen except settings itself", () => {
    const { window } = loadApp();
    const withGear = window.eval("header('post')");
    const withoutGear = window.eval("header('settings')");
    expect(withGear.querySelector(".header-actions .icon-btn")).not.toBeNull();
    expect(withoutGear.querySelector(".header-actions .icon-btn")).toBeNull();
  });

  test("[P178] the overview greeting moved into the sticky header, [P188] settings carry theirs there too", () => {
    const { window } = loadApp();
    window.eval("state.me = { forename: 'Mia' };");
    const overviewBar = window.eval("header('overview')");
    const settingsBar = window.eval("header('settings')");
    const title = overviewBar.querySelector(".header-title-row .header-title");
    expect(title).not.toBeNull();
    expect(title.classList.contains("greeting-head")).toBe(true);
    expect(title.textContent).toContain("Mia");
    expect(overviewBar.querySelector(".header-back")).toBeNull();
    const settingsTitle = settingsBar.querySelector(".header-title-row .header-title");
    expect(settingsTitle.textContent).toBe(window.eval(`t("settings.title")`));
    expect(settingsBar.querySelector(".header-title-row .header-back")).not.toBeNull();
  });

  test("styles.css keeps .header-title single-line (truncates instead of wrapping at narrow widths)", () => {
    const css = fs.readFileSync(path.resolve(__dirname, "..", "styles.css"), "utf8");
    const match = /\.header-title\s*\{([^}]*)\}/.exec(css);
    expect(match).not.toBeNull();
    expect(match[1]).toMatch(/white-space:\s*nowrap/);
    expect(match[1]).toMatch(/text-overflow:\s*ellipsis/);
  });

  test("styles.css flips the header back chevron in RTL, like the existing subpage back button", () => {
    const css = fs.readFileSync(path.resolve(__dirname, "..", "styles.css"), "utf8");
    expect(css).toMatch(/\[dir="rtl"\]\s*\.header-back\s*\.ico\s*\{\s*transform:\s*scaleX\(-1\);?\s*\}/);
  });

  test("letterDetailView no longer pulls its meta line up with a negative top margin (it used to offset a title row that lived above it; that row moved into the sticky .header, so a negative margin now pulls the meta line under it)", () => {
    const { window } = loadApp();
    window.eval(
      "state.letterDetail = { letter: { letter_id: '1', recipient_id: '2', title: 'Infobrief', sender: 'Schule', published: '2026-08-31', child: 'Mia' }, detail: { body_html: '<p>x</p>', attachments: [] } };"
    );
    const view = window.eval("letterDetailView()");
    const meta = view.querySelector(".row-meta");
    expect(meta).not.toBeNull();
    expect(meta.getAttribute("style") || "").not.toMatch(/margin:\s*-/);
  });
});
