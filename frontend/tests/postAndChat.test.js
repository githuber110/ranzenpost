import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const SELF = "@me:example.test";
const TEACHER = "@teacher:example.test";

const LETTERS = {
  tab: "current",
  letters: [
    { letter_id: "1", recipient_id: "2", title: "Sportfest", unread: true },
    { letter_id: "3", recipient_id: "4", title: "Ausflug", unread: false },
  ],
};

const PINBOARD = {
  folders: [],
  feed: [
    { id: 1, title: "Sommerfest", text: "Text", unread: true },
    { id: 2, title: "Kuchen", text: "Text", unread: true },
    { id: 3, title: "Alt", text: "Text", unread: false },
  ],
};

const ROOMS = {
  self_user_id: SELF,
  can_write_to_teacher: true,
  rooms: [
    {
      room_id: "!a:example.test",
      name: "Klasse 3b",
      members: ["Fr. Behrend"],
      member_names: { [TEACHER]: "Fr. Behrend" },
      last_message: "Bis morgen.",
      last_message_at: 1788336000000,
      unread_count: 2,
    },
    {
      room_id: "!b:example.test",
      name: "Sekretariat",
      members: ["Schulleitung"],
      member_names: {},
      last_message: "Guten Tag.",
      last_message_at: 1788249600000,
      unread_count: 0,
    },
  ],
};

function seed(window, extra) {
  window.eval(`
    state.config = {};
    state.children = [{ child_id: "c1", name: "Mia", class_name: "3b" }];
    state.absence = { data: { children: [], rules: {} } };
    state.letters = ${JSON.stringify(LETTERS)};
    state.pinboard = ${JSON.stringify(PINBOARD)};
    state.messengerRooms = ${JSON.stringify(ROOMS)};
    ${extra || ""}
  `);
}

function tabs(window) {
  const bar = window.eval("(function () { return tabbar(); })")();
  return Array.from(bar.querySelectorAll(".tab")).map((tab) => ({
    label: tab.querySelector("span:not(.ico-slot):not(.badge)").textContent,
    badge: tab.querySelector(".badge") ? tab.querySelector(".badge").textContent : "",
    aria: tab.getAttribute("aria-label"),
  }));
}

describe("[P198] the tab bar after the Post merge", () => {
  test("five tabs in the decided order, letters and pinboard folded into Post", () => {
    const { window } = loadApp();
    seed(window);
    const labels = tabs(window).map((tab) => tab.label);
    expect(labels).toEqual([
      window.eval("t('nav.overview')"),
      window.eval("t('nav.timetable')"),
      window.eval("t('nav.absence')"),
      window.eval("t('nav.post')"),
      window.eval("t('nav.messenger')"),
    ]);
  });

  test("the column count follows the number of tabs, so four tabs do not leave a hole", () => {
    const { window } = loadApp();
    seed(window);
    const wide = window.eval("(function () { state.timetableAvailable = true; return tabbar(); })")();
    expect(wide.style.getPropertyValue("--tabs")).toBe("5");
    expect(wide.querySelectorAll(".tab").length).toBe(5);
    const narrow = window.eval("(function () { state.timetableAvailable = false; return tabbar(); })")();
    expect(narrow.style.getPropertyValue("--tabs")).toBe("4");
    expect(narrow.querySelectorAll(".tab").length).toBe(4);
  });
});

describe("[P198] every badge path", () => {
  test("the Post tab carries the sum of unread letters and unread posts", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval("lettersUnreadCount()")).toBe(1);
    expect(window.eval("pinboardUnreadCount()")).toBe(2);
    expect(window.eval("badgeCount('post')")).toBe(3);
  });

  test("the segment keeps the two counts apart", () => {
    const { window } = loadApp();
    seed(window);
    const segment = window.eval("(function () { return postSegment(); })")();
    const buttons = segment.querySelectorAll("button");
    expect(buttons.length).toBe(2);
    expect(buttons[0].querySelector(".seg-badge").textContent).toBe("1");
    expect(buttons[1].querySelector(".seg-badge").textContent).toBe("2");
  });

  test("a badge speaks its number through the label, never through the badge node", () => {
    const { window } = loadApp();
    seed(window);
    const post = tabs(window)[3];
    expect(post.badge).toBe("3");
    expect(post.aria).toContain("3");
    const bar = window.eval("(function () { return tabbar(); })")();
    expect(bar.querySelector(".badge").getAttribute("aria-hidden")).toBe("true");
    const segment = window.eval("(function () { return postSegment(); })")();
    expect(segment.querySelectorAll("button")[0].getAttribute("aria-label")).toContain("1");
  });

  test("the letter count survives a trip into the archive folder", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval("badgeCount('post')")).toBe(3);
    window.eval("(function () { setLettersFolder('archive'); state.letters = { tab: 'archive', letters: [] }; })")();
    expect(window.eval("badgeCount('post')")).toBe(3);
    window.eval("(function () { setLettersFolder('current'); })")();
  });

  test("reading a letter lets the Post badge sink at once", () => {
    const { window } = loadApp();
    seed(window);
    window.eval("(function () { state.letters.letters[0].unread = false; })")();
    expect(window.eval("badgeCount('post')")).toBe(2);
  });

  test("reading a post lets the Post badge sink at once", () => {
    const { window } = loadApp();
    seed(window);
    window.eval("(function () { state.pinboard.feed[0].unread = false; })")();
    expect(window.eval("badgeCount('post')")).toBe(2);
  });

  test("an open read confirmation keeps a read letter in the Post count", () => {
    const { window } = loadApp();
    seed(window);
    window.eval(
      "(function () { state.letters.letters[1].confirmation = { type: 'seen', open: true }; })"
    )();
    expect(window.eval("badgeCount('post')")).toBe(4);
  });

  test("the Chat tab counts the unread rooms and drops back to nothing when they are read", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval("badgeCount('messenger')")).toBe(2);
    window.eval("(function () { state.messengerRooms.rooms[0].unread_count = 0; })")();
    expect(window.eval("badgeCount('messenger')")).toBe(0);
  });

  test("a failed room load shows no badge instead of a wrong number", () => {
    const { window } = loadApp();
    seed(window, "state.messengerRooms = { error: 'network' }; state.config = { poll_state: {} };");
    expect(window.eval("badgeCount('messenger')")).toBe(0);
  });
});

