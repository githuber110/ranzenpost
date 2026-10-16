const TASK_FILE_MAX_BYTES = 50 * 1024 * 1024;
const TASK_TOTAL_MAX_BYTES = 100 * 1024 * 1024;
const TASK_MAX_FILES = 20;
const TASK_MEGABYTE = 1024 * 1024;
const TASK_TEXT_MAX_LENGTH = 50000;
const TASK_SECTIONS = [["feedback", "tasks.detail.feedback"], ["solution", "tasks.detail.solution"]];

function taskKey(task) {
  return `${task.connection_id || ""}:${task.id || ""}`;
}

function taskOpenState(task) {
  const open = state.taskOpen;
  return open && open.key === taskKey(task) ? open : null;
}

function taskDetailOf(task) {
  const cached = state.taskDetails && state.taskDetails[taskKey(task)];
  if (cached && typeof cached === "object") return cached;
  return task.detail && typeof task.detail === "object" ? task.detail : null;
}

function keepTaskDetail(task, detail) {
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return;
  state.taskDetails = Object.assign({}, state.taskDetails, { [taskKey(task)]: detail });
}

function openTask(task) {
  state.taskOpen = { key: taskKey(task), loading: !!task.path, failed: "", busy: "", outcome: null, failure: "" };
  const detail = { kind: "task", item: task };
  if (detailPlacement(detail.kind, layoutMode(), state.view) === "pane") openDetail(detail);
  else openSheet(detailSheetFactory(detail));
  if (task.path) loadTaskDetail(task);
}

function taskQuery(task, extra) {
  return new URLSearchParams(Object.assign({ connection: task.connection_id || "", task: String(task.id || "") }, extra || {}));
}

async function loadTaskDetail(task) {
  const key = taskKey(task);
  let detail = null;
  try {
    detail = await getJson(`api/tasks/detail?${taskQuery(task)}`);
  } catch (error) {
    const open = state.taskOpen;
    if (!open || open.key !== key) return;
    open.loading = false;
    if (handleApiFailure(error, task.connection_id)) return;
    const body = error && error.body;
    open.failed = body && body.message_key ? t(body.message_key, body.message_vars) : t("tasks.detail.failed");
    rerender();
    return;
  }
  keepTaskDetail(task, detail);
  const open = state.taskOpen;
  if (open && open.key === key) {
    open.loading = false;
    open.failed = "";
  }
  rerender();
}

function taskFacts(facts) {
  return el("div", { class: "field-group task-facts" }, facts.map((fact) =>
    el("div", { class: "cell" }, [
      iservText("div", { class: "field-label" }, fact.label),
      iservText("div", { class: "fact" }, fact.value),
    ])
  ));
}

function squash(value) {
  return String(value || "").replace(/[\s,;]+/g, "").toLowerCase();
}

function shownFacts(detail) {
  const known = [detail.start_text, detail.due_text, detail.state_text].map(squash).filter(Boolean);
  const tags = squash((Array.isArray(detail.tags) ? detail.tags : []).join(""));
  return (Array.isArray(detail.facts) ? detail.facts : []).filter((fact) => {
    if (!fact || typeof fact !== "object" || !String(fact.value || "").trim()) return false;
    const value = squash(fact.value);
    return !known.includes(value) && !(tags && value === tags);
  });
}

function taskFileRows(task, kind, entries) {
  const files = [];
  (Array.isArray(entries) ? entries : []).forEach((entry, index) => {
    if (!entry || typeof entry !== "object") return;
    const label = String(entry.label || "").trim();
    const fromSchool = typeof entry.path === "string" && entry.path.startsWith("/");
    const address = typeof entry.url === "string" ? entry.url.trim() : "";
    files.push({
      filename: label || address || t("common.attachment"),
      sub: String(entry.meta || "").trim() || (!fromSchool && address && address !== label ? address : ""),
      url: fromSchool ? `api/tasks/file?${taskQuery(task, { kind, index: String(index) })}` : "",
    });
  });
  return files.length ? attachmentRows(files) : null;
}

function textLines(lines) {
  const kept = (Array.isArray(lines) ? lines : []).map((line) => String(line || "").trim()).filter(Boolean);
  return kept.length ? el("div", { class: "body-html news-text", dir: "auto" }, kept.map((line) => iservText("p", {}, line))) : null;
}

