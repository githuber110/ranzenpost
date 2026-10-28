const FORUM_READ_TIMEOUT_MS = 180000;

async function loadAccountList(key, path, views, apply) {
  const current = accountState(key);
  const keep = !!(current && !current.error);
  const outcome = await reload(key, () => getJson(path), keep);
  if (!outcome) return;
  if (outcome.data) apply(outcome.data);
  else if (outcome.error) apply({ error: outcome.error });
  if (views.includes(state.view)) rerender();
}

function accountState(key) {
  if (key === "forums") return state.forums;
  if (key === "texts") return state.texts;
  if (key === "infodisplay") return state.infodisplay;
  if (key === "whiteboards") return state.whiteboards;
  return null;
}

function loadForums() {
  return loadAccountList("forums", "api/forums", ["overview", "forums"], (value) => { state.forums = value; });
}

function loadTexts() {
  return loadAccountList("texts", "api/texts", ["overview", "texts"], (value) => { state.texts = value; });
}

function loadInfodisplay() {
  return loadAccountList("infodisplay", "api/infodisplay", ["overview", "infodisplay"], (value) => { state.infodisplay = value; });
}

function loadWhiteboards() {
  return loadAccountList("whiteboards", "api/whiteboards", ["overview", "whiteboards"], (value) => { state.whiteboards = value; });
}

function loadAccountLists() {
  return Promise.all([
    moduleOn("forums") ? loadForums() : null,
    moduleOn("texts") ? loadTexts() : null,
    moduleOn("infodisplay") ? loadInfodisplay() : null,
    moduleOn("whiteboards") ? loadWhiteboards() : null,
  ]);
}

function accountEntries(key) {
  const data = accountState(key);
  return data && Array.isArray(data[key]) ? data[key].filter((entry) => entry && typeof entry === "object") : [];
}

function listUnreadable(data, count) {
  if (!data || data.error || count || !Array.isArray(data.unreadable) || !data.unreadable.length) return false;
  const unavailable = Array.isArray(data.unavailable) ? data.unavailable : [];
  return unavailable.every((id) => data.unreadable.includes(id));
}

function unreadableBlock(iconName) {
  return emptyBlock(iconName, t("accountLists.unreadable.title"), t("accountLists.unreadable.text"));
}

function plainRow(title, sub, chips, side, unread, extraClass) {
  const tags = chips.filter(Boolean);
  return el("div", { class: `row ${unread ? "" : "read"} list-row ${extraClass}` }, [
    el("span", { class: "row-dot" }, unread ? [el("i", {})] : []),
    el("div", { class: "row-main" }, [
      tags.length ? el("div", { class: "row-tags" }, tags) : null,
      iservText("div", { class: "row-title" }, title),
      sub ? iservText("div", { class: "row-sub" }, sub) : null,
    ]),
    side ? el("div", { class: "row-side" }, [side]) : null,
  ]);
}

function forumUnread(forum) {
  return Number.isInteger(forum.unread) && forum.unread >= 0 ? forum.unread : null;
}

function forumsUnreadTotal(forums) {
  return (forums || accountEntries("forums")).reduce((sum, forum) => sum + (forumUnread(forum) || 0), 0);
}

function unreadForums() {
  return accountEntries("forums").filter((forum) => (forumUnread(forum) || 0) > 0);
}

function forumSub(forum) {
  const lines = [];
  const description = String(forum.description || "").trim();
  if (description) lines.push(description);
  const parts = [];
  for (const entry of Array.isArray(forum.extra) ? forum.extra : []) {
    const value = String((entry && entry.value) || "").trim();
    if (value) parts.push(entry.label ? `${entry.label}: ${value}` : value);
  }
  const last = String(forum.last_post || "").trim();
  if (last && last !== "-") parts.push(t("forums.lastPost", { text: last }));
  if (parts.length) lines.push(parts.join(" · "));
  return lines.join("\n");
}

