const MARK_NAMES_KEY = "markNames";
const MARK_NAME_CHIPS = 12;
const MARK_MAX_NAME_LENGTH = 60;
const MARK_STATE_SUBSTITUTED = "substituted";
const MARK_STATE_CANCELLED = "cancelled";
const MARK_CLARIFY_KEYS = {
  cancelled: { title: "marks.clarify.cancelled.title", text: "marks.clarify.cancelled.text" },
  foreign: { title: "marks.clarify.foreign.title", text: "marks.clarify.foreign.text" },
  orphaned: { title: "marks.clarify.orphaned.title", text: "marks.clarify.orphaned.text" },
};

function markAddButton(childId, lesson, time) {
  return el("button", { class: "btn mark-add", type: "button", onclick: () => openMarkForm(childId, lesson, time, null) }, [
    icon("plus", 18),
    el("span", {}, t("marks.action.add")),
  ]);
}

function markChildOf(childId) {
  return childId || state.childId || "";
}

function markList() {
  const box = state.marks;
  return box && box.data && Array.isArray(box.data.marks) ? box.data.marks : [];
}

async function loadMarks() {
  const keep = !!(state.marks && !state.marks.error);
  const outcome = await reload("marks", () => getJson("api/marks"), keep);
  if (!outcome) return;
  if (outcome.data) state.marks = { data: outcome.data };
  else if (outcome.error) state.marks = { error: outcome.error };
  rerender();
}

function lessonIso(lesson) {
  const parsed = parseAnyDate(lesson && lesson.date);
  return parsed ? isoDate(parsed) : "";
}

function plainCode(value) {
  return String(value || "").split(/\s+/).filter(Boolean).join(" ");
}

function lessonMatchesCode(lesson, code) {
  const wanted = plainCode(code);
  return !!wanted && !!lesson && [lesson.subject_key, lesson.subject_code, lesson.subject_label].some((value) => plainCode(value) === wanted);
}

function slotEntryFor(entries, childId, iso, period, lesson) {
  if (!childId || !iso) return null;
  const inSlot = entries.filter((entry) => entry.child_key === childId && entry.date === iso && Number(entry.period) === Number(period));
  if (!lesson) return inSlot[0] || null;
  return inSlot.find((entry) => lessonMatchesCode(lesson, entry.subject_code))
    || inSlot.find((entry) => !plainCode(entry.subject_code))
    || null;
}

function markAt(childId, iso, period, lesson) {
  return slotEntryFor(markList(), childId, iso, period, lesson);
}

function cancellationList() {
  const box = state.cancellations;
  return box && box.data && Array.isArray(box.data.cancellations) ? box.data.cancellations : [];
}

async function loadCancellations() {
  const keep = !!(state.cancellations && !state.cancellations.error);
  const outcome = await reload("cancellations", () => getJson("api/cancellations"), keep);
  if (!outcome) return;
  if (outcome.data) state.cancellations = { data: outcome.data };
  else if (outcome.error) state.cancellations = { error: outcome.error };
  rerender();
}

function cancellationAt(childId, iso, period, lesson) {
  return slotEntryFor(cancellationList(), childId, iso, period, lesson);
}

function cancellationOfLesson(lesson, childId) {
  return cancellationAt(markChildOf(childId), lessonIso(lesson), lesson && lesson.period, lesson);
}

function lessonDropped(lesson, childId) {
  return lesson.change_kind === "cancelled" || !!cancellationOfLesson(lesson, childId);
}

function displayChangeKind(lesson, childId) {
  if (lesson.change_kind) return lesson.change_kind;
  return cancellationOfLesson(lesson, childId) ? "cancelled" : "";
}

function cancellationRequest(path, options) {
  return jsonRequest(path, options, "timetable.cancel.error");
}

async function runCancellationAction(request, doneKey) {
  const outcome = await request();
  if (!outcome.ok) {
    toast(outcome.message, "bad");
    return false;
  }
  discardSheet();
  await loadCancellations();
  toast(t(doneKey));
  return true;
}

