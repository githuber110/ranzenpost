import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function pinboardData() {
  return {
    folders: [
      { id: 10, title: "10 - Abschlussjahrgang" },
      { id: 1, title: "01 - Klasse 1a" },
      { id: 2, title: "02 - Klasse 2a" },
    ],
    feed: [
      { id: 2, title: "B", column_title: "", unread: false },
      { id: 1, title: "A", column_title: "", unread: false },
    ],
  };
}

describe("[P131] folder sheet: natural sort", () => {
  test("orders folders 01, 02, 10 instead of string order 01, 10, 02", () => {
    const { window } = loadApp();
    window.eval(`state.pinboard = ${JSON.stringify(pinboardData())};`);
    const view = window.eval("folderSheet()");
    const titles = Array.from(view.querySelectorAll(".opt-main b")).map((b) => b.textContent);
    expect(titles).toEqual(["Alle Ordner", "01 - Klasse 1a", "02 - Klasse 2a", "10 - Abschlussjahrgang"]);
  });

  test("does not affect the main feed's chronological order", () => {
    const { window } = loadApp();
    const data = pinboardData();
    window.eval(`state.pinboard = ${JSON.stringify(data)};`);
    window.eval("folderSheet()");
    const tiles = window.eval("pinboardTiles(state.pinboard, null, '')");
    expect(tiles.map((t) => t.id)).toEqual([2, 1]);
  });
});
