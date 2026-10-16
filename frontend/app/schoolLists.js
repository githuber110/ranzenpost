async function loadTasks() {
  const keep = !!(state.tasks && !state.tasks.error);
  const outcome = await reload("tasks", () => getJson("api/tasks"), keep);
  if (!outcome) return;
  if (outcome.data) state.tasks = outcome.data;
  else if (outcome.error) state.tasks = { error: outcome.error };
  if (state.view === "overview" || state.view === "tasks") rerender();
}

async function loadNews() {
  const keep = !!(state.news && !state.news.error);
  const outcome = await reload("news", () => getJson("api/news"), keep);
  if (!outcome) return;
  if (outcome.data) state.news = outcome.data;
  else if (outcome.error) state.news = { error: outcome.error };
  if (state.view === "overview" || state.view === "news") rerender();
}

function listedTasks() {
  return state.tasks && Array.isArray(state.tasks.tasks) ? state.tasks.tasks.filter((task) => task && typeof task === "object") : [];
}

function listedNews() {
  return state.news && Array.isArray(state.news.news) ? state.news.news.filter((item) => item && typeof item === "object") : [];
}

function taskIsPast(task) {
  return task.past === true;
}

function taskIsDone(task) {
  return task.done === true;
}

function taskDueKey(task) {
  return String(task.due || "") || "9999-12-31";
}

function byDue(left, right) {
  return taskDueKey(left).localeCompare(taskDueKey(right)) || String(left.title || "").localeCompare(String(right.title || ""));
}

function openTasks() {
  return listedTasks().filter((task) => !taskIsPast(task) && !taskIsDone(task)).sort(byDue);
}

function doneTasks() {
  return listedTasks().filter((task) => !taskIsPast(task) && taskIsDone(task)).sort(byDue);
}

function pastTasks() {
  return listedTasks().filter(taskIsPast).sort((left, right) => byDue(right, left));
}

function listMoment(value, text) {
  const raw = String(value || "");
  const day = raw.slice(0, 10);
  if (!parseIsoDay(day)) return String(text || "");
  if (raw.length <= 10) return dateLabel(day);
  const moment = new Date(raw);
  return Number.isNaN(moment.getTime()) ? dateLabel(day) : `${dateLabel(day)} ${formatTime(moment)}`;
}

function taskOverdue(task, now) {
  if (taskIsPast(task) || taskIsDone(task) || !task.due) return false;
  const raw = String(task.due);
  if (raw.length <= 10) return raw < isoDate(now);
  const moment = new Date(raw);
  return !Number.isNaN(moment.getTime()) && moment.getTime() < now.getTime();
}

function taskSub(task) {
  const parts = [];
  const due = listMoment(task.due, task.due_text);
  const start = listMoment(task.start, task.start_text);
  if (due) parts.push(t("tasks.due", { date: due }));
  if (start) parts.push(t("tasks.start", { date: start }));
  for (const entry of Array.isArray(task.extra) ? task.extra : []) {
    const value = String((entry && entry.value) || "").trim();
    if (value) parts.push(entry.label ? `${entry.label}: ${value}` : value);
  }
  return parts.join(" · ");
}

function listButtonRow(title, sub, chips, side, onclick, extraClass) {
  const tags = chips.filter(Boolean);
  return el("button", { class: `row read list-row ${extraClass}`, type: "button", onclick }, [
    el("span", { class: "row-dot" }),
    el("div", { class: "row-main" }, [
      tags.length ? el("div", { class: "row-tags" }, tags) : null,
      iservText("div", { class: "row-title" }, title),
      sub ? iservText("div", { class: "row-sub" }, sub) : null,
    ]),
    side ? el("div", { class: "row-side" }, [side]) : null,
  ]);
}

function taskTagNodes(task) {
  const tags = (Array.isArray(task.tags) ? task.tags : []).filter((tag) => typeof tag === "string" && tag);
  return [schoolTag(task)].concat(tags.map((tag) => iservText("span", { class: "tag" }, tag)));
}

function taskRow(task, now) {
  const side = taskOverdue(task, now) ? el("span", { class: "tag no" }, t("tasks.overdue")) : null;
  return listButtonRow(task.title || t("tasks.untitled"), taskSub(task), taskTagNodes(task), side, () => openTask(task), "task-row");
}

function listSection(title, rows) {
  return el("section", { class: "list-section" }, [
    el("div", { class: "section-head" }, [el("span", { class: "overline" }, title)]),
    el("div", { class: "rows" }, rows),
  ]);
}