function addCancellation(childId, lesson) {
  const anchor = markLessonAnchor(lesson, markChildOf(childId));
  if (!anchor) return Promise.resolve(false);
  return runCancellationAction(
    () => cancellationRequest("api/cancellations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ child_key: anchor.child_key, date: anchor.date, period: anchor.period, subject_code: anchor.subject_code }),
    }),
    "timetable.cancel.toast.saved"
  );
}

function removeCancellation(cancellation) {
  return runCancellationAction(
    () => cancellationRequest(`api/cancellations/${encodeURIComponent(cancellation.id)}`, { method: "DELETE" }),
    "timetable.cancel.toast.removed"
  );
}

function cancellationPanel() {
  return el("div", { class: "mark-clarify", role: "group", "aria-label": t("timetable.cancel.title") }, [
    el("div", { class: "mark-clarify-head" }, [icon("alert", 16), el("b", {}, t("timetable.cancel.title"))]),
    el("p", { class: "mark-clarify-text" }, t("timetable.cancel.hint")),
  ]);
}

function markLessonAnchor(lesson, childId) {
  const iso = lessonIso(lesson);
  if (!iso || !childId) return null;
  const period = Number(lesson.period);
  if (!Number.isInteger(period) || period <= 0) return null;
  const subject = String(lesson.subject_key || "") || lessonSubjectKey(lesson);
  return subject ? { child_key: childId, date: iso, period, subject_code: subject } : null;
}

function markOfLesson(lesson, childId) {
  return markAt(markChildOf(childId), lessonIso(lesson), lesson && lesson.period, lesson);
}

function markLabel(mark) {
  return (mark && mark.name) || t("marks.default");
}

function markSubjectLabel(mark) {
  const code = (mark && mark.subject_code) || "";
  const subjects = connectionConfig(connectionOfKey(mark && mark.child_key) || currentConnectionId()).subjects || {};
  const stored = subjects[code];
  return (stored && stored.label) || code;
}

function markNeedsCheck(mark) {
  return !!(mark && MARK_CLARIFY_KEYS[mark.state]);
}

function marksOfDay(childId, iso) {
  return markList().filter((entry) => entry.child_key === childId && entry.date === iso);
}

