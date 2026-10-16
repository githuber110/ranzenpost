const MESSENGER_POLL_MS = 25000;
const MESSENGER_LOAD_KEY = "messenger";
const MESSENGER_ROOM_LOAD_KEY = "messengerRoom";
const MESSENGER_OLDER_LOAD_KEY = "messengerRoomOlder";
const MESSENGER_SYSTEM_KEYS = {
  join: "messenger.system.join",
  leave: "messenger.system.leave",
  invite: "messenger.system.invite",
};
const CHAT_BOTTOM_SLACK = 40;
const CHAT_OLDER_TRIGGER = 80;
const CHAT_COMPOSER_MAX = 132;

let messengerPollTimer = 0;
let chatViewportBound = false;

function inMessengerRoom() {
  return state.view === "messenger" && !!state.messengerRoom;
}

function messengerUnreadTotal() {
  const data = state.messengerRooms;
  if (data && !data.error) {
    return (data.rooms || []).reduce((sum, entry) => sum + (Number(entry.unread_count) || 0), 0);
  }
  let stored = 0;
  for (const entry of readySchools()) {
    const count = Number(((entry.poll_state || {}).messenger_unread) || 0);
    if (Number.isFinite(count) && count > 0) stored += count;
  }
  return stored;
}

function messengerRoomUnread() {
  const room = state.messengerRoom;
  return room ? Number(room.unread) || 0 : 0;
}

function messengerRoomLastEventId() {
  const room = state.messengerRoom;
  if (!room) return "";
  for (let index = room.messages.length - 1; index >= 0; index--) {
    const eventId = room.messages[index].event_id;
    if (eventId) return eventId;
  }
  return "";
}

function messengerReadButton() {
  const room = state.messengerRoom;
  const button = el("button", {
    class: "icon-btn messenger-read",
    type: "button",
    "aria-label": t("messenger.read.action"),
    "aria-busy": room && room.marking ? "true" : "false",
  }, [room && room.marking ? el("span", { class: "spin" }) : icon("check", 18)]);
  button.disabled = !!(room && room.marking) || !messengerRoomLastEventId();
  button.addEventListener("click", () => markMessengerRoomRead());
  return button;
}

async function markMessengerRoomRead() {
  const room = state.messengerRoom;
  const eventId = messengerRoomLastEventId();
  if (!room || room.marking || !eventId) return;
  room.marking = true;
  rerender();
  let result = null;
  try {
    result = await postJson("api/messenger/read", { room_id: room.room_id, event_id: eventId, connection_id: room.connectionId || "" });
  } catch (error) {
    if (handleApiFailure(error)) return;
    result = null;
  }
  if (state.messengerRoom !== room) return;
  room.marking = false;
  if (!result || !result.ok) {
    rerender();
    toast(apiMessage(result, "api.messenger.read.failed"), "bad");
    return;
  }
  room.unread = 0;
  rerender();
  toast(apiMessage(result, "api.messenger.read.ok"));
  await loadMessengerRooms();
}

function messengerRoomHeadTitle() {
  const room = state.messengerRoom;
  return iservText("h1", { class: "header-title" }, room.name || t("messenger.title"));
}

async function loadMessengerRooms() {
  const keep = !!(state.messengerRooms && !state.messengerRooms.error);
  const outcome = await reload(MESSENGER_LOAD_KEY, () => getJson("api/messenger/rooms"), keep);
  if (!outcome) return;
  if (outcome.data) state.messengerRooms = outcome.data;
  else if (outcome.error) {
    state.messengerRooms = {
      error: outcome.error,
      body: outcome.body || null,
      timedOut: !!outcome.timedOut,
    };
  }
  rerender();
}

function messengerFailureText(failure, fallbackKey) {
  const body = failure && failure.body;
  if (body && body.message_key) return t(body.message_key, body.message_vars);
  if (failure && failure.timedOut) return t("api.messenger.error.timeout");
  return t(fallbackKey || "messenger.error.text");
}

function diagnosisValueText(value) {
  if (typeof value === "boolean") return t(value ? "common.yes" : "common.no");
  if (Array.isArray(value)) return value.map(diagnosisValueText).join(", ");
  if (value && typeof value === "object") {
    return Object.keys(value).map((key) => `${key}: ${diagnosisValueText(value[key])}`).join(", ");
  }
  if (value === null || value === undefined || value === "") return t("common.none");
  return String(value);
}

function diagnosisLabel(key) {
  const candidate = `diagnosis.${key}`;
  return hasMessage(candidate) ? t(candidate) : key;
}

function diagnosisEntries(diagnosis) {
  if (!diagnosis || typeof diagnosis !== "object") return [];
  return Object.keys(diagnosis).map((key) => ({
    label: diagnosisLabel(key),
    value: diagnosisValueText(diagnosis[key]),
  }));
}