function forumUnreadTag(forum) {
  const unread = forumUnread(forum);
  return unread ? el("span", { class: "tag open forum-unread" }, tCount("forums.unreadCount", unread)) : null;
}

function forumRow(forum) {
  const unread = (forumUnread(forum) || 0) > 0;
  return plainRow(forum.title || t("forums.untitled"), forumSub(forum), [schoolTag(forum)], forumUnreadTag(forum), unread, "forum-row");
}

function forumGroups(forums) {
  const groups = new Map();
  for (const forum of forums) {
    const name = String(forum.category || "").trim();
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(forum);
  }
  return [...groups.entries()];
}

function forumReadOffered(id) {
  const schools = state.forums && Array.isArray(state.forums.schools) ? state.forums.schools : [];
  return schools.some((school) => school && (school.connection_id || "") === id && school.mark_read === true);
}

function forumSchoolsWithUnread() {
  const schools = [];
  for (const forum of unreadForums()) {
    const id = forum.connection_id || "";
    if (!schools.includes(id) && forumReadOffered(id)) schools.push(id);
  }
  return schools;
}

async function markForumsRead(connectionId) {
  const ok = await confirmAction({
    title: t("forums.readConfirm.title"),
    text: t("forums.readConfirm.text"),
    confirmLabel: t("forums.readConfirm.confirm"),
  });
  if (!ok) return;
  state.forumsBusy = true;
  rerender();
  try {
    const result = await postJson("api/forums/read", { connection_id: connectionId, confirmed: true }, FORUM_READ_TIMEOUT_MS);
    if (result && result.ok) toast(t("forums.readDone"), "good");
    else toast(apiMessage(result || {}, "api.forums.read.uncertain"), "bad");
  } catch (error) {
    if (handleApiFailure(error, connectionId)) {
      state.forumsBusy = false;
      return;
    }
    toast(t("api.forums.read.uncertain"), "bad");
  }
  state.forumsBusy = false;
  await loadForums();
  rerender();
}

function forumsHead(forums) {
  const unread = forumsUnreadTotal(forums);
  const schools = forumSchoolsWithUnread();
  const tools = schools.map((id) => el("button", {
    class: "forum-read",
    type: "button",
    disabled: state.forumsBusy ? "" : null,
    onclick: () => markForumsRead(id),
  }, schools.length > 1 ? t("forums.markAllReadAt", { school: schoolShortName(id) || schoolFullName(id) }) : t("forums.markAllRead")));
  return el("div", { class: "section-head" }, [
    el("span", { class: "overline" }, unread ? tCount("forums.unreadTotal", unread) : tCount("forums.count", forums.length)),
    tools.length ? el("div", { class: "letters-tools" }, tools) : null,
  ]);
}

function forumsView() {
  const view = el("div", { class: "school-list" });
  const data = state.forums;
  if (!data) {
    view.append(loadingBlock());
    return view;
  }
  const forums = accountEntries("forums");
  if (listUnreadable(data, forums.length)) {
    view.append(unreadableBlock("forums"));
    return view;
  }
  if (data.error || listUnknown(data, forums.length)) {
    view.append(listFailure("forums", () => { state.forums = null; rerender(); loadForums(); }));
    return view;
  }
  const note = refreshFailureNote("forums");
  if (note) view.append(note);
  if (!forums.length) {
    view.append(emptyBlock("forums", t("forums.empty.title"), t("forums.empty.text")));
    return view;
  }
  view.append(el("div", { class: "list-head forums-head" }, [forumsHead(forums)]));
  for (const [category, entries] of forumGroups(forums)) {
    const rows = entries.map(forumRow);
    view.append(category ? accountSection(category, rows) : el("div", { class: "rows" }, rows));
  }
  return view;
}

function accountSection(title, rows) {
  return el("section", { class: "list-section" }, [
    el("div", { class: "section-head" }, [iservText("span", { class: "overline" }, title)]),
    el("div", { class: "rows" }, rows),
  ]);
}

