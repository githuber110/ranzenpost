import { describe, expect, test, vi } from "vitest";
import { loadApp } from "./loadApp.js";

const TEACHER_A = { value: "userid:11111111-2222-3333-4444-555555555555", label: "Hr. Osterkamp", extra: "" };
const TEACHER_B = { value: "userid:66666666-7777-8888-9999-000000000000", label: "Fr. Behrend", extra: "" };

const ROOMS = {
  self_user_id: "@me:example.test",
  can_write_to_teacher: true,
  rooms: [
    {
      room_id: "!b:example.test",
      name: "Fr. Behrend",
      members: ["Fr. Behrend"],
      member_names: {},
      last_message: "Guten Tag.",
      last_message_at: 1788249600000,
      unread_count: 0,
    },
  ],
};

function seed(window, children, rooms) {
  window.eval(`
    state.config = {};
    state.absence = { data: { children: [], rules: {} } };
    state.children = ${JSON.stringify(children)};
    state.messengerRooms = ${JSON.stringify(rooms === undefined ? ROOMS : rooms)};
    state.view = "messenger";
  `);
}

const ONE_CHILD = [{ child_id: "c1", name: "Mia", class_name: "3b" }];
const TWO_CHILDREN = [
  { child_id: "c1", name: "Mia", class_name: "3b" },
  { child_id: "c2", name: "Tom", class_name: "1a" },
];

function flow(window) {
  return {
    node: window.eval("teacherRoomFlow.node"),
    step: window.eval("teacherRoomFlow.current()"),
    path: window.eval("teacherRoomFlow.path()"),
    form: window.eval("state.teacherRoom"),
    next: window.eval("teacherRoomFlow.node").querySelector(".sw-next"),
  };
}