function sectionHead(key) {
  return el("div", { class: "section-head news-section" }, [el("span", { class: "overline" }, t(key))]);
}

function taskMeta(task, detail) {
  const facts = [];
  const due = listMoment((detail && detail.due) || task.due, (detail && detail.due_text) || task.due_text);
  const start = listMoment((detail && detail.start) || task.start, (detail && detail.start_text) || task.start_text);
  if (due) facts.push(t("tasks.due", { date: due }));
  if (start) facts.push(t("tasks.start", { date: start }));
  const stateText = String((detail && detail.state_text) || "").trim() || taskState(task);
  if (stateText) facts.push(stateText);
  if (taskOverdue(task, new Date())) facts.push(t("tasks.overdue"));
  return facts.join(" · ");
}

function taskTags(task, detail) {
  const own = (Array.isArray(task.tags) && task.tags.length ? task.tags : (detail && Array.isArray(detail.tags) ? detail.tags : []))
    .filter((tag) => typeof tag === "string" && tag);
  return [schoolTag(task)].concat(own.map((tag) => iservText("span", { class: "tag" }, tag))).filter(Boolean);
}

function taskStatus(task, detail, open) {
  if (!open) return null;
  if (open.loading) return detail ? el("div", { class: "stamp", role: "status" }, t("tasks.detail.updating")) : loadingBlock();
  if (open.failed) {
    return el("div", { class: "task-failed" }, [
      noteBlock(detail ? t("tasks.detail.stale", { reason: open.failed }) : open.failed),
      el("button", { class: "btn ghost slim", type: "button", onclick: () => { open.loading = true; open.failed = ""; rerender(); loadTaskDetail(task); } }, t("common.retry")),
    ]);
  }
  return null;
}

function taskOutcomeNote(outcome) {
  if (!outcome) return null;
  const errors = (Array.isArray(outcome.errors) ? outcome.errors : []).map((line) => String(line || "").trim()).filter(Boolean);
  const text = el("div", { class: "task-outcome-text" }, [
    el("span", {}, outcome.text),
    ...errors.map((line) => iservText("div", { class: "task-outcome-error" }, line)),
  ]);
  if (outcome.kind === "done") return el("div", { class: "note info task-outcome", role: "status" }, [icon("check", 16), text]);
  return el("div", { class: "note task-outcome", role: "status" }, [icon("alert", 16), text]);
}

function taskDeletions(detail) {
  const actions = (detail && detail.actions) || {};
  const files = ((detail && detail.submission) || {}).files || [];
  return (Array.isArray(actions.delete) ? actions.delete : [])
    .filter((entry) => entry && typeof entry.form === "string")
    .map((entry) => {
      const file = Number.isInteger(entry.file) && entry.file >= 0 ? files[entry.file] : null;
      return Object.assign({}, entry, { name: String(entry.label || (file && file.label) || "").trim() || t("common.attachment") });
    });
}

function taskOwnText(detail) {
  const actions = (detail && detail.actions) || {};
  if (actions.text && Array.isArray(actions.text.text)) return actions.text.text;
  return ((detail && detail.submission) || {}).text || [];
}

function taskActionButtons(task, detail, open) {
  const actions = (detail && detail.actions) || {};
  const entries = [];
  const hasText = taskOwnText(detail).some((line) => String(line || "").trim());
  if (actions.upload) entries.push(["upload", t("tasks.act.upload"), () => openTaskUpload(task), true]);
  if (actions.text) entries.push(["text", t(hasText ? "tasks.act.editText" : "tasks.act.text"), () => openTaskText(task), true]);
  if (actions.confirm) entries.push(["confirm", t("tasks.act.confirm"), () => openTaskMark(task, "confirm"), true]);
  if (actions.undo) entries.push(["undo", t("tasks.act.undo"), () => openTaskMark(task, "undo"), false]);
  if (taskDeletions(detail).length) entries.push(["delete", t("tasks.act.remove"), () => openTaskRemove(task), false]);
  if (!entries.length) return null;
  const blocked = !!(open && (open.busy || open.loading));
  const primary = entries.findIndex((entry) => entry[3]);
  return el("div", { class: "btn-stack task-actions" }, entries.map(([kind, label, run], index) =>
    el("button", {
      class: index === primary ? `btn task-act-${kind}` : `btn ghost task-act-${kind}`,
      type: "button",
      disabled: blocked ? "" : null,
      onclick: () => { if (!blocked) run(); },
    }, label)
  ));
}

