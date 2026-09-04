import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const SELF = "@me:example.test";
const TEACHER = "@teacher:example.test";
const OFFICE = "@office:example.test";

const ROOMS = {
  self_user_id: SELF,
  rooms: [
    {
      room_id: "!a:example.test",
      name: "Klasse 3b Elternchat",
      members: ["Fr. Behrend-Waldenburger", "Schulleitung"],
      member_names: { [TEACHER]: "Fr. Behrend-Waldenburger", [OFFICE]: "Schulleitung" },
      last_message: "Alles klar, ist notiert.",
      last_message_at: 1788336000000,
      unread_count: 3,
    },
    {
      room_id: "!b:example.test",
      name: "Sekretariat",
      members: ["Schulleitung"],
      member_names: { [OFFICE]: "Schulleitung" },
      last_message: "Guten Tag.",
      last_message_at: 1788249600000,
      unread_count: 0,
    },
  ],
};

const NEWEST_PAGE = [
  { event_id: "$3", sender: SELF, sent_at: 1788336300000, kind: "text", body: "Danke sehr." },
  { event_id: "$2", sender: TEACHER, sent_at: 1788336200000, kind: "text", body: "Der Ausflug startet um acht." },
  { event_id: "$1", sender: OFFICE, sent_at: 1788336100000, kind: "system", system_kind: "join" },
];

function setRooms(window, data) {
  window.eval("(function (data) { state.view = 'messenger'; state.messengerSearch = ''; state.messengerRooms = data; })")(data);
}

function renderRooms(window) {
  return window.eval("(function () { return messengerView(); })")();
}

function makeRoom(window, overrides) {
  return window.eval(
    `(function (over) {
      state.view = "messenger";
      state.messengerRooms = null;
      state.messengerRoom = Object.assign({
        room_id: "!a:example.test",
        name: "Klasse 3b Elternchat",
        memberNames: over && over.memberNames ? over.memberNames : {},
        selfUserId: "${SELF}",
        messages: [],
        before: "",
        loading: false,
        loadingOlder: false,
        error: "",
        draft: "",
        sending: false,
        atBottom: true,
        stickBottom: true,
        logScroll: null,
        restoreFromEnd: null,
      }, over || {});
      return state.messengerRoom;
    })`
  )(overrides);
}

function renderRoom(window) {
  return window.eval("(function () { return messengerRoomView(); })")();
}

function typeInto(window, input, value) {
  input.value = value;
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
}

function mockFetch(window, handler) {
  const calls = [];
  window.fetch = (url, options) => {
    const target = String(url);
    calls.push({ url: target, options });
    const outcome = handler(target, options);
    if (outcome === null) return Promise.reject(new Error("network"));
    return Promise.resolve({
      ok: true,
      headers: { get: () => "" },
      json: () => Promise.resolve(outcome),
    });
  };
  return calls;
}

function bodyOf(call) {
  return JSON.parse(call.options.body);
}

