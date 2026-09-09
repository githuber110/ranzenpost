import { describe, expect, test } from "vitest";
import { loadApp } from "./loadApp.js";

const WITHHELD = {
  self_user_id: "",
  can_write_to_teacher: true,
  rooms: [],
  messages_unavailable: {
    message_key: "api.messenger.error.noCredentials",
    diagnosis: { stage: "no_credentials", status: 200 },
  },
};

const BROKEN = {
  self_user_id: "",
  can_write_to_teacher: true,
  rooms: [],
  messages_unavailable: {
    message_key: "api.messenger.error.network",
    diagnosis: { stage: "network", status: 502 },
  },
};

function seed(window, data) {
  window.eval(`
    state.config = {};
    state.children = [];
    state.messengerRooms = ${JSON.stringify(data)};
    state.view = "messenger";
  `);
  return window.eval("(function () { return messengerView(); })")();
}

function buttonLabels(view) {
  return Array.from(view.querySelectorAll(".empty .btn")).map((node) => node.textContent);
}

describe("[P228-A] the messenger stays usable while the messages are locked away", () => {
  test("a real failure names its reason instead of a room list that claims to be empty", () => {
    const { window } = loadApp();
    const view = seed(window, BROKEN);
    expect(view.textContent).toContain(window.eval("t('messenger.unavailable.title')"));
    expect(view.textContent).toContain(window.eval("t('api.messenger.error.network')"));
    expect(view.textContent).not.toContain(window.eval("t('messenger.empty.text')"));
  });

  test("the way to a teacher room is open in both states", () => {
    const { window } = loadApp();
    for (const data of [WITHHELD, BROKEN]) {
      const view = seed(window, data);
      expect(buttonLabels(view).join(" ")).toContain(window.eval("t('messenger.create.action')"));
    }
  });

  test("a real failure offers a retry of its own", () => {
    const { window } = loadApp();
    const view = seed(window, BROKEN);
    expect(buttonLabels(view).join(" ")).toContain(window.eval("t('common.retry')"));
  });

  test("the technical detail is there for whoever asks for it, in both states", () => {
    const { window } = loadApp();
    for (const data of [WITHHELD, BROKEN]) {
      const view = seed(window, data);
      expect(view.querySelector(".empty .tech-btn")).not.toBeNull();
    }
  });

  test("a healthy answer keeps the ordinary empty state", () => {
    const { window } = loadApp();
    const view = seed(window, { self_user_id: "@me:x", can_write_to_teacher: true, rooms: [] });
    expect(view.textContent).not.toContain(window.eval("t('messenger.unavailable.title')"));
    expect(view.textContent).toContain(window.eval("t('messenger.empty.text')"));
  });
});

describe("[P252] withheld messages are an empty state, not an error", () => {
  test("no retry, no warning icon, the calm title and the reason in plain words", () => {
    const { window } = loadApp();
    const view = seed(window, WITHHELD);
    const empty = view.querySelector(".empty");
    expect(empty).not.toBeNull();
    expect(empty.querySelector("b").textContent).toBe(window.eval("t('messenger.empty.title')"));
    expect(empty.querySelector("p").textContent).toBe(window.eval("t('messenger.empty.withheld')"));
    expect(buttonLabels(view).join(" ")).not.toContain(window.eval("t('common.retry')"));
    expect(view.textContent).not.toContain(window.eval("t('messenger.unavailable.title')"));
    expect(empty.querySelector(".ico-slot").innerHTML).toBe(window.eval("icon('messages', 40)").innerHTML);
  });

  test("the teacher room button is the only action left", () => {
    const { window } = loadApp();
    const view = seed(window, WITHHELD);
    expect(buttonLabels(view)).toEqual([window.eval("t('messenger.create.action')")]);
  });
});

describe("[P247] the buttons say which one is the point", () => {
  function buttons(window, data) {
    const view = seed(window, data);
    return Array.from(view.querySelectorAll(".empty .btn"));
  }

  test("writing to a teacher leads, retrying follows as the quiet one", () => {
    const { window } = loadApp();
    const found = buttons(window, BROKEN);
    expect(found.length).toBe(2);
    expect(found[0].textContent).toContain(window.eval("t('messenger.create.action')"));
    expect(found[0].className).not.toContain("ghost");
    expect(found[1].textContent).toContain(window.eval("t('common.retry')"));
    expect(found[1].className).toContain("ghost");
  });

  test("without the privilege the retry is the only and loudest button", () => {
    const { window } = loadApp();
    const found = buttons(window, Object.assign({}, BROKEN, { can_write_to_teacher: false }));
    expect(found.length).toBe(1);
    expect(found[0].textContent).toContain(window.eval("t('common.retry')"));
    expect(found[0].className).not.toContain("ghost");
  });
});