function taskSubmissionNodes(task, detail, open) {
  const submission = (detail && detail.submission) || {};
  const nodes = [];
  const outcome = open ? taskOutcomeNote(open.outcome) : null;
  const files = taskFileRows(task, "submission", submission.files);
  const own = textLines(taskOwnText(detail));
  const facts = shownFacts({ facts: submission.facts });
  const extra = textLines(detail && detail.actions && detail.actions.text ? submission.text : []);
  const buttons = taskActionButtons(task, detail, open);
  if (!outcome && !files && !own && !facts.length && !extra && !buttons) return nodes;
  nodes.push(sectionHead("tasks.detail.submission"));
  if (outcome) nodes.push(outcome);
  if (facts.length) nodes.push(taskFacts(facts));
  if (files) nodes.push(files);
  if (own) nodes.push(el("div", { class: "task-own-text" }, [el("div", { class: "field-label" }, t("tasks.detail.ownText")), own]));
  if (extra) nodes.push(extra);
  if (buttons) nodes.push(buttons);
  else if (detail && !(open && open.loading)) nodes.push(el("p", { class: "sheet-hint" }, t("tasks.detail.noHandIn")));
  if (detail && Number(detail.unrecognised) > 0 && !(open && open.loading)) nodes.push(el("p", { class: "sheet-hint task-unrecognised" }, t("tasks.detail.unrecognised")));
  return nodes;
}

function taskSectionNodes(task, detail, field, key) {
  const section = detail && detail[field];
  if (!section || typeof section !== "object") return [];
  const facts = shownFacts({ facts: section.facts });
  const text = textLines(section.text);
  const files = taskFileRows(task, field, section.files);
  const links = newsTextRows(section.links);
  if (!facts.length && !text && !files && !links) return [];
  return [sectionHead(key), facts.length ? taskFacts(facts) : null, text, files, links].filter(Boolean);
}

function taskDetailParts(task) {
  const detail = taskDetailOf(task);
  const open = taskOpenState(task);
  const body = [];
  const tags = taskTags(task, detail);
  if (tags.length) body.push(el("div", { class: "row-tags" }, tags));
  const meta = taskMeta(task, detail);
  if (meta) body.push(el("div", { class: "row-meta news-meta" }, meta));
  const status = taskStatus(task, detail, open);
  if (status) body.push(status);
  if (detail) {
    const text = textLines(detail.text);
    if (text) body.push(text);
    const facts = shownFacts(detail);
    if (facts.length) body.push(taskFacts(facts));
    const files = taskFileRows(task, "files", detail.files);
    if (files) body.push(sectionHead("news.detail.files"), files);
    const images = taskFileRows(task, "images", detail.images);
    if (images) body.push(sectionHead("news.detail.images"), images);
    const links = newsTextRows(detail.links);
    if (links) body.push(sectionHead("news.detail.links"), links);
  } else {
    const extra = (Array.isArray(task.extra) ? task.extra : []).filter((entry) => entry && String(entry.value || "").trim());
    if (extra.length) body.push(taskFacts(extra.map((entry) => ({ label: entry.label || "", value: String(entry.value) }))));
    if (!task.path) body.push(noteBlock(t("tasks.detail.noPage")));
  }
  body.push(...taskSubmissionNodes(task, detail, open));
  for (const [field, key] of TASK_SECTIONS) body.push(...taskSectionNodes(task, detail, field, key));
  return { title: task.title || t("tasks.untitled"), body, foot: null, extra: null };
}

function taskActBody(task, action, form, extra) {
  return Object.assign({ connection_id: task.connection_id || "", task_id: String(task.id || ""), action, form, confirmed: true }, extra || {});
}

function taskFailure(open, result, fallback) {
  open.failure = apiMessage(result, fallback);
  toast(open.failure, "bad");
}