describe("[P198] messenger room list", () => {
  test("renders every room with preview, stamp and unread badge", () => {
    const { window } = loadApp();
    setRooms(window, ROOMS);
    const view = renderRooms(window);
    const rows = view.querySelectorAll(".rows .row");
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain("Klasse 3b Elternchat");
    expect(rows[0].textContent).toContain("Alles klar, ist notiert.");
    expect(rows[0].querySelector(".badge").textContent).toBe("3");
    expect(rows[0].querySelector(".row-meta").textContent).not.toBe("");
    expect(rows[1].className).toContain("read");
    expect(rows[1].querySelector(".badge")).toBe(null);
  });

  test("room names and previews keep their own reading direction", () => {
    const { window } = loadApp();
    setRooms(window, ROOMS);
    const row = renderRooms(window).querySelector(".rows .row");
    expect(row.querySelector(".row-title").getAttribute("dir")).toBe("auto");
    expect(row.querySelector(".row-sub").getAttribute("dir")).toBe("auto");
  });

  test("the filter narrows by name, by member and by preview, and clearing restores", () => {
    const { window } = loadApp();
    setRooms(window, ROOMS);
    const view = renderRooms(window);
    const input = view.querySelector(".search-input");

    typeInto(window, input, "SEKRETARIAT");
    expect(view.querySelectorAll(".rows .row").length).toBe(1);

    typeInto(window, input, "behrend");
    expect(view.querySelectorAll(".rows .row").length).toBe(1);
    expect(view.textContent).toContain("Klasse 3b Elternchat");

    typeInto(window, input, "notiert");
    expect(view.querySelectorAll(".rows .row").length).toBe(1);

    typeInto(window, input, "");
    expect(view.querySelectorAll(".rows .row").length).toBe(2);
  });

  test("a filter without a hit shows the search empty state instead of an empty list", () => {
    const { window } = loadApp();
    setRooms(window, ROOMS);
    const view = renderRooms(window);
    typeInto(window, view.querySelector(".search-input"), "zzzz");
    expect(view.querySelectorAll(".rows .row").length).toBe(0);
    expect(view.querySelector(".empty")).not.toBe(null);
  });

  test("no rooms at all shows a neutral empty state that promises nothing", () => {
    const { window } = loadApp();
    setRooms(window, { self_user_id: SELF, rooms: [] });
    const view = renderRooms(window);
    const empty = view.querySelector(".empty");
    expect(empty).not.toBe(null);
    expect(empty.textContent).toContain(window.eval("t('messenger.empty.title')"));
    expect(empty.textContent).toContain(window.eval("t('messenger.empty.text')"));
    expect(view.querySelector(".search-input")).toBe(null);
  });
});