function messengerDiagnosisEntries(failure) {
  return diagnosisEntries(failure && failure.body && failure.body.diagnosis);
}

async function retryMessengerRooms() {
  if (state.messengerRetrying) return;
  state.messengerRetrying = true;
  state.messengerRetryFailed = false;
  rerender();
  state.messengerRooms = null;
  await loadMessengerRooms();
  state.messengerRetrying = false;
  state.messengerRetryFailed = !!(state.messengerRooms && state.messengerRooms.error);
  rerender();
}

function messengerUnavailableBlock(data) {
  const failure = data && data.messages_unavailable;
  if (!failure) return null;
  const entry = teacherRoomEntry("btn");
  if (failure.diagnosis && failure.diagnosis.stage === "no_credentials") {
    const calm = emptyBlock("messages", t("messenger.empty.title"), t("messenger.empty.withheld"), entry);
    const details = diagnosisEntries(failure.diagnosis);
    if (details.length) calm.append(techDetailsButton(details));
    return calm;
  }
  const retry = retryButton(retryMessengerRooms);
  if (entry) retry.classList.add("ghost");
  const block = emptyBlock(
    "alert",
    t("messenger.unavailable.title"),
    t("messenger.unavailable.text", { reason: t(failure.message_key || "messenger.error.text") }),
    entry || retry
  );
  if (entry) block.append(retry);
  const entries = diagnosisEntries(failure.diagnosis);
  if (entries.length) block.append(techDetailsButton(entries));
  return block;
}

function messengerErrorBlock() {
  const failure = state.messengerRooms || {};
  const block = emptyBlock(
    "alert",
    t("messenger.error.title"),
    messengerFailureText(failure),
    retryButton(retryMessengerRooms)
  );
  if (state.messengerRetryFailed) {
    block.insertBefore(noteBlock(t("messenger.error.retryFailed")), block.lastChild);
  }
  const entries = messengerDiagnosisEntries(failure);
  if (entries.length) block.append(techDetailsButton(entries));
  return block;
}

function matchesRoomQuery(room, query) {
  return [room.name || "", (room.members || []).join(" "), room.last_message || ""]
    .join(" ")
    .toLowerCase()
    .includes(query);
}

function messengerDate(value) {
  const stamp = Number(value);
  if (!stamp) return null;
  const date = new Date(stamp);
  return Number.isNaN(date.getTime()) ? null : date;
}

function messengerStamp(value) {
  const date = messengerDate(value);
  if (!date) return "";
  return isoDate(date) === isoDate(new Date()) ? formatTime(date) : formatShortDate(date);
}

function messengerTime(value) {
  const date = messengerDate(value);
  return date ? formatTime(date) : "";
}

function messengerDayKey(value) {
  const date = messengerDate(value);
  return date ? isoDate(date) : "";
}

function messengerDayLabel(value) {
  const date = messengerDate(value);
  return date ? formatWeekdayDay(date) : "";
}

function messengerRoomRow(room) {
  const unread = Number(room.unread_count) || 0;
  const dot = el("span", { class: "row-dot" }, unread ? el("i") : null);
  const school = schoolTag(room);
  const main = el("div", { class: "row-main" }, [
    school ? el("div", { class: "row-tags" }, [school]) : null,
    iservText("div", { class: "row-title" }, room.name || t("messenger.title")),
  ]);
  if (room.last_message) main.append(iservText("div", { class: "row-sub" }, room.last_message));
  const side = el("div", { class: "row-side" }, [el("span", { class: "row-meta" }, messengerStamp(room.last_message_at))]);
  if (unread) side.append(el("span", { class: "badge" }, badgeText(unread)));
  return el("button", {
    type: "button",
    class: openRowClass(unread ? "row" : "row read", "room", room.room_id),
    onclick: () => openMessengerRoom(room),
  }, [dot, main, side]);
}