function finishTaskAction(task, result) {
  const open = taskOpenState(task);
  if (!open) return;
  open.busy = "";
  if (result && result.detail) keepTaskDetail(task, result.detail);
  if (result && !result.ok && !result.outcome && result.message_key) {
    taskFailure(open, result, "tasks.act.failed");
    rerender();
    return;
  }
  if (!result || (!result.ok && !result.outcome)) {
    open.outcome = { kind: "uncertain", text: t("api.tasks.act.uncertain"), errors: [] };
    open.loading = true;
    loadTaskDetail(task);
  } else {
    open.outcome = {
      kind: result.ok ? "done" : String(result.outcome || "failed"),
      text: apiMessage(result, result.ok ? "api.tasks.act.done" : "tasks.act.failed"),
      errors: Array.isArray(result.errors) ? result.errors : [],
    };
  }
  open.failure = "";
  toast(open.outcome.text, open.outcome.kind === "done" ? "good" : "bad");
  discardSheet();
  if (result && result.ok) loadTasks();
}

async function sendTaskAction(task, action, form, extra, files) {
  const open = taskOpenState(task);
  if (!open || open.busy) return;
  open.busy = action;
  open.failure = "";
  rerender();
  let result = null;
  try {
    const body = taskActBody(task, action, form, extra);
    result = files ? await postFormData("api/tasks/act", body, files) : await postJson("api/tasks/act", body, UPLOAD_TIMEOUT_MS);
  } catch (error) {
    open.busy = "";
    if (handleApiFailure(error, task.connection_id)) return;
    result = null;
  }
  finishTaskAction(task, result);
}

function taskActionOf(task, kind) {
  const detail = taskDetailOf(task);
  const actions = (detail && detail.actions) || {};
  return actions[kind] && typeof actions[kind].form === "string" ? actions[kind] : null;
}

function busyLabel(open, kind, label) {
  return [open && open.busy === kind ? el("span", { class: "spin" }) : null, label];
}

function taskGoneSheet(title) {
  return sheet(title, [noteBlock(t("api.tasks.act.unavailable"))]);
}

function openTaskUpload(task) {
  const open = taskOpenState(task);
  if (!open) return;
  open.upload = { files: [], preview: false };
  open.failure = "";
  openNestedSheet(() => taskUploadSheet(task));
}

function uploadProblem(action, files) {
  if (!files.length) return "empty";
  if (files.some((file) => file.size > TASK_FILE_MAX_BYTES)) return "large";
  if (!action.multiple && files.length > 1) return "one";
  if (files.length > TASK_MAX_FILES) return "many";
  if (files.reduce((sum, file) => sum + (Number(file.size) || 0), 0) > TASK_TOTAL_MAX_BYTES) return "total";
  return "";
}

function uploadProblemNote(problem) {
  if (problem === "one") return noteBlock(t("api.tasks.act.oneFile"));
  if (problem === "many") return noteBlock(t("api.tasks.act.tooMany", { max: formatNumber(TASK_MAX_FILES) }));
  if (problem === "total") return noteBlock(t("api.tasks.act.tooLarge", { max: formatNumber(TASK_TOTAL_MAX_BYTES / TASK_MEGABYTE) }));
  return null;
}

