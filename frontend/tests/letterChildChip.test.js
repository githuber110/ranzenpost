import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const LETTERS = [
  { letter_id: "1", recipient_id: "1", title: "Klassenfahrt", child: "Nena Beispiel", recipients: "Klasse 3b", sender: "Sekretariat", published: "01.09.2026", unread: true, confirmation: { open: true } },
  { letter_id: "2", recipient_id: "2", title: "Elternabend", child: "Beispiel, Toko", recipients: "Klasse 5a", sender: "Sekretariat", published: "02.09.2026", unread: false },
];

function lettersList(window, children) {
  const run = window.eval(`
    (function (letters, kids) {
      state.view = "post";
      state.postTab = "letters";
      state.lettersTab = "current";
      state.children = kids;
      state.childId = kids.length ? kids[0].child_id : "";
      state.letters = { tab: "current", letters: letters };
      return lettersView(null);
    })
  `);
  return run(LETTERS, children);
}

function detail(window, letter) {
  const run = window.eval(`
    (function (letter) {
      state.view = "post";
      state.letterDetail = { letter: letter, detail: { body_html: "<p>Text</p>", attachments: [] }, loading: false, error: "" };
      return letterDetailView();
    })
  `);
  return run(letter);
}

function tagTexts(node) {
  return [...node.querySelectorAll(".row-tags .tag")].map((t) => t.textContent.trim());
}

describe("[P234] every letter says which child it is about", () => {
  test("the list shows the child's first name as a chip beside the class", () => {
    const { window } = loadApp();
    const view = lettersList(window, [{ child_id: "c1", name: "Nena Beispiel", class_name: "3b" }]);
    const rows = [...view.querySelectorAll(".rows .row")];
    expect(rows.length).toBe(2);
    expect(tagTexts(rows[0])).toContain("Nena");
    expect(tagTexts(rows[0])).toContain("Klasse 3b");
  });

  test("a single-child household sees it too", () => {
    const { window } = loadApp();
    const view = lettersList(window, [{ child_id: "c1", name: "Nena Beispiel", class_name: "3b" }]);
    const first = view.querySelector(".rows .row");
    expect(tagTexts(first)).toContain("Nena");
  });

  test("only the first name is shown, never the surname", () => {
    const { window } = loadApp();
    const view = lettersList(window, [{ child_id: "c1", name: "Nena Beispiel", class_name: "3b" }]);
    const texts = [...view.querySelectorAll(".row-tags .tag")].map((t) => t.textContent);
    expect(texts.join(" ")).not.toContain("Beispiel");
  });

  test("a surname-first spelling still yields the given name", () => {
    const { window } = loadApp();
    const view = lettersList(window, [{ child_id: "c1", name: "Nena Beispiel", class_name: "3b" }]);
    const rows = [...view.querySelectorAll(".rows .row")];
    expect(tagTexts(rows[1])).toContain("Toko");
    expect(tagTexts(rows[1]).join(" ")).not.toContain("Beispiel");
  });

  test("the detail view carries the same chip instead of burying it in the meta line", () => {
    const { window } = loadApp();
    const view = detail(window, LETTERS[0]);
    expect(tagTexts(view)).toContain("Nena");
    expect(tagTexts(view)).toContain("Klasse 3b");
    const meta = view.querySelector(".row-meta");
    expect(meta.textContent).not.toContain("Nena");
    expect(meta.textContent).toContain("Sekretariat");
  });

  test("a letter without a child simply carries no child chip", () => {
    const { window } = loadApp();
    const view = detail(window, { ...LETTERS[0], child: "" });
    expect(tagTexts(view)).not.toContain("Nena");
    expect(tagTexts(view)).toContain("Klasse 3b");
  });
});

describe("[P234] the overview says which child a new letter is about", () => {
  test("an unread letter in the overview carries the child chip", () => {
    const { window } = loadApp();
    const html = window.eval(`
      (function (letters) {
        state.children = [{ child_id: "c1", name: "Nena Beispiel", class_name: "3b" }];
        state.childId = "c1";
        state.letters = { tab: "current", letters: letters };
        const chapter = lettersChapter();
        return chapter.blocks.map(function (b) { return b.node ? b.node.outerHTML : String(b.key); }).join("");
      })
    `)(LETTERS);
    expect(html).toContain("tag child");
    expect(html).toContain("Nena");
    expect(html).not.toContain("Beispiel");
  });

  test("the overview row builder renders the chip when one is passed", () => {
    const { window } = loadApp();
    const row = window.eval(`
      (function () {
        const tag = letterChildTag({ child: "Nena Beispiel" });
        return overviewListRow("Titel", "Absender", "01.09.", true, function () {}, [tag]).outerHTML;
      })
    `)();
    expect(row).toContain("row-tags");
    expect(row).toContain("tag child");
    expect(row).toContain("Nena");
    expect(row).not.toContain("Beispiel");
  });

  test("overview rows without a child stay exactly as they were", () => {
    const { window } = loadApp();
    const row = window.eval(`
      (function () {
        return overviewListRow("Titel", "Absender", "01.09.", true, function () {}, []).outerHTML;
      })
    `)();
    expect(row).not.toContain("row-tags");
    expect(row).toContain("Titel");
  });
});

describe("[P234] the overview letter row carries the same facts as the list", () => {
  test("class, child and the pending-confirmation badge all appear in the overview", () => {
    const { window } = loadApp();
    const html = window.eval(`
      (function (letters) {
        state.children = [{ child_id: "c1", name: "Nena Beispiel", class_name: "3b" }];
        state.childId = "c1";
        state.letters = { tab: "current", letters: letters };
        const chapter = lettersChapter();
        return chapter.blocks.map(function (b) { return b.node ? b.node.outerHTML : ""; }).join("");
      })
    `)(LETTERS);
    expect(html).toContain("Klasse 3b");
    expect(html).toContain("Nena");
    expect(html).toContain(window.eval('t("letters.confirm.badge")'));
  });

  test("the list and the overview build their chips from one source", () => {
    const { window } = loadApp();
    const same = window.eval(`
      (function (letter) {
        const nodes = letterTagNodes(letter);
        return nodes.map(function (n) { return n.textContent.trim(); }).join("|");
      })
    `)(LETTERS[0]);
    expect(same).toContain("Klasse 3b");
    expect(same).toContain("Nena");
  });
});