function markNameHistory() {
  try {
    const parsed = JSON.parse(readStoredText(MARK_NAMES_KEY) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((value) => typeof value === "string" && value.trim()).slice(0, MARK_NAME_CHIPS);
  } catch (error) {
    return [];
  }
}

function storeMarkNames(names) {
  writeStoredText(MARK_NAMES_KEY, names.length ? JSON.stringify(names) : "");
}

function rememberMarkName(name) {
  const text = String(name || "").trim();
  if (!text) return;
  storeMarkNames([text].concat(markNameHistory().filter((value) => value !== text)).slice(0, MARK_NAME_CHIPS));
}

function forgetMarkName(name) {
  storeMarkNames(markNameHistory().filter((value) => value !== name));
}

function markPanel(mark, childId, lesson, time) {
  const rows = [
    el("div", { class: "cell mark-cell" }, [
      el("div", { class: "cell-head" }, [icon("exam", 16), el("span", { class: "field-label" }, t("marks.default"))]),
      iservText("div", { class: "mark-name" }, markLabel(mark)),
      mark.state === MARK_STATE_SUBSTITUTED
        ? el("p", { class: "mark-note" }, t("marks.state.substituted"))
        : null,
    ]),
  ];
  const panel = el("div", { class: "field-group mark-panel" }, rows);
  const clarify = markClarifyPanel(mark, childId, lesson, time);
  if (!clarify) return panel;
  return el("div", { class: "mark-block" }, [panel, clarify]);
}

function markClarifyPanel(mark, childId, lesson, time) {
  const keys = MARK_CLARIFY_KEYS[mark.state];
  if (!keys) return null;
  return el("div", { class: "mark-clarify", role: "group", "aria-label": t(keys.title) }, [
    el("div", { class: "mark-clarify-head" }, [icon("alert", 16), el("b", {}, t(keys.title))]),
    el("p", { class: "mark-clarify-text" }, t(keys.text)),
    el("div", { class: "btn-stack" }, [
      el("button", { class: "btn ghost", type: "button", onclick: keepMark }, t("marks.clarify.keep")),
      el("button", { class: "btn ghost", type: "button", onclick: () => openMarkMove(mark, childId) }, t("marks.clarify.move")),
      el("button", { class: "btn ghost destructive", type: "button", onclick: () => removeMark(mark) }, t("marks.clarify.remove")),
    ]),
  ]);
}

function openMarkSheet(mark, childId) {
  openSheet(() => markSheet(mark, markChildOf(childId)));
}

function markSheet(mark, childId) {
  const body = [
    el("p", { class: "dlg-text" }, t("marks.origin", {
      subject: markSubjectLabel(mark),
      period: formatNumber(mark.period),
    })),
  ];
  const clarify = markClarifyPanel(mark, childId, null, "");
  if (clarify) body.push(clarify);
  const foot = clarify
    ? null
    : [
      el("div", { class: "btn-stack" }, [
        el("button", { class: "btn ghost", type: "button", onclick: () => openMarkForm(childId, null, "", mark) }, t("marks.action.rename")),
        el("button", { class: "btn ghost destructive", type: "button", onclick: () => removeMark(mark) }, t("marks.action.remove")),
      ]),
    ];
  return sheet(markLabel(mark), body, foot);
}

function markDayLessons(childId, iso) {
  const weeks = [];
  if (state.timetable && childId === state.childId) weeks.push(state.timetable);
  const byChild = state.overviewWeeks[childId] || {};
  for (const key of Object.keys(byChild)) weeks.push(byChild[key]);
  const seen = new Set();
  const found = [];
  for (const week of weeks) {
    for (const lesson of (week && week.lessons) || []) {
      if (lessonIso(lesson) !== iso) continue;
      const key = `${lesson.period}:${lesson.subject_code}`;
      if (seen.has(key)) continue;
      seen.add(key);
      found.push(lesson);
    }
  }
  return found.sort((first, second) => Number(first.period) - Number(second.period));
}

function markMoveTargets(mark, childId) {
  return markDayLessons(childId, mark.date).filter((lesson) => {
    if (Number(lesson.period) === Number(mark.period) && lessonMatchesCode(lesson, mark.subject_code)) return false;
    if (displayChangeKind(lesson, childId) === MARK_STATE_CANCELLED) return false;
    if (!markLessonAnchor(lesson, childId)) return false;
    return !markAt(childId, mark.date, lesson.period, lesson);
  });
}

function openMarkMove(mark, childId) {
  openSheet(() => markMoveSheet(mark, markChildOf(childId)));
}

function markMoveSheet(mark, childId) {
  const targets = markMoveTargets(mark, childId);
  if (!targets.length) return sheet(t("marks.move.title"), [el("p", { class: "dlg-text" }, t("marks.move.empty"))]);
  const rows = targets.map((lesson) => {
    const label = t("marks.move.option", {
      period: formatNumber(lesson.period),
      subject: lesson.subject_label || lesson.subject_code || t("timetable.lesson.fallback"),
    });
    return el("button", { class: "row mark-target", type: "button", onclick: () => moveMark(mark, lesson) }, [
      el("span", { class: "row-dot" }, [el("i", {})]),
      el("div", { class: "row-main" }, [iservText("div", { class: "row-title" }, label)]),
      el("div", { class: "row-side" }, [el("span", { class: "row-meta" }, lessonTime(lesson) || periodShort(lesson.period))]),
    ]);
  });
  return sheet(t("marks.move.title"), [el("div", { class: "rows" }, rows)]);
}

function jsonRequest(path, options, fallbackKey) {
  return requestJson(path, options, fallbackKey);
}

function markRequest(path, options) {
  return jsonRequest(path, options, "marks.error.failed");
}

function markPost(path, body) {
  return markRequest(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

async function runMarkAction(request, doneKey) {
  const outcome = await request();
  if (!outcome.ok) {
    toast(outcome.message, "bad");
    return false;
  }
  discardSheet();
  await loadMarks();
  toast(t(doneKey));
  return true;
}

function keepMark() {
  discardSheet();
  toast(t("marks.clarify.kept"));
}

function removeMark(mark) {
  return runMarkAction(
    () => markRequest(`api/marks/${encodeURIComponent(mark.id)}`, { method: "DELETE" }),
    "marks.toast.removed"
  );
}

function moveMark(mark, lesson) {
  return runMarkAction(
    () => markPost(`api/marks/${encodeURIComponent(mark.id)}`, {
      period: Number(lesson.period),
      subject_code: lesson.subject_code || lesson.subject_label || "",
    }),
    "marks.toast.moved"
  );
}

function openMarkForm(childId, lesson, time, mark) {
  openSheet(() => markFormSheet(markChildOf(childId), lesson, time, mark));
}

function markFormContext(lesson, time, mark) {
  if (lesson) {
    const parts = [
      lesson.date ? showDate(lesson.date) : "",
      lessonPeriodFact(lesson, time),
      lesson.subject_label || lesson.subject_code || "",
      lesson.room ? t("timetable.room", { room: lesson.room }) : "",
    ];
    return parts.filter(Boolean).join(" · ");
  }
  return [showDate(mark.date), t("timetable.fact.periodValue", { period: formatNumber(mark.period) }), markSubjectLabel(mark)]
    .filter(Boolean)
    .join(" · ");
}

function markFormSheet(childId, lesson, time, mark) {
  const form = sheetState(() => ({ name: mark ? mark.name || "" : "" }));
  const input = el("input", {
    class: "inp",
    type: "text",
    value: form.name,
    placeholder: t("marks.form.placeholder"),
    autocomplete: "off",
    maxlength: String(MARK_MAX_NAME_LENGTH),
    "aria-label": t("marks.form.name"),
  });
  input.addEventListener("input", () => { form.name = input.value; });
  const submit = () => saveMark(childId, lesson, mark, form.name);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      submit();
    }
  });
  const body = [
    iservText("p", { class: "mark-context" }, markFormContext(lesson, time, mark)),
    markNameChips(form, input),
    el("div", { class: "field" }, [input]),
    el("p", { class: "mark-note" }, t("marks.form.hint")),
  ];
  const foot = [el("button", { class: "btn", type: "button", onclick: submit }, t(mark ? "common.save" : "marks.form.submit"))];
  window.setTimeout(() => { if (input.isConnected) input.focus(); }, 0);
  return sheet(t("marks.action.add"), body, foot);
}