function textSchools() {
  const data = state.texts;
  return data && Array.isArray(data.schools) ? data.schools.filter((school) => school && typeof school === "object") : [];
}

function textFilterOptions() {
  const options = [];
  for (const school of textSchools()) {
    for (const choice of Array.isArray(school.filters) ? school.filters : []) {
      const value = String((choice && choice.value) || "");
      if (!value || options.some((option) => option.value === `filter:${value}`)) continue;
      options.push({ value: `filter:${value}`, label: String(choice.label || value), kind: "filter" });
    }
  }
  const tags = new Set();
  for (const text of accountEntries("texts")) {
    for (const tag of Array.isArray(text.tags) ? text.tags : []) if (typeof tag === "string" && tag) tags.add(tag);
  }
  const sorted = [...tags].sort((left, right) => left.localeCompare(right, currentLanguage(), { sensitivity: "base", numeric: true }));
  for (const tag of sorted) options.push({ value: `tag:${tag}`, label: tag, kind: "tag" });
  return options;
}

function textDefaultFilter(text) {
  const school = textSchools().find((entry) => (entry.connection_id || "") === (text.connection_id || ""));
  const choices = school && Array.isArray(school.filters) ? school.filters : [];
  const chosen = choices.find((choice) => choice && choice.default);
  return chosen ? String(chosen.value || "") : "";
}

function textInFilter(text, filter) {
  const memberOf = Array.isArray(text.filters) ? text.filters : [];
  if (!filter) {
    const standard = textDefaultFilter(text);
    return !standard || !memberOf.length || memberOf.includes(standard);
  }
  if (filter.startsWith("filter:")) return memberOf.includes(filter.slice(7));
  if (filter.startsWith("tag:")) return (Array.isArray(text.tags) ? text.tags : []).includes(filter.slice(4));
  return true;
}

function textMatches(text, query) {
  const haystack = [text.title, text.owner, ...(Array.isArray(text.tags) ? text.tags : [])].map((part) => String(part || "")).join(" ").toLowerCase();
  return haystack.includes(query);
}

function textSub(text) {
  const parts = [];
  const owner = String(text.owner || "").trim();
  if (owner) parts.push(owner);
  const changed = listMoment(text.changed, text.changed_text);
  if (changed) parts.push(t("texts.changed", { date: changed }));
  return parts.join(" · ");
}

function textRow(text) {
  const tags = (Array.isArray(text.tags) ? text.tags : []).filter((tag) => typeof tag === "string" && tag);
  const chips = [schoolTag(text)].concat(tags.map((tag) => iservText("span", { class: "tag" }, tag)));
  return plainRow(text.title || t("texts.untitled"), textSub(text), chips, null, false, "text-row");
}

function byChange(left, right) {
  return String(right.changed || "").localeCompare(String(left.changed || "")) || String(left.title || "").localeCompare(String(right.title || ""));
}

function setTextsFilter(value) {
  state.textsFilter = value;
  discardSheet();
}

function textsFilterSheet() {
  const options = textFilterOptions();
  const row = (value, label, own, hint, glyph) => el("div", { class: "opt", "aria-pressed": String((state.textsFilter || "") === value) }, [
    el("button", { class: "opt-main texts-filter-opt", type: "button", onclick: () => setTextsFilter(value) }, [
      icon(glyph, 20),
      el("span", {}, [own ? el("b", {}, label) : iservText("b", {}, label), hint ? el("small", {}, hint) : null]),
    ]),
  ]);
  const rows = [row("", t("texts.filter.standard"), true, t("texts.filter.standardHint"), "texts")]
    .concat(options.map((option) => row(option.value, option.label, false, option.kind === "tag" ? t("texts.filter.tag") : "", option.kind === "tag" ? "filter" : "texts")));
  return sheet(t("texts.filter.title"), [el("div", { class: "opt-list" }, rows)]);
}

function textsFilterLabel(options) {
  const chosen = options.find((option) => option.value === state.textsFilter);
  return chosen ? iservText("span", { class: "chip-label" }, chosen.label) : el("span", { class: "chip-label" }, t("texts.filter.standard"));
}