describe("[P198] the Post screen", () => {
  test("the segment switches the body between letters and pinboard", () => {
    const { window } = loadApp();
    seed(window);
    window.eval("(function () { state.view = 'post'; state.postTab = 'letters'; })")();
    const letters = window.eval("(function () { return postView(); })")();
    expect(letters.textContent).toContain("Sportfest");
    window.eval("(function () { state.postTab = 'pinboard'; })")();
    const pinboard = window.eval("(function () { return postView(); })")();
    expect(pinboard.textContent).toContain("Sommerfest");
  });

  test("[P221] inbox and archive stand side by side as chips, no intermediate sheet", () => {
    const { window } = loadApp();
    seed(window);
    window.eval("(function () { state.view = 'post'; state.postTab = 'letters'; })")();
    const view = window.eval("(function () { return postView(); })")();
    expect(view.querySelectorAll(".list-head .segment").length).toBe(1);
    const chips = [...view.querySelectorAll(".list-head .chipbar .chip")];
    expect(chips.length).toBe(2);
    expect(chips[0].textContent).toContain(window.eval("t('letters.folder.current')"));
    expect(chips[1].textContent).toContain(window.eval("t('letters.folder.archive')"));
    expect(chips[0].getAttribute("role")).toBe("tab");
    expect(chips[0].getAttribute("aria-selected")).toBe("true");
    expect(chips[1].getAttribute("aria-selected")).toBe("false");
  });

  test("[P221] one tap on the archive chip switches straight over", () => {
    const { window } = loadApp();
    seed(window);
    window.eval("(function () { state.view = 'post'; state.postTab = 'letters'; render(); })")();
    const chips = [...window.document.querySelectorAll(".list-head .chipbar .chip")];
    chips[1].click();
    expect(window.eval("state.lettersTab")).toBe("archive");
    expect(window.eval("state.letters")).toBe(null);
    const after = [...window.document.querySelectorAll(".list-head .chipbar .chip")];
    expect(after[1].getAttribute("aria-selected")).toBe("true");
  });

  test("[P220] the post tab always comes back on the letters segment", () => {
    const { window } = loadApp();
    seed(window);
    window.eval(`
      state.view = "post";
      state.postTab = "pinboard";
      setView("overview");
      setView("post");
    `);
    expect(window.eval("state.postTab")).toBe("letters");
  });
});

describe("[P222] the pinboard filter chip names the folder it filters by", () => {
  function pinboardHead(window, folderId) {
    return window.eval(`
      (function (folderId) {
        state.view = "post";
        state.postTab = "pinboard";
        state.pinboardFolder = folderId;
        state.pinboard = {
          feed: [],
          folders: [
            { id: "f1", title: "Elternbriefe der ganzen Schule und aller Klassen" },
            { id: "f2", title: "Kurz" },
          ],
        };
        return pinboardView(null);
      })
    `)(folderId);
  }

  test("without a folder the chip reads 'all folders' and wears the filter icon", () => {
    const { window } = loadApp();
    const view = pinboardHead(window, null);
    const chip = view.querySelector(".chipbar .chip-filter");
    expect(chip).not.toBeNull();
    expect(chip.textContent).toContain(window.eval("t('pinboard.folder.all')"));
    const drawn = chip.querySelector("svg path").getAttribute("d");
    expect(window.eval("ICON_SHAPES.filter")).toContain(drawn);
    expect(window.eval("ICON_SHAPES.folder")).not.toContain(drawn);
  });

  test("a chosen folder replaces the label with its own name", () => {
    const { window } = loadApp();
    const view = pinboardHead(window, "f2");
    const chip = view.querySelector(".chipbar .chip-filter");
    expect(chip.textContent).toContain("Kurz");
    expect(chip.textContent).not.toContain(window.eval("t('pinboard.folder.all')"));
  });

  test("a long folder name reaches the clipping label whole, never shortened in javascript", () => {
    const { window } = loadApp();
    const view = pinboardHead(window, "f1");
    const label = view.querySelector(".chipbar .chip-filter .chip-label");
    expect(label).not.toBeNull();
    expect(label.getAttribute("dir")).toBe("auto");
    expect(label.textContent).toBe("Elternbriefe der ganzen Schule und aller Klassen");
    expect(label.textContent).not.toContain("…");
  });
});