function taskState(task) {
  const text = String(task.done_text || "").trim();
  if (text) return text;
  if (taskIsPast(task)) return t("tasks.section.past");
  if (task.done === true) return t("tasks.section.done");
  if (task.done === false) return t("tasks.section.open");
  return "";
}

function listUnknown(data, count) {
  return !!data && !data.error && !count && Array.isArray(data.unavailable) && data.unavailable.length > 0;
}

function listFailure(key, retry) {
  if (anyOutage()) return outageEmptyBlock();
  return emptyBlock("alert", t(`${key}.error.title`), t(`${key}.error.text`), retryButton(retry));
}

function tasksView() {
  const view = el("div", { class: "school-list" });
  const data = state.tasks;
  if (!data) {
    view.append(loadingBlock());
    return view;
  }
  const now = new Date();
  const open = openTasks();
  const done = doneTasks();
  const past = pastTasks();
  if (data.error || listUnknown(data, open.length + done.length + past.length)) {
    view.append(listFailure("tasks", () => { state.tasks = null; rerender(); loadTasks(); }));
    return view;
  }
  const note = refreshFailureNote("tasks");
  if (note) view.append(note);
  if (!open.length && !done.length && !past.length) {
    view.append(emptyBlock("tasks", t("tasks.empty.title"), t("tasks.empty.text")));
  }
  if (open.length) view.append(listSection(t("tasks.section.open"), open.map((task) => taskRow(task, now))));
  if (done.length) view.append(listSection(t("tasks.section.done"), done.map((task) => taskRow(task, now))));
  if (past.length) view.append(pastTasksSection(past, now));
  return view;
}

function pastTasksSection(past, now) {
  const section = el("details", { class: "list-section list-past" }, [
    el("summary", { class: "section-head" }, [
      el("span", { class: "ico-slot chev-toggle", html: iconSvg("chevron", 16) }),
      el("span", { class: "overline" }, t("tasks.section.past")),
      el("span", { class: "count" }, formatNumber(past.length)),
    ]),
    el("div", { class: "rows" }, past.map((task) => taskRow(task, now))),
  ]);
  section.open = state.tasksPastOpen === true;
  section.addEventListener("toggle", () => {
    state.tasksPastOpen = section.open;
  });
  return section;
}

function newsSub(item) {
  const parts = [];
  const category = String(item.category || item.category_slug || "").trim();
  if (category) parts.push(category);
  const date = listMoment(item.date, item.date_text);
  if (date) parts.push(date);
  return parts.join(" · ");
}

function newsRow(item) {
  const sub = [newsSub(item), String(item.summary || "").trim()].filter(Boolean).join("\n");
  const section = newsSection(item);
  const chips = [schoolTag(item), section ? el("span", { class: "tag" }, t(`news.section.${section}`)) : null];
  return listButtonRow(item.title || t("news.untitled"), sub, chips, null, () => openNews(item), "news-row");
}

function newsDetailOf(item) {
  const detail = item && item.detail;
  return detail && typeof detail === "object" && !detail.unreadable ? detail : null;
}

function newsFileRows(item, kind, entries) {
  const files = [];
  (Array.isArray(entries) ? entries : []).forEach((entry, index) => {
    if (!entry || typeof entry !== "object") return;
    const label = String(entry.label || "").trim();
    const fromSchool = typeof entry.path === "string" && entry.path.startsWith("/");
    const fields = { connection: item.connection_id || "", item: item.id || "", kind, index: String(index) };
    if (newsSection(item)) fields.section = newsSection(item);
    const query = new URLSearchParams(fields);
    files.push({ filename: label || t("common.attachment"), url: fromSchool ? `api/news/file?${query}` : "" });
  });
  return files.length ? attachmentRows(files) : null;
}

function newsTextRows(entries) {
  const rows = (Array.isArray(entries) ? entries : [])
    .filter((entry) => entry && typeof entry === "object")
    .map((entry) => {
      const label = String(entry.label || "").trim();
      const address = typeof entry.url === "string" ? entry.url.trim() : "";
      const sub = address && address !== label ? address : "";
      return el("div", { class: "row read news-link" }, [
        el("span", { class: "row-dot" }),
        el("div", { class: "row-main" }, [
          iservText("div", { class: "row-title full" }, label || address),
          sub ? iservText("div", { class: "row-sub" }, sub) : null,
        ]),
      ]);
    });
  return rows.length ? el("div", { class: "rows" }, rows) : null;
}

const NEWS_DETAIL_SECTIONS = [["files", "news.detail.files"], ["images", "news.detail.images"], ["links", "news.detail.links"]];

function newsItemKey(item) {
  return `${item.connection_id || ""}:${newsSection(item)}:${item.id || ""}`;
}