function jsonReply(body) {
  return Promise.resolve({
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    json: () => Promise.resolve(body),
  });
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("[P198] the way into the teacher room wizard", () => {
  test("no entry without the IServ privilege", () => {
    const { window } = loadApp();
    seed(window, ONE_CHILD, Object.assign({}, ROOMS, { can_write_to_teacher: false }));
    expect(window.eval("(function () { return teacherRoomEntry('btn'); })")()).toBe(null);
  });

  test("the entry sits in the room list once the privilege is there", () => {
    const { window } = loadApp();
    seed(window, ONE_CHILD);
    const view = window.eval("(function () { return messengerView(); })")();
    const entry = view.querySelector(".list-actions .btn");
    expect(entry).not.toBeNull();
    expect(entry.textContent).toContain(window.eval("t('messenger.create.action')"));
  });

  test("the empty room list carries the entry as its own action", () => {
    const { window } = loadApp();
    seed(window, ONE_CHILD, Object.assign({}, ROOMS, { rooms: [] }));
    const view = window.eval("(function () { return messengerView(); })")();
    expect(view.querySelector(".empty .btn")).not.toBeNull();
  });
});

describe("[P198] the wizard path", () => {
  test("one child skips the child step and presets the id", () => {
    const { window } = loadApp();
    seed(window, ONE_CHILD);
    window.eval("startTeacherRoom()");
    expect(flow(window).path).toEqual(["teacher", "parents", "review"]);
    expect(window.eval("state.teacherRoom.childIds")).toEqual(["c1"]);
  });

  test("more than one child asks, and nothing is preselected", () => {
    const { window } = loadApp();
    seed(window, TWO_CHILDREN);
    window.eval("startTeacherRoom()");
    expect(flow(window).path).toEqual(["teacher", "children", "parents", "review"]);
    expect(window.eval("state.teacherRoom.childIds")).toEqual([]);
  });

  test("the other-parents box starts switched off by default", () => {
    const { window } = loadApp();
    seed(window, ONE_CHILD);
    window.eval("startTeacherRoom()");
    expect(window.eval("state.teacherRoom.addOtherParents")).toBe(false);
    const field = window.eval("(function () { return teacherRoomParentsField(); })")();
    expect(field.querySelector("input[type=checkbox]").checked).toBe(false);
    expect(field.textContent).toContain(window.eval("t('messenger.create.parents.label')"));
    expect(field.textContent).toContain(window.eval("t('messenger.create.parents.origin')"));
  });

  test("no step past the teacher without a chosen teacher", () => {
    const { window } = loadApp();
    seed(window, ONE_CHILD);
    window.eval("startTeacherRoom()");
    const wizard = flow(window);
    wizard.next.click();
    expect(window.eval("teacherRoomFlow.current()")).toBe("teacher");
    expect(wizard.node.querySelector(".sw-status").textContent).toBe(
      window.eval("t('messenger.create.block.teacher')")
    );
  });

  test("no step past the child step without a child", () => {
    const { window } = loadApp();
    seed(window, TWO_CHILDREN);
    window.eval("startTeacherRoom()");
    window.eval(`(function (hit) { chooseTeacher(hit); })`)(TEACHER_A);
    flow(window).next.click();
    expect(window.eval("teacherRoomFlow.current()")).toBe("children");
    flow(window).next.click();
    expect(window.eval("teacherRoomFlow.current()")).toBe("children");
  });
});

describe("[P198] the teacher search", () => {
  test("it waits 250 ms, asks once and drops the old request on the next keystroke", async () => {
    vi.useFakeTimers();
    try {
      const { window } = loadApp();
      seed(window, ONE_CHILD);
      const calls = [];
      const aborted = [];
      window.fetch = (input, init) => {
        calls.push(String(input));
        if (init && init.signal) init.signal.addEventListener("abort", () => aborted.push(String(input)));
        return jsonReply({ teachers: [TEACHER_A], allowed: true });
      };
      window.eval("startTeacherRoom()");
      window.eval("queueTeacherSearch('Ost')");
      vi.advanceTimersByTime(240);
      expect(calls.length).toBe(0);
      vi.advanceTimersByTime(20);
      expect(calls.length).toBe(1);
      expect(calls[0]).toContain("api/messenger/teachers?query=Ost");
      window.eval("queueTeacherSearch('Oste')");
      expect(aborted.length).toBe(1);
      vi.advanceTimersByTime(260);
      expect(calls.length).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });

  test("an emptied field asks nothing and shows the starting hint again", async () => {
    vi.useFakeTimers();
    try {
      const { window } = loadApp();
      seed(window, ONE_CHILD);
      const calls = [];
      window.fetch = (input) => {
        calls.push(String(input));
        return jsonReply({ teachers: [], allowed: true });
      };
      window.eval("startTeacherRoom()");
      window.eval("queueTeacherSearch('   ')");
      vi.advanceTimersByTime(500);
      expect(calls).toEqual([]);
      expect(window.eval("state.teacherRoom.results")).toBe(null);
      const nodes = window.eval("(function () { return teacherResultNodes()[0]; })")();
      expect(nodes.textContent).toContain(window.eval("t('messenger.create.search.start.title')"));
    } finally {
      vi.useRealTimers();
    }
  });

  test("zero hits is an empty state, not a dead end", async () => {
    const { window } = loadApp();
    seed(window, ONE_CHILD);
    window.fetch = () => jsonReply({ teachers: [], allowed: true });
    window.eval("startTeacherRoom()");
    window.eval("(function () { state.teacherRoom.query = 'Zzz'; })")();
    await window.eval("runTeacherSearch('Zzz')");
    const node = window.eval("(function () { return teacherResultNodes()[0]; })")();
    expect(node.textContent).toContain(window.eval("t('messenger.create.search.empty.title')"));
  });

  test("a broken search says so instead of pretending nobody exists", async () => {
    const { window } = loadApp();
    seed(window, ONE_CHILD);
    window.fetch = () => Promise.reject(new Error("boom"));
    window.eval("startTeacherRoom()");
    window.eval("(function () { state.teacherRoom.query = 'Ost'; })")();
    await window.eval("runTeacherSearch('Ost')");
    const node = window.eval("(function () { return teacherResultNodes()[0]; })")();
    expect(node.textContent).toContain(window.eval("t('messenger.create.search.failed.title')"));
  });

  test("a hit shows the extra line when IServ ships one", () => {
    const { window } = loadApp();
    seed(window, ONE_CHILD);
    window.eval("startTeacherRoom()");
    const row = window.eval("(function (hit) { return teacherHitRow(hit); })")(
      Object.assign({}, TEACHER_A, { extra: "Klasse 3b" })
    );
    expect(row.textContent).toContain("Hr. Osterkamp");
    expect(row.textContent).toContain("Klasse 3b");
  });
});

describe("[P198] duplicate defence and the summary", () => {
  test("a teacher who already has a room adds the duplicate step", () => {
    const { window } = loadApp();
    seed(window, ONE_CHILD);
    window.eval("startTeacherRoom()");
    window.eval("(function (hit) { chooseTeacher(hit); })")(TEACHER_B);
    expect(flow(window).path).toEqual(["teacher", "parents", "duplicate", "review"]);
    window.eval("(function (hit) { chooseTeacher(hit); })")(TEACHER_A);
    expect(flow(window).path).toEqual(["teacher", "parents", "review"]);
  });

  test("the duplicate step offers the existing room instead of a second one", () => {
    const { window } = loadApp();
    seed(window, ONE_CHILD);
    window.eval("startTeacherRoom()");
    window.eval("(function (hit) { chooseTeacher(hit); })")(TEACHER_B);
    window.eval("teacherRoomFlow.go('duplicate')");
    const node = window.eval("teacherRoomFlow.node");
    expect(node.querySelector(".create-name").textContent).toBe("Fr. Behrend");
    node.querySelector(".sw-body .btn").click();
    expect(window.eval("state.teacherRoom")).toBe(null);
    expect(window.eval("state.view")).toBe("messenger");
    expect(window.eval("state.messengerRoom.room_id")).toBe("!b:example.test");
  });

  test("the summary makes the teacher the loudest thing on the screen", () => {
    const { window } = loadApp();
    seed(window, ONE_CHILD);
    window.eval("startTeacherRoom()");
    window.eval("(function (hit) { chooseTeacher(hit); })")(TEACHER_A);
    window.eval("teacherRoomFlow.go('review')");
    const node = window.eval("teacherRoomFlow.node");
    expect(node.querySelector(".create-name b").textContent).toBe("Hr. Osterkamp");
    expect(node.textContent).toContain("Mia");
    expect(node.textContent).toContain(window.eval("t('messenger.create.review.parents.no')"));
    expect(node.querySelector(".sw-next").textContent).toBe(window.eval("t('messenger.create.submit')"));
    expect(node.querySelector(".sw-next").className).toContain("danger");
    expect(node.querySelector(".sw-status").textContent).toContain("Hr. Osterkamp");
  });
});

describe("[P198] the one POST", () => {
  function atReview(window, children) {
    seed(window, children || ONE_CHILD);
    window.eval("startTeacherRoom()");
    window.eval("(function (hit) { chooseTeacher(hit); })")(TEACHER_A);
    if ((children || ONE_CHILD).length > 1) {
      window.eval("(function () { state.teacherRoom.childIds = ['c1', 'c2']; })")();
    }
    window.eval("teacherRoomFlow.go('review')");
    return window.eval("teacherRoomFlow.node");
  }

  test("a double tap on the create button sends exactly one request", async () => {
    const { window } = loadApp();
    const node = atReview(window);
    const posts = [];
    window.fetch = (input, init) => {
      posts.push({ url: String(input), body: init && init.body ? JSON.parse(init.body) : null });
      if (String(input).includes("api/messenger/rooms")) return jsonReply(ROOMS);
      return jsonReply({ ok: true, message_key: "api.messenger.room.ok", room_id: "!new:example.test", joined: true });
    };
    const button = node.querySelector(".sw-next");
    button.click();
    button.click();
    await settle();
    await settle();
    const creates = posts.filter((call) => call.url.includes("api/messenger/room/teacher"));
    expect(creates.length).toBe(1);
  });

  test("the autocomplete value travels into the POST untouched, the flags beside it", async () => {
    const { window } = loadApp();
    const node = atReview(window, TWO_CHILDREN);
    window.eval("(function () { state.teacherRoom.addOtherParents = true; })")();
    const posts = [];
    window.fetch = (input, init) => {
      posts.push({ url: String(input), body: init && init.body ? JSON.parse(init.body) : null });
      if (String(input).includes("api/messenger/rooms")) return jsonReply(ROOMS);
      return jsonReply({ ok: true, message_key: "api.messenger.room.ok", room_id: "!new:example.test", joined: true });
    };
    node.querySelector(".sw-next").click();
    await settle();
    await settle();
    const create = posts.find((call) => call.url.includes("api/messenger/room/teacher"));
    expect(create.body).toEqual({
      teacher: TEACHER_A.value,
      child_ids: ["c1", "c2"],
      add_other_parents: true,
    });
  });

  test("a rejected answer keeps the user in the step with a readable message", async () => {
    const { window } = loadApp();
    const node = atReview(window);
    window.fetch = (input) => {
      if (String(input).includes("api/messenger/rooms")) return jsonReply(ROOMS);
      return jsonReply({ ok: false, message_key: "api.messenger.room.rejected" });
    };
    node.querySelector(".sw-next").click();
    await settle();
    await settle();
    await settle();
    expect(window.eval("teacherRoomFlow.current()")).toBe("review");
    expect(node.querySelector(".sw-status").textContent).toBe(
      window.eval("t('api.messenger.room.rejected')")
    );
  });

  test("a failure re-syncs and lands on the duplicate warning when a room appeared meanwhile", async () => {
    const { window } = loadApp();
    const node = atReview(window);
    window.fetch = (input) => {
      if (String(input).includes("api/messenger/rooms")) {
        return jsonReply({
          self_user_id: "@me:example.test",
          can_write_to_teacher: true,
          rooms: [
            {
              room_id: "!fresh:example.test",
              name: "Hr. Osterkamp",
              members: ["Hr. Osterkamp"],
              member_names: {},
              last_message: "",
              last_message_at: 1,
              unread_count: 0,
            },
          ],
        });
      }
      return jsonReply({ ok: false, message_key: "api.messenger.room.failed" });
    };
    node.querySelector(".sw-next").click();
    await settle();
    await settle();
    await settle();
    expect(window.eval("teacherRoomFlow.current()")).toBe("duplicate");
    expect(window.eval("state.teacherRoom.duplicate.room_id")).toBe("!fresh:example.test");
  });

  test("a created room opens right away instead of dropping back into the list", async () => {
    const { window } = loadApp();
    const node = atReview(window);
    window.fetch = (input) => {
      if (String(input).includes("api/messenger/rooms")) {
        return jsonReply({
          self_user_id: "@me:example.test",
          can_write_to_teacher: true,
          rooms: [
            {
              room_id: "!new:example.test",
              name: "Hr. Osterkamp",
              members: ["Hr. Osterkamp"],
              member_names: {},
              last_message: "",
              last_message_at: 1,
              unread_count: 0,
            },
          ],
        });
      }
      if (String(input).includes("api/messenger/room?")) return jsonReply({ messages: [], before: "" });
      return jsonReply({ ok: true, message_key: "api.messenger.room.ok", room_id: "!new:example.test", joined: true });
    };
    node.querySelector(".sw-next").click();
    await settle();
    await settle();
    await settle();
    expect(window.eval("state.teacherRoom")).toBe(null);
    expect(window.eval("state.view")).toBe("messenger");
    expect(window.eval("state.messengerRoom.room_id")).toBe("!new:example.test");
  });
});

describe("[P198] a late answer never overwrites a newer query", () => {
  test("an answer that belongs to an older query is dropped", async () => {
    const { window } = loadApp();
    seed(window, ONE_CHILD);
    window.fetch = () => jsonReply({ teachers: [TEACHER_A], allowed: true });
    window.eval("startTeacherRoom()");
    window.eval("(function () { state.teacherRoom.query = 'Oste'; })")();
    await window.eval("runTeacherSearch('Ost')");
    expect(window.eval("state.teacherRoom.results")).toBe(null);
  });
});