function messengerView() {
  const view = el("div", {});
  const head = el("div", { class: "list-head" });
  view.append(head);
  if (state.messengerRetrying) {
    view.append(noteBlock(t("messenger.error.retrying")));
    view.append(loadingBlock());
    return view;
  }
  const data = state.messengerRooms;
  if (!data) {
    autoLoad(MESSENGER_LOAD_KEY, loadMessengerRooms);
    view.append(loadingBlock());
    return view;
  }
  if (data.error) {
    view.append(anyOutage() ? outageEmptyBlock() : messengerErrorBlock());
    return view;
  }
  const note = refreshFailureNote(MESSENGER_LOAD_KEY);
  if (note) head.append(note);
  const rooms = data.rooms || [];
  if (!rooms.length) {
    const unavailable = messengerUnavailableBlock(data);
    if (unavailable) {
      view.append(unavailable);
      return view;
    }
    view.append(
      emptyBlock("messages", t("messenger.empty.title"), t("messenger.empty.text"), teacherRoomEntry("btn"))
    );
    return view;
  }
  const entry = teacherRoomEntry("btn slim");
  if (entry) head.append(el("div", { class: "list-actions" }, [entry]));
  const schoolBar = schoolFilterBar(rooms, state.messengerSchoolFilter, setMessengerSchoolFilter);
  if (schoolBar) head.append(schoolBar);
  const hitCount = el("span", { class: "search-hits" });
  const rowsHost = el("div", {});
  function renderRoomRows() {
    const query = (state.messengerSearch || "").trim().toLowerCase();
    const bySchool = filterBySchool(rooms, state.messengerSchoolFilter);
    const filtered = query ? bySchool.filter((room) => matchesRoomQuery(room, query)) : bySchool;
    hitCount.textContent = query ? tCount("common.hits", filtered.length) : "";
    if (!filtered.length) {
      rowsHost.replaceChildren(emptyBlock("search", t("messenger.search.emptyTitle"), t("messenger.search.emptyText")));
      return;
    }
    const list = el("div", { class: "rows" });
    for (const room of filtered) list.append(messengerRoomRow(room));
    rowsHost.replaceChildren(list);
  }
  head.append(searchField(state.messengerSearch, t("messenger.search.placeholder"), (value) => {
    state.messengerSearch = value;
    renderRoomRows();
  }, hitCount));
  view.append(rowsHost);
  renderRoomRows();
  return view;
}

function openMessengerRoom(room) {
  state.messengerRoom = {
    room_id: room.room_id,
    connectionId: room.connection_id || "",
    name: room.name || "",
    memberNames: room.member_names || {},
    selfUserId: room.self_user_id || (state.messengerRooms && state.messengerRooms.self_user_id) || "",
    unread: Number(room.unread_count) || 0,
    marking: false,
    messages: [],
    before: "",
    loading: true,
    loadingOlder: false,
    error: "",
    draft: "",
    sending: false,
    atBottom: true,
    stickBottom: true,
    logScroll: null,
    restoreFromEnd: null,
  };
  rerender();
  startMessengerPoll();
  loadMessengerHistory();
}

function closeMessengerRoom() {
  stopMessengerPoll();
  state.messengerRoom = null;
  rerender();
  loadMessengerRooms();
}

function mergeMessengerMessages(existing, page) {
  const arrived = new Set(page.map((entry) => entry.event_id));
  return existing.filter((entry) => !arrived.has(entry.event_id)).concat(page);
}

function applyMessengerHistory(room, data, older) {
  const page = (data.messages || []).slice().reverse();
  if (data.self_user_id) room.selfUserId = data.self_user_id;
  if (older) {
    room.messages = page.concat(room.messages);
    room.before = data.before || "";
    return;
  }
  const first = !room.messages.length;
  const grown = mergeMessengerMessages(room.messages, page);
  const changed = grown.length !== room.messages.length;
  room.messages = grown;
  if (first) room.before = data.before || "";
  if (first || (changed && room.atBottom)) room.stickBottom = true;
}

async function loadMessengerHistory(options) {
  const room = state.messengerRoom;
  if (!room) return;
  const older = !!(options && options.older);
  if (older && (!room.before || room.loadingOlder)) return;
  if (older) {
    room.loadingOlder = true;
    rerender();
  }
  const query = older ? `&before=${encodeURIComponent(room.before)}` : "";
  const outcome = await reload(
    older ? MESSENGER_OLDER_LOAD_KEY : MESSENGER_ROOM_LOAD_KEY,
    () => getJson(`api/messenger/room?id=${encodeURIComponent(room.room_id)}&connection=${encodeURIComponent(room.connectionId || "")}${query}`),
    !older && room.messages.length > 0
  );
  if (!outcome || state.messengerRoom !== room) return;
  room.loading = false;
  room.loadingOlder = false;
  if (outcome.data) {
    room.error = "";
    room.errorBody = null;
    room.errorTimedOut = false;
    applyMessengerHistory(room, outcome.data, older);
  } else if (outcome.error) {
    room.error = outcome.error;
    room.errorBody = outcome.body || null;
    room.errorTimedOut = !!outcome.timedOut;
  }
  rerender();
}

function messengerSenderName(room, message) {
  return (room.memberNames || {})[message.sender] || "";
}