function taskUploadSheet(task) {
  const open = taskOpenState(task);
  const action = taskActionOf(task, "upload");
  if (!open || !action || !open.upload) return taskGoneSheet(t("tasks.act.upload"));
  const draft = open.upload;
  const sending = open.busy === "upload";
  if (draft.preview) {
    const body = [
      iservText("p", { class: "dlg-text" }, t("tasks.upload.previewText", { title: task.title || t("tasks.untitled") })),
      el("div", { class: "rows" }, draft.files.map(({ name, size }) => el("div", { class: "row read disabled" }, attachmentRowContent(name, formatBytes(size))))),
    ];
    if (open.failure) body.push(noteBlock(open.failure));
    return sheet(t("tasks.act.upload"), body, [el("div", { class: "btn-stack" }, [
      el("button", { class: "btn task-upload-send", type: "button", disabled: sending ? "" : null, onclick: () => sendTaskAction(task, "upload", action.form, {}, draft.files) }, busyLabel(open, "upload", t("tasks.upload.send"))),
      el("button", { class: "btn ghost", type: "button", disabled: sending ? "" : null, onclick: () => { draft.preview = false; open.failure = ""; rerender(); } }, t("tasks.upload.back")),
    ])]);
  }
  const input = el("input", { type: "file", class: "task-upload-input", hidden: "" });
  if (action.multiple) input.multiple = true;
  if (action.accept) input.accept = action.accept;
  input.addEventListener("change", () => {
    const chosen = Array.from(input.files || []);
    draft.files = action.multiple ? draft.files.concat(chosen) : chosen.slice(0, 1);
    input.value = "";
    rerender();
  });
  const rows = draft.files.map((file, index) => {
    const fileLabel = file.name || "";
    const remove = el("button", { class: "search-clear", type: "button", "aria-label": t("tasks.upload.drop", { name: fileLabel }) }, [icon("close", 14)]);
    remove.addEventListener("click", () => {
      draft.files.splice(index, 1);
      rerender();
    });
    const large = file.size > TASK_FILE_MAX_BYTES;
    return el("div", { class: "row read disabled" }, [
      el("span", { class: "row-dot" }, [icon("clip", 14)]),
      el("div", { class: "row-main" }, [
        iservText("div", { class: "row-title full" }, fileLabel),
        el("div", { class: large ? "row-sub task-file-large" : "row-sub" }, large ? t("tasks.upload.tooLarge") : formatBytes(file.size)),
      ]),
      remove,
    ]);
  });
  const problem = uploadProblem(action, draft.files);
  const add = el("button", { class: "btn ghost slim task-upload-add", type: "button" }, [icon("plus", 14), t(action.multiple ? "tasks.upload.add" : "tasks.upload.choose")]);
  add.addEventListener("click", () => input.click());
  const body = [
    el("p", { class: "dlg-text" }, t(action.multiple ? "tasks.upload.text" : "tasks.upload.textOne")),
    action.accept ? iservText("p", { class: "sheet-hint" }, t("tasks.upload.accept", { types: action.accept })) : null,
    rows.length ? el("div", { class: "rows" }, rows) : null,
    uploadProblemNote(problem),
    add,
    input,
  ].filter(Boolean);
  return sheet(t("tasks.act.upload"), body, [el("div", { class: "btn-stack" }, [
    el("button", { class: "btn task-upload-next", type: "button", disabled: problem ? "" : null, onclick: () => { if (!uploadProblem(action, draft.files)) { draft.preview = true; rerender(); } } }, t("tasks.upload.next")),
  ])]);
}

function formatBytes(size) {
  const value = Number(size) || 0;
  const large = value >= 1024 * 1024;
  const amount = large ? value / (1024 * 1024) : Math.max(1, value / 1024);
  return new Intl.NumberFormat(currentLanguage(), { style: "unit", unit: large ? "megabyte" : "kilobyte", maximumFractionDigits: large ? 1 : 0 }).format(amount);
}

function openTaskText(task) {
  const open = taskOpenState(task);
  const action = taskActionOf(task, "text");
  if (!open || !action) return;
  open.failure = "";
  const current = (Array.isArray(action.text) ? action.text : []).join("\n");
  openNestedSheet(() => taskTextSheet(task, current));
}

function taskTextLimit(action) {
  const limit = Number(action.max_length) || 0;
  return limit > 0 ? Math.min(limit, TASK_TEXT_MAX_LENGTH) : TASK_TEXT_MAX_LENGTH;
}

function taskTextSheet(task, current) {
  const open = taskOpenState(task);
  const action = taskActionOf(task, "text");
  if (!open || !action) return taskGoneSheet(t("tasks.act.text"));
  const draft = sheetState(() => ({ text: current, preview: false }));
  const sending = open.busy === "text";
  if (draft.preview) {
    const body = [
      iservText("p", { class: "dlg-text" }, t("tasks.text.previewText", { title: task.title || t("tasks.untitled") })),
      el("blockquote", { class: "dlg-quote task-text-quote", dir: "auto" }, draft.text.trim()),
    ];
    if (open.failure) body.push(noteBlock(open.failure));
    return sheet(t("tasks.act.text"), body, [el("div", { class: "btn-stack" }, [
      el("button", { class: "btn task-text-send", type: "button", disabled: sending ? "" : null, onclick: () => sendTaskAction(task, "text", action.form, { text: draft.text.trim() }) }, busyLabel(open, "text", t("tasks.text.send"))),
      el("button", { class: "btn ghost", type: "button", disabled: sending ? "" : null, onclick: () => { draft.preview = false; open.failure = ""; rerender(); } }, t("tasks.text.edit")),
    ])]);
  }
  const field = el("textarea", { class: "inp task-text-field", dir: "auto", rows: "8", maxlength: String(taskTextLimit(action)), "aria-label": t("tasks.text.label") });
  field.value = draft.text;
  const next = el("button", {
    class: "btn task-text-next",
    type: "button",
    disabled: draft.text.trim() ? null : "",
    onclick: () => {
      if (!draft.text.trim()) return;
      draft.preview = true;
      rerender();
    },
  }, t("tasks.text.next"));
  field.addEventListener("input", () => {
    draft.text = field.value;
    next.disabled = !draft.text.trim();
  });
  window.setTimeout(() => { if (field.isConnected) field.focus(); }, 0);
  return sheet(t("tasks.act.text"), [
    el("p", { class: "dlg-text" }, t("tasks.text.text")),
    el("label", { class: "field" }, [el("span", { class: "lbl" }, t("tasks.text.label")), field]),
  ], [el("div", { class: "btn-stack" }, [next])]);
}