function textsView() {
  const view = el("div", { class: "school-list" });
  const data = state.texts;
  if (!data) {
    view.append(loadingBlock());
    return view;
  }
  const texts = accountEntries("texts");
  if (listUnreadable(data, texts.length)) {
    view.append(unreadableBlock("texts"));
    return view;
  }
  if (data.error || listUnknown(data, texts.length)) {
    view.append(listFailure("texts", () => { state.texts = null; rerender(); loadTexts(); }));
    return view;
  }
  const note = refreshFailureNote("texts");
  if (note) view.append(note);
  if (!texts.length) {
    view.append(emptyBlock("texts", t("texts.empty.title"), t("texts.empty.text")));
    return view;
  }
  const options = textFilterOptions();
  if (state.textsFilter && !options.some((option) => option.value === state.textsFilter)) state.textsFilter = "";
  const head = el("div", { class: "list-head texts-head" });
  if (options.length) {
    head.append(el("div", { class: "chipbar" }, [
      el("button", { class: "chip chip-filter texts-filter", type: "button", "aria-pressed": String(!!state.textsFilter), onclick: () => openSheet(textsFilterSheet) }, [
        icon("filter", 14),
        textsFilterLabel(options),
      ]),
    ]));
  }
  const hits = el("span", { class: "search-hits" });
  const host = el("div", {});
  const renderBody = () => {
    const query = String(state.textsSearch || "").trim().toLowerCase();
    const shown = texts.filter((text) => textInFilter(text, state.textsFilter) && (!query || textMatches(text, query))).sort(byChange);
    hits.textContent = query ? tCount("common.hits", shown.length) : "";
    host.replaceChildren(shown.length
      ? el("div", { class: "rows" }, shown.map(textRow))
      : emptyBlock("search", t("texts.search.emptyTitle"), t(query ? "texts.search.emptyText" : "texts.filter.emptyText")));
  };
  head.append(searchField(state.textsSearch, t("texts.search.placeholder"), (value) => {
    state.textsSearch = value;
    renderBody();
  }, hits));
  view.append(head, host);
  renderBody();
  return view;
}

function standardTexts() {
  return accountEntries("texts").filter((text) => textInFilter(text, "")).sort(byChange);
}

function screenRow(screen) {
  return plainRow(screen.title || t("infodisplay.untitled"), "", [schoolTag(screen)], null, false, "compact screen-row");
}

function infodisplayView() {
  const view = el("div", { class: "school-list" });
  const data = state.infodisplay;
  if (!data) {
    view.append(loadingBlock());
    return view;
  }
  const screens = accountEntries("infodisplay");
  if (listUnreadable(data, screens.length)) {
    view.append(unreadableBlock("screen"));
    return view;
  }
  if (data.error || listUnknown(data, screens.length)) {
    view.append(listFailure("infodisplay", () => { state.infodisplay = null; rerender(); loadInfodisplay(); }));
    return view;
  }
  const note = refreshFailureNote("infodisplay");
  if (note) view.append(note);
  if (!screens.length) {
    view.append(emptyBlock("screen", t("infodisplay.empty.title"), t("infodisplay.empty.text")));
    return view;
  }
  view.append(el("div", { class: "rows" }, screens.map(screenRow)));
  return view;
}

function whiteboardSub(board) {
  const parts = [];
  const owner = String(board.owner || "").trim();
  if (owner) parts.push(owner);
  const created = listMoment(board.created, board.created_text);
  if (created) parts.push(t("whiteboards.created", { date: created }));
  const changed = listMoment(board.changed, board.changed_text);
  if (changed) parts.push(t("whiteboards.changed", { date: changed }));
  return parts.join(" · ");
}

function whiteboardRow(board) {
  return plainRow(board.title || t("whiteboards.untitled"), whiteboardSub(board), [schoolTag(board)], null, false, "whiteboard-row");
}