describe("[P198] messenger room view", () => {
  test("shows the history oldest first and separates own from foreign posts", () => {
    const { window } = loadApp();
    const room = makeRoom(window, {
      messages: [
        { event_id: "$1", sender: OFFICE, sent_at: 1788336100000, kind: "text", body: "Erste Nachricht." },
        { event_id: "$2", sender: TEACHER, sent_at: 1788336200000, kind: "text", body: "Zweite Nachricht." },
        { event_id: "$3", sender: SELF, sent_at: 1788336300000, kind: "text", body: "Dritte Nachricht." },
      ],
      memberNames: { [TEACHER]: "Fr. Behrend-Waldenburger", [OFFICE]: "Schulleitung" },
    });
    expect(room.messages.length).toBe(3);
    const view = renderRoom(window);
    const bubbles = [...view.querySelectorAll(".chat-msg")];
    expect(bubbles.map((node) => node.querySelector(".chat-text").textContent)).toEqual([
      "Erste Nachricht.",
      "Zweite Nachricht.",
      "Dritte Nachricht.",
    ]);
    expect(bubbles[0].className).not.toContain("mine");
    expect(bubbles[2].className).toContain("mine");
    expect(bubbles[0].querySelector(".chat-from").textContent).toBe("Schulleitung");
    expect(bubbles[1].querySelector(".chat-from").textContent).toBe("Fr. Behrend-Waldenburger");
    expect(bubbles[2].querySelector(".chat-from")).toBe(null);
    expect(bubbles[0].querySelector(".chat-from").getAttribute("dir")).toBe("auto");
    expect(bubbles[0].querySelector(".chat-text").getAttribute("dir")).toBe("auto");
    expect(bubbles[0].querySelector(".chat-time").textContent).not.toBe("");
  });

  test("without a known own user id nothing is claimed as own", () => {
    const { window } = loadApp();
    makeRoom(window, {
      selfUserId: "",
      messages: [{ event_id: "$1", sender: SELF, sent_at: 1788336100000, kind: "text", body: "Hallo." }],
    });
    expect(renderRoom(window).querySelector(".chat-msg").className).not.toContain("mine");
  });

  test("system events render as a quiet line, not as a bubble", () => {
    const { window } = loadApp();
    makeRoom(window, {
      messages: [
        { event_id: "$1", sender: OFFICE, sent_at: 1788336100000, kind: "system", system_kind: "join" },
        { event_id: "$2", sender: OFFICE, sent_at: 1788336200000, kind: "system", system_kind: "quirk" },
      ],
    });
    const view = renderRoom(window);
    const lines = [...view.querySelectorAll(".chat-system")];
    expect(lines.length).toBe(2);
    expect(view.querySelectorAll(".chat-msg").length).toBe(0);
    expect(lines[0].textContent).toBe(window.eval("t('messenger.system.join')"));
    expect(lines[1].textContent).toBe(window.eval("t('messenger.system.change')"));
  });

  test("a day change inserts exactly one separator", () => {
    const { window } = loadApp();
    makeRoom(window, {
      messages: [
        { event_id: "$1", sender: TEACHER, sent_at: 1788249600000, kind: "text", body: "Gestern." },
        { event_id: "$2", sender: TEACHER, sent_at: 1788336100000, kind: "text", body: "Heute." },
        { event_id: "$3", sender: TEACHER, sent_at: 1788336200000, kind: "text", body: "Auch heute." },
      ],
    });
    expect(renderRoom(window).querySelectorAll(".chat-day").length).toBe(2);
  });

  test("an empty room says so instead of showing a blank log", () => {
    const { window } = loadApp();
    makeRoom(window, { messages: [] });
    expect(renderRoom(window).querySelector(".chat-log .empty")).not.toBe(null);
  });

  test("a file post reuses the attachment row that opens through the app", () => {
    const { window } = loadApp();
    makeRoom(window, {
      messages: [
        {
          event_id: "$1",
          sender: OFFICE,
          sent_at: 1788336100000,
          kind: "file",
          body: "protokoll.txt",
          media_url: "api/messenger/media/srv/file-1",
        },
      ],
    });
    const row = renderRoom(window).querySelector(".chat-msg .rows .row");
    expect(row).not.toBe(null);
    expect(row.textContent).toContain("protokoll.txt");
  });
});

describe("[P198] messenger paging", () => {
  test("the newest page arrives newest first and is turned around for the screen", () => {
    const { window } = loadApp();
    const room = makeRoom(window, {});
    window.eval("(function (room, data) { applyMessengerHistory(room, data, false); })")(room, {
      messages: NEWEST_PAGE,
      before: "page-2",
      self_user_id: SELF,
    });
    expect(room.messages.map((entry) => entry.event_id)).toEqual(["$1", "$2", "$3"]);
    expect(room.before).toBe("page-2");
  });

  test("an older page is prepended and never replaces what is already shown", () => {
    const { window } = loadApp();
    const room = makeRoom(window, {
      messages: [{ event_id: "$2", sender: TEACHER, sent_at: 2, kind: "text", body: "Neuer." }],
      before: "page-2",
    });
    window.eval("(function (room, data) { applyMessengerHistory(room, data, true); })")(room, {
      messages: [{ event_id: "$1", sender: TEACHER, sent_at: 1, kind: "text", body: "Aelter." }],
      before: "",
      self_user_id: SELF,
    });
    expect(room.messages.map((entry) => entry.event_id)).toEqual(["$1", "$2"]);
    expect(room.before).toBe("");
  });

  test("a refresh keeps already loaded older posts and adds only what is new", () => {
    const { window } = loadApp();
    const room = makeRoom(window, {
      messages: [
        { event_id: "$0", sender: TEACHER, sent_at: 0, kind: "text", body: "Ganz alt." },
        { event_id: "$1", sender: OFFICE, sent_at: 1, kind: "text", body: "Alt." },
      ],
      before: "page-2",
    });
    window.eval("(function (room, data) { applyMessengerHistory(room, data, false); })")(room, {
      messages: [
        { event_id: "$2", sender: TEACHER, sent_at: 2, kind: "text", body: "Neu." },
        { event_id: "$1", sender: OFFICE, sent_at: 1, kind: "text", body: "Alt." },
      ],
      before: "page-9",
      self_user_id: SELF,
    });
    expect(room.messages.map((entry) => entry.event_id)).toEqual(["$0", "$1", "$2"]);
    expect(room.before).toBe("page-2");
  });

  test("loading older asks the backend with the before token of the room", async () => {
    const { window } = loadApp();
    const room = makeRoom(window, {
      messages: [{ event_id: "$2", sender: TEACHER, sent_at: 2, kind: "text", body: "Neuer." }],
      before: "page-2",
    });
    const calls = mockFetch(window, () => ({
      messages: [{ event_id: "$1", sender: TEACHER, sent_at: 1, kind: "text", body: "Aelter." }],
      before: "",
      self_user_id: SELF,
    }));
    await window.eval("(function () { return loadMessengerHistory({ older: true }); })")();
    const history = calls.filter((call) => call.url.includes("api/messenger/room?id="));
    expect(history.length).toBe(1);
    expect(history[0].url).toContain("before=page-2");
    expect(room.messages.map((entry) => entry.event_id)).toEqual(["$1", "$2"]);
  });
});