function newsDetailParts(item) {
  const body = [];
  const tags = [schoolTag(item)].filter(Boolean);
  if (tags.length) body.push(el("div", { class: "row-tags" }, tags));
  const meta = newsSub(item);
  if (meta) body.push(el("div", { class: "row-meta news-meta" }, meta));
  const detail = newsDetailOf(item);
  const lines = detail && Array.isArray(detail.text) ? detail.text.map((line) => String(line || "").trim()).filter(Boolean) : [];
  if (lines.length) {
    body.push(el("div", { class: "body-html news-text", dir: "auto" }, lines.map((line) => iservText("p", {}, line))));
  } else {
    const summary = String(item.summary || "").trim();
    if (summary) body.push(el("div", { class: "body-html news-text", dir: "auto" }, [iservText("p", {}, summary)]));
    if (state.newsDetailLoading === newsItemKey(item)) body.push(el("div", { class: "stamp", role: "status" }, t("news.detail.loading")));
    else body.push(noteBlock(t("news.detail.missing")));
  }
  for (const [field, key] of NEWS_DETAIL_SECTIONS) {
    const entries = detail && detail[field];
    const rows = field === "links" ? newsTextRows(entries) : newsFileRows(item, field, entries);
    if (!rows) continue;
    body.push(el("div", { class: "section-head news-section" }, [el("span", { class: "overline" }, t(key))]));
    body.push(rows);
  }
  return { title: item.title || t("news.untitled"), body, foot: null, extra: null };
}

async function loadNewsSectionDetail(item) {
  const key = newsItemKey(item);
  state.newsDetailLoading = key;
  const query = new URLSearchParams({ connection: item.connection_id || "", section: newsSection(item), item: item.id || "" });
  try {
    item.detail = await getJson(`api/news/section/detail?${query}`);
  } catch (error) {
    if (handleApiFailure(error, item.connection_id)) return;
  } finally {
    if (state.newsDetailLoading === key) state.newsDetailLoading = "";
  }
  rerender();
}

function openNews(item) {
  const detail = { kind: "news", item };
  if (newsSection(item) && !newsDetailOf(item) && item.path) loadNewsSectionDetail(item);
  if (detailPlacement(detail.kind, layoutMode(), state.view) === "pane") return openDetail(detail);
  openSheet(detailSheetFactory(detail));
}

const NEWS_SECTIONS = ["archive", "packages"];
const NEWS_SECTION_SECONDS = 600;

function newsSection(item) {
  return item && NEWS_SECTIONS.includes(item.section) ? item.section : "";
}

function currentNews() {
  return listedNews().filter((item) => !newsSection(item));
}

function linkedNewsSections() {
  const schools = state.news && Array.isArray(state.news.schools) ? state.news.schools : [];
  return NEWS_SECTIONS.filter((section) => schools.some((school) => school && Array.isArray(school.sections) && school.sections.includes(section)));
}

function filterSection(filter) {
  return String(filter || "").startsWith("section:") ? String(filter).slice(8) : "";
}

function newsFilterOptions(items) {
  const options = linkedNewsSections().map((section) => ({ value: `section:${section}`, label: t(`news.section.${section}`), own: true }));
  const categories = new Map();
  for (const item of items) {
    const slug = String(item.category_slug || "").trim();
    if (!newsSection(item) && slug && !categories.has(slug)) categories.set(slug, String(item.category || slug).trim() || slug);
  }
  const sorted = [...categories.entries()].sort((left, right) => left[1].localeCompare(right[1], currentLanguage(), { sensitivity: "base", numeric: true }));
  for (const [slug, label] of sorted) options.push({ value: `category:${slug}`, label, own: false });
  return options;
}

function newsInFilter(item, filter) {
  if (newsSection(item)) return newsSection(item) === filterSection(filter);
  if (!filter) return true;
  if (filter.startsWith("category:")) return String(item.category_slug || "") === filter.slice(9);
  return false;
}

function newsMatches(item, query) {
  const detail = newsDetailOf(item);
  const lines = detail && Array.isArray(detail.text) ? detail.text : [];
  const haystack = [item.title, item.summary, item.category, item.category_slug, ...lines].map((part) => String(part || "")).join(" ").toLowerCase();
  return haystack.includes(query);
}

function newsSectionState(section) {
  const sections = state.newsSections || {};
  return sections[section] || null;
}

async function loadNewsSection(section) {
  state.newsSections = Object.assign({}, state.newsSections, { [section]: { loading: true } });
  let entry = null;
  try {
    const data = await getJson(`api/news/section?${new URLSearchParams({ section })}`);
    entry = { data, at: Date.now() };
  } catch (error) {
    if (handleApiFailure(error)) return;
    entry = { error: true, at: Date.now() };
  }
  state.newsSections = Object.assign({}, state.newsSections, { [section]: entry });
  if (state.view === "news") rerender();
}