function openTaskMark(task, kind) {
  const open = taskOpenState(task);
  if (!open || !taskActionOf(task, kind)) return;
  open.failure = "";
  openNestedSheet(() => taskMarkSheet(task, kind));
}

function taskMarkSheet(task, kind) {
  const open = taskOpenState(task);
  const action = taskActionOf(task, kind);
  const title = t(kind === "confirm" ? "tasks.act.confirm" : "tasks.act.undo");
  if (!open || !action) return taskGoneSheet(title);
  const sending = open.busy === kind;
  const body = [iservText("p", { class: "dlg-text" }, t(kind === "confirm" ? "tasks.confirm.text" : "tasks.undo.text", { title: task.title || t("tasks.untitled") }))];
  if (open.failure) body.push(noteBlock(open.failure));
  return sheet(title, body, [el("div", { class: "btn-stack" }, [
    el("button", { class: `btn task-${kind}-send`, type: "button", disabled: sending ? "" : null, onclick: () => sendTaskAction(task, kind, action.form, {}) }, busyLabel(open, kind, title)),
    el("button", { class: "btn ghost", type: "button", disabled: sending ? "" : null, onclick: () => discardSheet() }, t("common.cancel")),
  ])]);
}

function openTaskRemove(task) {
  const open = taskOpenState(task);
  const choices = taskDeletions(taskDetailOf(task));
  if (!open || !choices.length) return;
  open.failure = "";
  open.remove = choices.length === 1 ? choices[0] : null;
  openNestedSheet(() => taskRemoveSheet(task));
}

function taskRemoveSheet(task) {
  const open = taskOpenState(task);
  const choices = taskDeletions(taskDetailOf(task));
  const title = t("tasks.act.remove");
  if (!open || !choices.length) return taskGoneSheet(title);
  const chosen = open.remove;
  const sending = open.busy === "delete";
  if (chosen) {
    const body = [iservText("p", { class: "dlg-text" }, t("tasks.remove.text", { name: chosen.name }))];
    if (open.failure) body.push(noteBlock(open.failure));
    return sheet(title, body, [el("div", { class: "btn-stack" }, [
      el("button", { class: "btn destructive task-remove-send", type: "button", disabled: sending ? "" : null, onclick: () => sendTaskAction(task, "delete", chosen.form, { target: chosen.target, target_label: String(chosen.label || ""), target_value: String(chosen.value || "") }) }, busyLabel(open, "delete", t("tasks.remove.send"))),
      el("button", {
        class: "btn ghost",
        type: "button",
        disabled: sending ? "" : null,
        onclick: () => {
          if (choices.length === 1) return discardSheet();
          open.remove = null;
          open.failure = "";
          rerender();
        },
      }, t(choices.length === 1 ? "common.cancel" : "tasks.upload.back")),
    ])]);
  }
  return sheet(title, [
    el("p", { class: "dlg-text" }, t("tasks.remove.choose")),
    el("div", { class: "rows" }, choices.map((choice) => el("button", {
      class: "row task-remove-row",
      type: "button",
      onclick: () => { open.remove = choice; rerender(); },
    }, [
      el("span", { class: "row-dot" }, [icon("trash", 14)]),
      el("div", { class: "row-main" }, [iservText("div", { class: "row-title full" }, choice.name)]),
    ]))),
  ]);
}