describe("[P198] sending", () => {
  test("a click sends once, clears the box and reloads the history", async () => {
    const { window } = loadApp();
    const room = makeRoom(window, { messages: [] });
    const calls = mockFetch(window, (url) => {
      if (url.includes("api/messenger/send")) return { ok: true, message_key: "api.messenger.send.ok" };
      return { messages: [], before: "", self_user_id: SELF };
    });
    const view = renderRoom(window);
    typeInto(window, view.querySelector(".composer-input"), "  Guten Tag  ");
    expect(room.draft).toBe("  Guten Tag  ");
    await window.eval("(function (node) { return sendMessengerMessage(node); })")(view.querySelector(".composer-input"));
    const sends = calls.filter((call) => call.url.includes("api/messenger/send"));
    expect(sends.length).toBe(1);
    expect(bodyOf(sends[0])).toEqual({ room_id: "!a:example.test", text: "Guten Tag" });
    expect(room.draft).toBe("");
    expect(room.sending).toBe(false);
    expect(calls.some((call) => call.url.includes("api/messenger/room?id="))).toBe(true);
  });

  test("a rejected send keeps the typed text and says why", async () => {
    const { window } = loadApp();
    const room = makeRoom(window, { messages: [] });
    mockFetch(window, () => ({ ok: false, message_key: "api.messenger.send.failed" }));
    const view = renderRoom(window);
    const input = view.querySelector(".composer-input");
    typeInto(window, input, "Bitte weiterleiten");
    await window.eval("(function (node) { return sendMessengerMessage(node); })")(input);
    expect(room.draft).toBe("Bitte weiterleiten");
    expect(room.sending).toBe(false);
    const toast = window.eval("state.toast");
    expect(toast.kind).toBe("bad");
    expect(toast.message).toBe(window.eval("t('api.messenger.send.failed')"));
    expect(renderRoom(window).querySelector(".composer-input").value).toBe("Bitte weiterleiten");
  });

  test("an empty box never reaches the network and says the message is empty", async () => {
    const { window } = loadApp();
    makeRoom(window, { messages: [] });
    const calls = mockFetch(window, () => ({ ok: true }));
    const view = renderRoom(window);
    const input = view.querySelector(".composer-input");
    typeInto(window, input, "   ");
    await window.eval("(function (node) { return sendMessengerMessage(node); })")(input);
    expect(calls.filter((call) => call.url.includes("api/messenger/"))).toEqual([]);
    expect(window.eval("state.toast").message).toBe(window.eval("t('api.messenger.send.empty')"));
  });

  test("while a send is in flight the button is blocked against a second click", async () => {
    const { window } = loadApp();
    makeRoom(window, { messages: [], sending: true, draft: "Noch unterwegs" });
    const view = renderRoom(window);
    expect(view.querySelector(".composer-send").disabled).toBe(true);
    expect(view.querySelector(".composer-send .spin")).not.toBe(null);
    const calls = mockFetch(window, () => ({ ok: true }));
    await window.eval("(function (node) { return sendMessengerMessage(node); })")(view.querySelector(".composer-input"));
    expect(calls.filter((call) => call.url.includes("api/messenger/"))).toEqual([]);
  });
});