function messengerImage(message) {
  const label = message.body || t("messenger.image");
  const button = el("button", { type: "button", class: "chat-image", "aria-label": label }, [
    el("img", { class: "chat-thumb", src: apiUrl(message.media_url), alt: "", loading: "lazy", draggable: "false" }),
  ]);
  button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.disabled = true;
    try {
      await openAppFile(message.media_url, label, button);
    } catch (error) {
      toast(error.userMessage || t("common.attachmentOpenFailed"), "bad");
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function messengerBody(message) {
  if (message.kind === "image" && message.media_url) return messengerImage(message);
  if (message.kind === "file" && message.media_url) {
    return attachmentRows([{ filename: message.body || "", url: message.media_url }]);
  }
  return iservText("div", { class: "chat-text" }, message.body || "");
}

function messengerSystemRow(message) {
  return el("div", { class: "chat-system", role: "note" }, t(MESSENGER_SYSTEM_KEYS[message.system_kind] || "messenger.system.change"));
}

function messengerBubble(room, message) {
  const mine = !!room.selfUserId && message.sender === room.selfUserId;
  const bubble = el("div", { class: mine ? "chat-msg mine" : "chat-msg" });
  if (!mine) {
    const sender = messengerSenderName(room, message);
    if (sender) bubble.append(iservText("div", { class: "chat-from" }, sender));
  }
  bubble.append(messengerBody(message));
  bubble.append(el("div", { class: "chat-time" }, messengerTime(message.sent_at)));
  return bubble;
}

function messengerOlderStrip(room) {
  const strip = el("div", { class: "chat-older" });
  if (room.loadingOlder) {
    strip.append(el("span", { class: "spin" }));
    return strip;
  }
  strip.append(
    el("button", {
      class: "chat-older-btn",
      type: "button",
      onclick: () => loadMessengerHistory({ older: true }),
    }, t("messenger.room.loadOlder"))
  );
  return strip;
}

function messengerLogScroll(log, room) {
  room.logScroll = log.scrollTop;
  room.atBottom = log.scrollHeight - log.scrollTop - log.clientHeight <= CHAT_BOTTOM_SLACK;
  if (log.scrollTop > CHAT_OLDER_TRIGGER || !room.before || room.loadingOlder) return;
  if (log.scrollHeight <= log.clientHeight) return;
  room.restoreFromEnd = log.scrollHeight - log.scrollTop;
  loadMessengerHistory({ older: true });
}

function placeMessengerLog(log, room) {
  if (room.restoreFromEnd !== null && room.restoreFromEnd !== undefined) {
    log.scrollTop = Math.max(log.scrollHeight - room.restoreFromEnd, 0);
    room.restoreFromEnd = null;
  } else if (room.stickBottom || room.logScroll === null || room.logScroll === undefined) {
    log.scrollTop = log.scrollHeight;
    room.stickBottom = false;
  } else {
    log.scrollTop = room.logScroll;
  }
  room.logScroll = log.scrollTop;
}

function messengerStream(room) {
  const stream = el("div", { class: "chat-stream" });
  let lastDay = "";
  for (const message of room.messages) {
    const day = messengerDayKey(message.sent_at);
    if (day && day !== lastDay) {
      lastDay = day;
      stream.append(el("div", { class: "chat-day" }, messengerDayLabel(message.sent_at)));
    }
    stream.append(message.kind === "system" ? messengerSystemRow(message) : messengerBubble(room, message));
  }
  return stream;
}

function messengerLog(room) {
  const log = el("div", { class: "chat-log", role: "log" });
  if (room.loading && !room.messages.length) {
    log.append(loadingBlock());
    return log;
  }
  if (room.error && !room.messages.length) {
    const failure = { error: room.error, body: room.errorBody, timedOut: room.errorTimedOut };
    const block = emptyBlock("alert", t("messenger.room.error.title"), messengerFailureText(failure, "messenger.room.error.text"), retryButton(() => {
      room.error = "";
      room.errorBody = null;
      room.errorTimedOut = false;
      room.loading = true;
      rerender();
      loadMessengerHistory();
    }));
    const entries = messengerDiagnosisEntries(failure);
    if (entries.length) block.append(techDetailsButton(entries));
    log.append(block);
    return log;
  }
  if (!room.messages.length) {
    log.append(emptyBlock("messages", t("messenger.room.empty.title"), t("messenger.room.empty.text")));
    return log;
  }
  const note = refreshFailureNote(MESSENGER_ROOM_LOAD_KEY);
  if (note) log.append(note);
  if (room.before) log.append(messengerOlderStrip(room));
  log.append(messengerStream(room));
  log.addEventListener("scroll", () => messengerLogScroll(log, room));
  window.setTimeout(() => placeMessengerLog(log, room), 0);
  return log;
}

function growComposer(input) {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, CHAT_COMPOSER_MAX) + "px";
}

function messengerComposer(room) {
  const input = el("textarea", {
    class: "composer-input",
    rows: "1",
    dir: "auto",
    placeholder: t("messenger.compose.placeholder"),
    "aria-label": t("messenger.compose.placeholder"),
  });
  input.value = room.draft || "";
  input.addEventListener("input", () => {
    room.draft = input.value;
    growComposer(input);
  });
  const button = el("button", {
    class: "composer-send",
    type: "button",
    "aria-label": t("messenger.compose.send"),
  }, [room.sending ? el("span", { class: "spin" }) : icon("send", 18)]);
  button.disabled = !!room.sending;
  button.addEventListener("click", () => sendMessengerMessage(input));
  window.setTimeout(() => growComposer(input), 0);
  return el("div", { class: "composer" }, [el("div", { class: "composer-inner" }, [input, button])]);
}

const MESSENGER_SEND_TIMEOUT_MS = 60000;

function newMessengerTxnId() {
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

async function sendMessengerMessage(input) {
  const room = state.messengerRoom;
  if (!room || room.sending) return;
  const text = (input.value || "").trim();
  if (!text) {
    toast(t("api.messenger.send.empty"), "bad");
    input.focus();
    return;
  }
  room.draft = input.value;
  room.sending = true;
  if (!room.pendingSend || room.pendingSend.text !== text) room.pendingSend = { text, txn: newMessengerTxnId() };
  rerender();
  let result = null;
  try {
    result = await postJson("api/messenger/send", {
      room_id: room.room_id,
      text,
      connection_id: room.connectionId || "",
      txn_id: room.pendingSend.txn,
    }, MESSENGER_SEND_TIMEOUT_MS);
  } catch (error) {
    if (handleApiFailure(error)) return;
    result = isTimeoutError(error) ? { ok: false, uncertain: true, message_key: "api.messenger.send.unclear" } : null;
  }
  if (state.messengerRoom !== room) return;
  room.sending = false;
  if (result && result.uncertain) {
    rerender();
    toast(apiMessage(result, "api.messenger.send.unclear"), "bad");
    await loadMessengerHistory();
    return;
  }
  if (!result || !result.ok) {
    rerender();
    toast(apiMessage(result, "api.messenger.send.failed"), "bad");
    return;
  }
  room.pendingSend = null;
  room.draft = "";
  room.stickBottom = true;
  rerender();
  await loadMessengerHistory();
}

function messengerRoomView() {
  const room = state.messengerRoom;
  return el("div", { class: "chat" }, [messengerLog(room), messengerComposer(room)]);
}

function messengerComposing() {
  const active = document.activeElement;
  return !!(active && active.classList && active.classList.contains("composer-input"));
}

function pollMessengerRoom() {
  const room = state.messengerRoom;
  if (!room || state.view !== "messenger" || document.hidden) return;
  if (room.sending || room.loadingOlder || messengerComposing()) return;
  loadMessengerHistory();
  loadMessengerRooms();
}

function startMessengerPoll() {
  stopMessengerPoll();
  messengerPollTimer = window.setInterval(pollMessengerRoom, MESSENGER_POLL_MS);
}

function stopMessengerPoll() {
  if (!messengerPollTimer) return;
  window.clearInterval(messengerPollTimer);
  messengerPollTimer = 0;
}

function applyChatViewport() {
  const view = window.visualViewport;
  if (!view) return;
  const app = root();
  if (!app) return;
  if (!inMessengerRoom()) {
    app.style.removeProperty("--chat-vh");
    return;
  }
  app.style.setProperty("--chat-vh", Math.round(view.height) + "px");
}

function setupChatViewport() {
  if (chatViewportBound || !window.visualViewport) return;
  chatViewportBound = true;
  window.visualViewport.addEventListener("resize", applyChatViewport);
  window.visualViewport.addEventListener("scroll", applyChatViewport);
}

const TEACHER_SEARCH_DEBOUNCE_MS = 250;
const TEACHER_ROOM_TIMEOUT_MS = 30000;
const TEACHER_ROOM_FLOW_TEXTS = {
  back: "messenger.create.back",
  goal: "messenger.create.goal",
  progress: "messenger.create.progress",
  progressTotal: "messenger.create.progress.total",
  failed: "messenger.create.failed",
};

let teacherRoomFlow = null;
let teacherResultsHost = null;
let teacherSearchTimer = 0;
let teacherSearchAbort = null;

function teacherRoomEntry(className) {
  const data = state.messengerRooms;
  if (!data || data.error || !data.can_write_to_teacher || noChildren()) return null;
  return el("button", { class: className, type: "button", onclick: startTeacherRoom }, [
    icon("plus", 16),
    el("span", {}, t("messenger.create.action")),
  ]);
}

function teacherSchoolIds() {
  const data = state.messengerRooms || {};
  const listed = Array.isArray(data.teacher_schools) ? data.teacher_schools : readySchools().map((entry) => entry.id);
  return listed.filter((id) => connectionOf(id));
}

function startTeacherRoom() {
  const ids = teacherSchoolIds();
  if (ids.length > 1) {
    openSheet(() => schoolChoiceSheet(ids, "", openTeacherRoom));
    return;
  }
  openTeacherRoom(ids[0] || currentConnectionId());
}

function openTeacherRoom(connectionId) {
  state.teacherRoom = {
    connectionId: connectionId || "",
    teacher: null,
    query: "",
    results: null,
    searching: false,
    failed: false,
    allowed: true,
    childOptions: null,
    childrenFailed: false,
    childIds: [],
    addOtherParents: false,
    duplicate: null,
  };
  dropSheet();
  teacherRoomFlowStart();
  render();
  loadTeacherRoomChildren();
}

async function loadTeacherRoomChildren() {
  const form = state.teacherRoom;
  if (!form) return;
  form.childrenFailed = false;
  let data = null;
  try {
    data = await getJson(`api/messenger/room/teacher/children?connection=${encodeURIComponent(form.connectionId)}`);
  } catch (error) {
    if (state.teacherRoom !== form) return;
    form.childrenFailed = true;
    teacherRoomChildrenArrived();
    return;
  }
  if (state.teacherRoom !== form) return;
  form.childOptions = (data && data.children) || [];
  form.allowed = !data || data.allowed !== false;
  form.childIds = form.childOptions.length === 1 ? [form.childOptions[0].id] : [];
  teacherRoomChildrenArrived();
}

function teacherRoomChildrenArrived() {
  if (!teacherRoomFlow) return;
  if (teacherRoomFlow.current() !== "teacher") {
    teacherRoomFlow.render();
    return;
  }
  teacherRoomFlow.sync();
  renderTeacherResults();
}

function closeTeacherRoom() {
  cancelTeacherSearch();
  window.clearTimeout(teacherSearchTimer);
  teacherSearchTimer = 0;
  if (teacherRoomFlow) teacherRoomFlow.destroy();
  teacherRoomFlow = null;
  teacherResultsHost = null;
  state.teacherRoom = null;
}

function exitTeacherRoom() {
  closeTeacherRoom();
  render();
}

function teacherRoomFlowStart() {
  if (teacherRoomFlow) teacherRoomFlow.destroy();
  teacherRoomFlow = window.StepFlow.create({
    text: teacherRoomText,
    steps: teacherRoomPath,
    step: teacherRoomStep,
    title: () => t("messenger.create.title"),
    trailing: teacherRoomTrailing,
    onExit: exitTeacherRoom,
  });
  teacherRoomFlow.start(teacherRoomPath()[0]);
}

function teacherRoomText(name, vars) {
  const key = TEACHER_ROOM_FLOW_TEXTS[name];
  return key ? t(key, vars) : "";
}

function teacherRoomTrailing() {
  return el("button", {
    class: "icon-btn",
    type: "button",
    "aria-label": t("messenger.create.exit"),
    onclick: exitTeacherRoom,
  }, [icon("close", 18)]);
}

function teacherRoomPath() {
  const form = state.teacherRoom;
  if (!form) return ["teacher"];
  const path = ["teacher"];
  if (!form.childOptions || form.childOptions.length !== 1) path.push("children");
  path.push("parents");
  if (form.duplicate) path.push("duplicate");
  path.push("review");
  return path;
}

function cancelTeacherSearch() {
  if (!teacherSearchAbort) return;
  teacherSearchAbort.abort();
  teacherSearchAbort = null;
}

function queueTeacherSearch(value) {
  const form = state.teacherRoom;
  if (!form) return;
  form.query = value;
  window.clearTimeout(teacherSearchTimer);
  cancelTeacherSearch();
  const query = value.trim();
  form.failed = false;
  if (!query) {
    form.results = null;
    form.searching = false;
    renderTeacherResults();
    return;
  }
  form.searching = true;
  renderTeacherResults();
  teacherSearchTimer = window.setTimeout(() => runTeacherSearch(query), TEACHER_SEARCH_DEBOUNCE_MS);
}

async function runTeacherSearch(query) {
  const form = state.teacherRoom;
  if (!form) return;
  const controller = window.AbortController ? new window.AbortController() : null;
  teacherSearchAbort = controller;
  let data = null;
  try {
    data = await getJson(`api/messenger/teachers?query=${encodeURIComponent(query)}&connection=${encodeURIComponent(form.connectionId)}`, controller ? controller.signal : undefined);
  } catch (error) {
    if (controller && controller.signal.aborted) return;
    if (handleApiFailure(error)) return;
    data = null;
  }
  if (state.teacherRoom !== form || form.query.trim() !== query) return;
  teacherSearchAbort = null;
  form.searching = false;
  form.failed = !data;
  form.allowed = !data || data.allowed !== false;
  form.results = data ? data.teachers || [] : [];
  renderTeacherResults();
}

function findDuplicateRoom(label) {
  const data = state.messengerRooms;
  const name = String(label || "").trim().toLowerCase();
  if (!data || data.error || !name) return null;
  return (data.rooms || []).find((room) =>
    String(room.name || "").toLowerCase().includes(name) ||
    (room.members || []).some((member) => String(member).trim().toLowerCase() === name)
  ) || null;
}

function chooseTeacher(hit) {
  const form = state.teacherRoom;
  if (!form) return;
  form.teacher = hit;
  form.duplicate = findDuplicateRoom(hit.label);
  renderTeacherResults();
  if (teacherRoomFlow) teacherRoomFlow.sync();
}

function teacherHitRow(hit) {
  const form = state.teacherRoom;
  const chosen = !!(form.teacher && form.teacher.value === hit.value);
  const lines = [iservText("b", {}, hit.label)];
  if (hit.extra) lines.push(iservText("small", {}, hit.extra));
  return el("button", {
    class: "opt",
    type: "button",
    "aria-pressed": String(chosen),
    onclick: () => chooseTeacher(hit),
  }, [el("span", {}, lines)]);
}

function teacherResultNodes() {
  const form = state.teacherRoom;
  if (!form) return [];
  if (form.searching) return [loadingBlock()];
  if (form.failed) {
    return [emptyBlock("alert", t("messenger.create.search.failed.title"), t("messenger.create.search.failed.text"))];
  }
  if (!form.allowed) {
    return [emptyBlock("alert", t("messenger.create.search.forbidden.title"), t("messenger.create.search.forbidden.text"))];
  }
  if (form.results === null) {
    return [emptyBlock("search", t("messenger.create.search.start.title"), t("messenger.create.search.start.text"))];
  }
  if (!form.results.length) {
    return [emptyBlock("search", t("messenger.create.search.empty.title"), t("messenger.create.search.empty.text"))];
  }
  return [el("div", { class: "sw-list" }, form.results.map(teacherHitRow))];
}

function renderTeacherResults() {
  if (!teacherResultsHost) return;
  teacherResultsHost.replaceChildren(...teacherResultNodes());
}

function teacherSearchField() {
  const form = state.teacherRoom;
  const input = el("input", {
    class: "search-input",
    type: "search",
    dir: "auto",
    value: form.query || "",
    placeholder: t("messenger.create.search.placeholder"),
    "aria-label": t("messenger.create.search.placeholder"),
    autocomplete: "off",
    autocapitalize: "none",
    spellcheck: "false",
  });
  input.addEventListener("input", () => queueTeacherSearch(input.value));
  return el("div", { class: "search-field" }, [input]);
}

function toggleTeacherRoomChild(childId, on) {
  const form = state.teacherRoom;
  const kept = form.childIds.filter((value) => value !== childId);
  form.childIds = on ? kept.concat([childId]) : kept;
}

function teacherRoomChildRow(child) {
  const form = state.teacherRoom;
  const box = el("input", { type: "checkbox" });
  box.checked = form.childIds.includes(child.id);
  box.addEventListener("change", () => {
    toggleTeacherRoomChild(child.id, box.checked);
    if (teacherRoomFlow) teacherRoomFlow.sync();
  });
  return el("label", { class: "cell check" }, [box, iservText("span", {}, child.name || child.id)]);
}

function teacherRoomChildNodes() {
  const form = state.teacherRoom;
  if (form.childrenFailed) {
    return [
      emptyBlock(
        "alert",
        t("messenger.create.children.failed.title"),
        t("messenger.create.children.failed.text"),
        retryButton(loadTeacherRoomChildren)
      ),
    ];
  }
  if (!form.childOptions) return [loadingBlock()];
  if (!form.childOptions.length) {
    return [
      emptyBlock(
        "conferences",
        t("messenger.create.children.empty.title"),
        t("messenger.create.children.empty.text")
      ),
    ];
  }
  return [el("div", { class: "field-group" }, form.childOptions.map(teacherRoomChildRow))];
}

function teacherRoomParentsField() {
  const form = state.teacherRoom;
  const box = el("input", { type: "checkbox" });
  box.checked = !!form.addOtherParents;
  box.addEventListener("change", () => {
    form.addOtherParents = box.checked;
  });
  return el("div", { class: "field-group" }, [
    el("label", { class: "cell check" }, [box, el("span", {}, t("messenger.create.parents.label"))]),
    el("p", { class: "hint" }, t("messenger.create.parents.origin")),
  ]);
}

function teacherRoomChildNames() {
  const form = state.teacherRoom;
  return (form.childOptions || [])
    .filter((child) => form.childIds.includes(child.id))
    .map((child) => child.name || child.id)
    .filter(Boolean)
    .join(", ");
}

function teacherRoomReviewBody() {
  const form = state.teacherRoom;
  const school = manySchools() && form.connectionId ? [[t("messenger.create.review.school"), schoolFullName(form.connectionId)]] : [];
  return el("div", { class: "sw-review" }, [
    el("div", { class: "create-name" }, [iservText("b", {}, form.teacher ? form.teacher.label : "")]),
    factList(school.concat([
      [t("messenger.create.review.children"), teacherRoomChildNames()],
      [
        t("messenger.create.review.parents"),
        t(form.addOtherParents ? "messenger.create.review.parents.yes" : "messenger.create.review.parents.no"),
      ],
    ])),
    el("p", { class: "hint" }, t("messenger.create.parents.origin")),
  ]);
}

function openDuplicateRoom() {
  const form = state.teacherRoom;
  const room = form && form.duplicate;
  if (!room) return;
  closeTeacherRoom();
  setView("messenger");
  openMessengerRoom(room);
}

const TEACHER_ROOM_STEPS = {
  teacher(form) {
    return {
      list: true,
      question: t("messenger.create.step.teacher"),
      body: () => {
        teacherResultsHost = el("div", { class: "sw-results" }, teacherResultNodes());
        return [teacherSearchField(), teacherResultsHost];
      },
      block: form.teacher ? "" : t("messenger.create.block.teacher"),
    };
  },
  children(form) {
    return {
      list: true,
      question: t("messenger.create.step.children"),
      body: teacherRoomChildNodes(),
      block: form.childIds.length ? "" : t("messenger.create.block.children"),
    };
  },
  parents() {
    return {
      question: t("messenger.create.step.parents"),
      body: [teacherRoomParentsField()],
    };
  },
  duplicate(form) {
    const room = form.duplicate;
    return {
      question: t("messenger.create.step.duplicate"),
      body: [
        el("div", { class: "sw-review" }, [
          el("div", { class: "create-name" }, [iservText("b", {}, room ? room.name || "" : "")]),
          el("p", { class: "dlg-text" }, t("messenger.create.duplicate.text")),
          el("button", { class: "btn", type: "button", onclick: openDuplicateRoom }, t("messenger.create.duplicate.open")),
        ]),
      ],
      nextLabel: t("messenger.create.duplicate.continue"),
    };
  },
  review(form) {
    return {
      question: t("messenger.create.step.review"),
      body: [teacherRoomReviewBody()],
      hint: t("messenger.create.review.warning", { name: form.teacher ? form.teacher.label : "" }),
      nextLabel: t("messenger.create.submit"),
      busyLabel: t("common.sending"),
      danger: true,
      onNext: submitTeacherRoom,
    };
  },
};

function teacherRoomStep(id) {
  const form = state.teacherRoom;
  if (!form) return { question: "", body: [], nextLabel: "" };
  const builder = TEACHER_ROOM_STEPS[id];
  if (!builder) return { question: "", body: [], nextLabel: t("common.next") };
  const step = builder(form);
  if (!step.nextLabel) step.nextLabel = t("common.next");
  return step;
}

async function submitTeacherRoom() {
  const form = state.teacherRoom;
  if (!form || !form.teacher) return t("messenger.create.block.teacher");
  if (!form.childIds.length) return t("messenger.create.block.children");
  let result = null;
  try {
    result = await postJson("api/messenger/room/teacher", {
      connection_id: form.connectionId,
      teacher: form.teacher.value,
      child_ids: form.childIds,
      add_other_parents: !!form.addOtherParents,
    }, TEACHER_ROOM_TIMEOUT_MS);
  } catch (error) {
    if (handleApiFailure(error)) return false;
    result = null;
  }
  if (state.teacherRoom !== form) return false;
  if (!result || !result.ok) return teacherRoomFailure(form, result);
  return finishTeacherRoom(form, result);
}

async function teacherRoomFailure(form, result) {
  const message = apiMessage(result, "api.messenger.room.failed");
  await loadMessengerRooms();
  if (state.teacherRoom !== form) return false;
  form.duplicate = findDuplicateRoom(form.teacher.label);
  if (form.duplicate) return { step: "duplicate" };
  return message;
}

async function finishTeacherRoom(form, result) {
  const roomId = result.room_id || "";
  const message = apiMessage(result, "api.messenger.room.ok");
  closeTeacherRoom();
  await loadMessengerRooms();
  const rooms = (state.messengerRooms && state.messengerRooms.rooms) || [];
  const created = rooms.find((room) => room.room_id === roomId) || null;
  setView("messenger");
  if (created) openMessengerRoom(created);
  toast(message);
  return true;
}
