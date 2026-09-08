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

function seed(window, data) {
  window.eval(`
    state.config = {};
    state.children = [];
    state.messengerRooms = ${JSON.stringify(data)};
    state.view = "messenger";
  `);
  return window.eval("(function () { return messengerView(); })")();
}

describe("[P228-A] the messenger stays usable while the messages are locked away", () => {
  test("the reason is on the screen instead of a room list that claims to be empty", () => {
    const { window } = loadApp();
    const view = seed(window, WITHHELD);
    expect(view.textContent).toContain(window.eval("t('messenger.unavailable.title')"));
    expect(view.textContent).toContain(window.eval("t('api.messenger.error.noCredentials')"));
    expect(view.textContent).not.toContain(window.eval("t('messenger.empty.text')"));
  });

  test("the way to a teacher room is still open", () => {
    const { window } = loadApp();
    const view = seed(window, WITHHELD);
    const labels = Array.from(view.querySelectorAll(".empty .btn")).map((node) => node.textContent);
    expect(labels.join(" ")).toContain(window.eval("t('messenger.create.action')"));
  });

  test("this state offers a retry of its own", () => {
    const { window } = loadApp();
    const view = seed(window, WITHHELD);
    const labels = Array.from(view.querySelectorAll(".empty .btn")).map((node) => node.textContent);
    expect(labels.join(" ")).toContain(window.eval("t('common.retry')"));
  });

  test("the technical detail is there for whoever asks for it", () => {
    const { window } = loadApp();
    const view = seed(window, WITHHELD);
    expect(view.querySelector(".empty .tech-btn")).not.toBeNull();
  });

  test("a healthy answer keeps the ordinary empty state", () => {
    const { window } = loadApp();
    const view = seed(window, { self_user_id: "@me:x", can_write_to_teacher: true, rooms: [] });
    expect(view.textContent).not.toContain(window.eval("t('messenger.unavailable.title')"));
    expect(view.textContent).toContain(window.eval("t('messenger.empty.text')"));
  });
});