describe("[P198] image posts open the existing viewer", () => {
  test("tapping the thumbnail loads the media proxy and opens the overlay", async () => {
    const { window } = loadApp();
    makeRoom(window, {
      messages: [
        {
          event_id: "$1",
          sender: TEACHER,
          sent_at: 1788336100000,
          kind: "image",
          body: "gruppenfoto.jpg",
          media_url: "api/messenger/media/srv/image-1",
        },
      ],
    });
    window.URL.createObjectURL = () => "blob:messenger-test";
    window.URL.revokeObjectURL = () => {};
    const seen = [];
    window.fetch = (url) => {
      seen.push(String(url));
      return Promise.resolve({
        ok: true,
        headers: { get: () => "" },
        blob: () => Promise.resolve(new window.Blob(["x"], { type: "image/jpeg" })),
      });
    };
    const view = renderRoom(window);
    const thumb = view.querySelector(".chat-image");
    expect(thumb.querySelector(".chat-thumb").getAttribute("src")).toContain("api/messenger/media/srv/image-1");
    thumb.dispatchEvent(new window.Event("click", { bubbles: true }));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(seen.some((url) => url.includes("api/messenger/media/srv/image-1"))).toBe(true);
    const viewer = window.eval("state.fileViewer");
    expect(viewer.kind).toBe("image");
    expect(viewer.filename).toBe("gruppenfoto.jpg");
    expect(window.eval("(function () { return fileViewerNode(); })")().querySelector(".viewer-img")).not.toBe(null);
  });
});

describe("[P198] the way in", () => {
  test("the chat is a tab of its own and the header carries no entry any more", () => {
    const { window } = loadApp();
    const keys = window.eval("VIEWS.map((item) => item.key)");
    expect(keys).toContain("messenger");
    expect(keys).not.toContain("letters");
    expect(keys).not.toContain("pinboard");
    expect(window.eval("typeof messengerEntryButton")).toBe("undefined");
    expect(window.eval("typeof openMessenger")).toBe("undefined");
  });

  test("before the rooms are loaded the tab badge comes from the poller state", () => {
    const { window } = loadApp();
    const total = window.eval(
      "(function (poll) { state.messengerRooms = null; state.config = { poll_state: poll }; return badgeCount('messenger'); })"
    );
    expect(total({ messenger_unread: 4 })).toBe(4);
    expect(total({ messenger_unread: 0 })).toBe(0);
    expect(total({})).toBe(0);
  });

  test("the loaded rooms beat the poller state for the tab badge", () => {
    const { window } = loadApp();
    setRooms(window, ROOMS);
    window.eval("(function () { state.config = { poll_state: { messenger_unread: 99 } }; })")();
    expect(window.eval("badgeCount('messenger')")).toBe(3);
  });

  test("entering the chat tab drops any open room", () => {
    const { window } = loadApp();
    window.eval(`
      state.config = {};
      state.children = [];
      state.absence = { data: { children: [], rules: {} } };
      state.view = "overview";
      state.messengerRoom = { room_id: "!a:example.test", messages: [] };
      setView("messenger");
    `);
    expect(window.eval("state.view")).toBe("messenger");
    expect(window.eval("state.messengerRoom")).toBe(null);
  });
});