function byBoardChange(left, right) {
  const leftMoment = String(left.changed || left.created || "");
  const rightMoment = String(right.changed || right.created || "");
  return rightMoment.localeCompare(leftMoment) || String(left.title || "").localeCompare(String(right.title || ""), currentLanguage(), { sensitivity: "base", numeric: true });
}

function sortedWhiteboards() {
  return accountEntries("whiteboards").sort(byBoardChange);
}

function whiteboardsView() {
  const view = el("div", { class: "school-list" });
  const data = state.whiteboards;
  if (!data) {
    view.append(loadingBlock());
    return view;
  }
  const boards = sortedWhiteboards();
  if (listUnreadable(data, boards.length)) {
    view.append(unreadableBlock("board"));
    return view;
  }
  if (data.error || listUnknown(data, boards.length)) {
    view.append(listFailure("whiteboards", () => { state.whiteboards = null; rerender(); loadWhiteboards(); }));
    return view;
  }
  const note = refreshFailureNote("whiteboards");
  if (note) view.append(note);
  if (!boards.length) {
    view.append(emptyBlock("board", t("whiteboards.empty.title"), t("whiteboards.empty.text")));
    return view;
  }
  view.append(el("div", { class: "rows" }, boards.map(whiteboardRow)));
  return view;
}

function accountChapter(size, key, view, rows, build, load) {
  if (!moduleOn(key)) return null;
  const data = accountState(key);
  if (!data || listUnreadable(data, accountEntries(key).length)) return null;
  const chapter = overviewChapter(key, t(`blocks.${key}.title`), { label: t("overview.viewAll"), onclick: () => setView(view) });
  if (data.error || listUnknown(data, accountEntries(key).length)) {
    chapter.bodyClass = "panel-rest";
    chapter.blocks = [overviewFailureBlock(`${key}:failed`, load)];
    return chapter;
  }
  const listed = rows();
  if (!listed.length) return listPartlyUnknown(data) ? overviewListFailure(chapter, key, load) : null;
  return withPartialNote(chapterRows(chapter, size, layoutBlocks().blockOf(key), listed, build, overviewAllRow(`${key}:all`, t(`overview.all.${key}`), () => setView(view))), key, data);
}

function forumsChapter(size) {
  return accountChapter(size, "forums", "forums", unreadForums, (forum) => overviewBlock(
    `forum:${forum.connection_id || ""}:${forum.id}`,
    sizedRow(size, forum.title || t("forums.untitled"), String(forum.category || ""), tCount("forums.unreadCount", forumUnread(forum) || 0), true, () => setView("forums"), [schoolTag(forum)])
  ), loadForums);
}

function textsChapter(size) {
  return accountChapter(size, "texts", "texts", standardTexts, (text) => overviewBlock(
    `text:${text.connection_id || ""}:${text.id}`,
    sizedRow(size, text.title || t("texts.untitled"), String(text.owner || ""), text.changed ? listMoment(text.changed, text.changed_text) : "", false, () => setView("texts"), [schoolTag(text)])
  ), loadTexts);
}

function infodisplayChapter(size) {
  return accountChapter(size, "infodisplay", "infodisplay", () => accountEntries("infodisplay"), (screen) => overviewBlock(
    `screen:${screen.connection_id || ""}:${screen.id}`,
    sizedRow(size, screen.title || t("infodisplay.untitled"), "", "", false, () => setView("infodisplay"), [schoolTag(screen)])
  ), loadInfodisplay);
}

function whiteboardsChapter(size) {
  return accountChapter(size, "whiteboards", "whiteboards", sortedWhiteboards, (board) => overviewBlock(
    `whiteboard:${board.connection_id || ""}:${board.id}`,
    sizedRow(size, board.title || t("whiteboards.untitled"), String(board.owner || ""), listMoment(board.changed || board.created, board.changed ? board.changed_text : board.created_text), false, () => setView("whiteboards"), [schoolTag(board)])
  ), loadWhiteboards);
}
