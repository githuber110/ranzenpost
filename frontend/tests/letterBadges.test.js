import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

function renderLetterRow(window, letter, children) {
  const run = window.eval(
    "(function (letter, children) { if (children) state.children = children; return letterRow(letter); })"
  );
  return run(letter, children);
}

describe("[P99] letter list shows recipients + child badges", () => {
  test("row carries a Verteiler badge and a child badge (>1 child, C15 gate)", () => {
    const { window } = loadApp();
    const children = [{ child_id: "c1", name: "Mia" }, { child_id: "c2", name: "Leo" }];
    const letter = {
      letter_id: "1",
      recipient_id: "2",
      title: "Infobrief",
      child: "Mia",
      recipients: "Klasse 2B",
      unread: true,
    };
    const row = renderLetterRow(window, letter, children);
    const tags = row.querySelectorAll(".row-tags .tag");
    const texts = Array.from(tags).map((t) => t.textContent);
    expect(texts).toContain("Klasse 2B");
    expect(texts).toContain("Mia");
  });

  test("child badge hidden with exactly 1 child (C15 gate)", () => {
    const { window } = loadApp();
    const children = [{ child_id: "c1", name: "Mia" }];
    const letter = { letter_id: "1", recipient_id: "2", title: "Infobrief", child: "Mia", recipients: "Klasse 2B", unread: true };
    const row = renderLetterRow(window, letter, children);
    const tags = row.querySelectorAll(".row-tags .tag");
    const texts = Array.from(tags).map((t) => t.textContent);
    expect(texts).toContain("Klasse 2B");
    expect(texts).not.toContain("Mia");
  });

  test("no tags block when neither recipients nor child are known", () => {
    const { window } = loadApp();
    const letter = { letter_id: "1", recipient_id: "2", title: "Infobrief", unread: false };
    const row = renderLetterRow(window, letter);
    expect(row.querySelector(".row-tags")).toBeNull();
  });
});

describe("[P115] letter list shows a clip indicator for attachments", () => {
  test("clip indicator appears when the letter has attachments", () => {
    const { window } = loadApp();
    const letter = {
      letter_id: "1",
      recipient_id: "2",
      title: "Infobrief",
      unread: false,
      attachments: [{ filename: "einladung.pdf", url: "api/letters/attachment/x" }],
    };
    const row = renderLetterRow(window, letter);
    expect(row.querySelector(".row-clip")).not.toBeNull();
  });

  test("no clip indicator when the letter has no attachments", () => {
    const { window } = loadApp();
    const letter = { letter_id: "1", recipient_id: "2", title: "Infobrief", unread: false, attachments: [] };
    const row = renderLetterRow(window, letter);
    expect(row.querySelector(".row-clip")).toBeNull();
  });
});