function ensureNewsSection(section) {
  const current = newsSectionState(section);
  if (current && (current.loading || (current.data && Date.now() - current.at < NEWS_SECTION_SECONDS * 1000))) return;
  loadNewsSection(section);
}

function setNewsFilter(value) {
  state.newsFilter = value;
  const section = filterSection(value);
  if (section) ensureNewsSection(section);
  discardSheet();
}

function newsFilterSheet() {
  const options = newsFilterOptions(listedNews());
  const row = (value, label, own, hint) => el("div", { class: "opt", "aria-pressed": String((state.newsFilter || "") === value) }, [
    el("button", { class: "opt-main news-filter-opt", type: "button", onclick: () => setNewsFilter(value) }, [
      icon(value === "section:archive" ? "archive" : "news", 20),
      el("span", {}, [own ? el("b", {}, label) : iservText("b", {}, label), hint ? el("small", {}, hint) : null]),
    ]),
  ]);
  const rows = [row("", t("news.filter.all"), true, t("news.filter.allHint"))].concat(options.map((option) => row(option.value, option.label, option.own, "")));
  return sheet(t("news.filter.title"), [el("div", { class: "opt-list" }, rows)]);
}

function newsFilterLabel(options) {
  const chosen = options.find((option) => option.value === state.newsFilter);
  if (!chosen) return el("span", { class: "chip-label" }, t("news.filter.all"));
  return chosen.own ? el("span", { class: "chip-label" }, chosen.label) : iservText("span", { class: "chip-label" }, chosen.label);
}

function newsSectionItems(section) {
  const current = newsSectionState(section);
  const listed = current && current.data && Array.isArray(current.data.news) ? current.data.news : [];
  return listed.filter((item) => item && typeof item === "object" && newsSection(item) === section);
}

function newsView() {
  const view = el("div", { class: "school-list" });
  const data = state.news;
  if (!data) {
    view.append(loadingBlock());
    return view;
  }
  const items = currentNews();
  if (data.error || listUnknown(data, items.length)) {
    view.append(listFailure("news", () => { state.news = null; rerender(); loadNews(); }));
    return view;
  }
  const note = refreshFailureNote("news");
  if (note) view.append(note);
  const options = newsFilterOptions(items);
  if (!items.length && !options.length) {
    view.append(emptyBlock("news", t("news.empty.title"), t("news.empty.text")));
    return view;
  }
  if (state.newsFilter && !options.some((option) => option.value === state.newsFilter)) state.newsFilter = "";
  const section = filterSection(state.newsFilter);
  if (section) ensureNewsSection(section);
  const head = el("div", { class: "list-head news-head" });
  if (options.length) {
    head.append(el("div", { class: "chipbar" }, [
      el("button", { class: "chip chip-filter news-filter", type: "button", "aria-pressed": String(!!state.newsFilter), onclick: () => openSheet(newsFilterSheet) }, [
        icon("filter", 14),
        newsFilterLabel(options),
      ]),
    ]));
  }
  const hits = el("span", { class: "search-hits" });
  const host = el("div", {});
  const sectionState = section ? newsSectionState(section) : null;
  const renderBody = () => {
    if (section && (!sectionState || sectionState.loading)) {
      hits.textContent = "";
      host.replaceChildren(loadingBlock());
      return;
    }
    if (section && sectionState.error) {
      hits.textContent = "";
      host.replaceChildren(emptyBlock("alert", t("news.error.title"), t("news.section.failed"), retryButton(() => loadNewsSection(section))));
      return;
    }
    const query = String(state.newsSearch || "").trim().toLowerCase();
    const pool = section ? newsSectionItems(section) : items;
    const shown = pool.filter((item) => newsInFilter(item, state.newsFilter) && (!query || newsMatches(item, query)));
    hits.textContent = query ? tCount("common.hits", shown.length) : "";
    if (!shown.length && !query && !state.newsFilter) {
      host.replaceChildren(emptyBlock("news", t("news.empty.title"), t("news.empty.text")));
      return;
    }
    host.replaceChildren(shown.length
      ? el("div", { class: "rows" }, shown.map(newsRow))
      : emptyBlock("search", t("news.search.emptyTitle"), t(query ? "news.search.emptyText" : "news.filter.emptyText")));
  };
  head.append(searchField(state.newsSearch, t("news.search.placeholder"), (value) => {
    state.newsSearch = value;
    renderBody();
  }, hits));
  view.append(head, host);
  renderBody();
  return view;
}