describe("[P198] the overview knows about Post and Chat", () => {
  test("a letters row opens the letter in place, a pinboard row opens its post sheet", () => {
    const { window } = loadApp();
    seed(window);
    window.eval("(function () { state.view = 'overview'; })")();
    const letters = window.eval("(function () { return lettersChapter().blocks[0].node; })")();
    letters.click();
    expect(window.eval("state.view")).toBe("post");
    expect(window.eval("state.postTab")).toBe("letters");
    expect(window.eval("state.letterDetail.letter.letter_id")).toBe("1");
    window.eval("(function () { state.view = 'overview'; state.letterDetail = null; })")();
    const pinboard = window.eval("(function () { return pinboardChapter().blocks[0].node; })")();
    pinboard.click();
    expect(window.eval("state.view")).toBe("overview");
    expect(window.eval("typeof state.sheet")).toBe("function");
  });

  test("the chat chapter appears only while something is unread", () => {
    const { window } = loadApp();
    seed(window);
    expect(window.eval("overviewChapters().map((c) => c.area)")).toEqual([
      "today",
      "letters",
      "pinboard",
      "messenger",
    ]);
    window.eval("(function () { state.messengerRooms.rooms[0].unread_count = 0; })")();
    expect(window.eval("overviewChapters().map((c) => c.area)")).toEqual([
      "today",
      "letters",
      "pinboard",
    ]);
  });

  test("a chat row names the room and jumps straight into it", () => {
    const { window } = loadApp();
    seed(window);
    const chapter = window.eval("(function () { return messengerChapter(); })")();
    expect(chapter.blocks.length).toBe(2);
    expect(chapter.blocks[0].node.textContent).toContain("Klasse 3b");
    expect(chapter.blocks[0].node.textContent).toContain(
      window.eval("tCount('overview.messenger.count', 2)")
    );
    window.eval("(function (node) { window.__row = node; })")(chapter.blocks[0].node);
    window.eval("window.__row.click()");
    expect(window.eval("state.view")).toBe("messenger");
    expect(window.eval("state.messengerRoom.room_id")).toBe("!a:example.test");
  });
});

describe("[P198] the deliberate read marker", () => {
  function openRoom(window) {
    seed(window);
    window.eval("(function () { setView('messenger'); openMessengerRoom(state.messengerRooms.rooms[0]); })")();
    window.eval(
      "(function () { state.messengerRoom.messages = [{ event_id: '$one', sender: '@t:x', sent_at: 1, kind: 'text', body: 'hi' }, { event_id: '$two', sender: '@t:x', sent_at: 2, kind: 'text', body: 'ho' }]; })"
    )();
  }

  test("the button shows up only in a room that has something unread", () => {
    const { window } = loadApp();
    openRoom(window);
    expect(window.eval("(function () { return header('messenger'); })")().querySelector(".messenger-read")).not.toBeNull();
    window.eval("(function () { state.messengerRoom.unread = 0; })")();
    expect(window.eval("(function () { return header('messenger'); })")().querySelector(".messenger-read")).toBeNull();
  });

  test("the marker names the newest event and only one request leaves the app", async () => {
    const { window } = loadApp();
    openRoom(window);
    const sent = [];
    window.fetch = (input, init) => {
      sent.push({ url: String(input), body: JSON.parse(init.body) });
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ ok: true, message_key: "api.messenger.read.ok" }),
      });
    };
    const button = window.eval("(function () { return header('messenger'); })")().querySelector(".messenger-read");
    button.click();
    button.click();
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    const reads = sent.filter((call) => call.url.includes("api/messenger/read"));
    expect(reads.length).toBe(1);
    expect(reads[0].body).toEqual({ room_id: "!a:example.test", event_id: "$two" });
  });

  test("a room without a single event offers nothing to mark", () => {
    const { window } = loadApp();
    openRoom(window);
    window.eval("(function () { state.messengerRoom.messages = []; })")();
    const button = window.eval("(function () { return header('messenger'); })")().querySelector(".messenger-read");
    expect(button.disabled).toBe(true);
  });
});