function markNameChips(form, input) {
  const names = markNameHistory();
  if (!names.length) return null;
  const block = el("div", { class: "mark-chips" });
  const row = el("div", { class: "chip-row" });
  const entry = (name) => {
    const fill = el("button", {
      class: "chip mark-chip",
      type: "button",
      onclick: () => {
        form.name = name;
        input.value = name;
        input.focus();
      },
    }, [iservText("span", { class: "chip-label" }, name)]);
    const remove = el("button", {
      class: "mark-chip-remove",
      type: "button",
      "aria-label": t("marks.form.recentRemove", { name }),
    }, [icon("close", 14)]);
    const holder = el("div", { class: "mark-recent" }, [fill, remove]);
    remove.addEventListener("click", () => {
      forgetMarkName(name);
      const next = holder.nextElementSibling || holder.previousElementSibling;
      holder.remove();
      if (next) {
        next.querySelector(".mark-chip-remove").focus();
        return;
      }
      block.remove();
      input.focus();
    });
    return holder;
  };
  row.append(...names.map(entry));
  block.append(el("span", { class: "overline" }, t("marks.form.recent")), row);
  return block;
}

async function saveMark(childId, lesson, mark, name) {
  const anchor = mark ? null : markLessonAnchor(lesson, childId);
  if (!mark && !anchor) return false;
  const done = mark ? await runMarkAction(
    () => markPost(`api/marks/${encodeURIComponent(mark.id)}`, { name }),
    "marks.toast.updated"
  ) : await runMarkAction(
    () => markPost("api/marks", Object.assign({}, anchor, { name })),
    "marks.toast.saved"
  );
  if (done) rememberMarkName(name);
  return done;
}
