function absenceSchoolId() {
  const fromChild = currentConnectionId();
  if (fromChild) return fromChild;
  return state.absenceSchool && connectionOf(state.absenceSchool) ? state.absenceSchool : "";
}

function openAbsenceSchoolId() {
  return (state.absence && state.absence.connectionId) || absenceSchoolId();
}

function chooseAbsenceSchool(id) {
  state.absenceSchool = id;
  state.absence = null;
  rerender();
}

function absenceSchoolBlock() {
  const ids = readySchools().map((entry) => entry.id);
  const button = el("button", {
    class: "btn",
    type: "button",
    onclick: () => openSheet(() => schoolChoiceSheet(ids, state.absenceSchool || "", chooseAbsenceSchool)),
  }, t("schools.choose.action"));
  return emptyBlock("absence", t("schools.choose.title"), t("absence.school.text"), button);
}

async function loadAbsences() {
  const school = absenceSchoolId();
  if (!school && manySchools()) return;
  const keep = !!(state.absence && !state.absence.error && (!state.absence.connectionId || state.absence.connectionId === school));
  const outcome = await reload("absence", () => getJson(`api/absences?connection=${encodeURIComponent(school)}`), keep, school);
  if (!outcome) return;
  if (outcome.data) {
    state.absence = { data: outcome.data, connectionId: school };
    olderSettleSends(outcome.data, school);
  }
  else if (outcome.error) state.absence = { error: outcome.error, connectionId: school };
  rerender();
}

function absenceStale(box) {
  return !box || (!!box.connectionId && box.connectionId !== absenceSchoolId());
}

function absenceView() {
  const view = el("div", {});
  if (childPillsShown()) view.append(childPills(state.childId, selectChild));
  if (!absenceSchoolId() && manySchools()) {
    view.append(absenceSchoolBlock());
    return view;
  }
  const banner = schoolIssueBanner([absenceSchoolId()]);
  if (banner) view.append(banner);
  const box = state.absence;
  if (absenceStale(box)) {
    autoLoad("absence", loadAbsences);
    view.append(loadingBlock());
    return view;
  }
  if (box.error) {
    view.append(schoolInOutage(box.connectionId || absenceSchoolId())
      ? outageEmptyBlock()
      : emptyBlock("alert", t("absence.error.title"), t("absence.error.text"), retryButton(() => { state.absence = null; rerender(); })));
    return view;
  }
  const data = box.data;
  const note = refreshFailureNote("absence");
  if (note) view.append(note);
  if (Array.isArray(data.children) && !data.children.length) {
    view.append(emptyBlock("absence", t("absence.children.empty.title"), t("absence.children.empty.text")));
  } else {
    const older = absenceOlderSource(data);
    view.append(el("button", {
      class: "btn",
      type: "button",
      onclick: (event) => (older ? startOlderAbsenceForm(event.currentTarget) : startAbsenceForm()),
    }, [icon("plus", 18), t("absence.report")]));
  }
  if (absenceOlderSource(data) && Number(data.withheld) > 0) view.append(noteBlock(t("absence.older.withheld")));
  const phones = (data.phones || []).filter((entry) => entry.number);
  const entries = (data.entries || []).concat(olderLocalEntries(data, box.connectionId || absenceSchoolId()));
  view.append(el("div", { class: "section-head", style: "margin-top:28px" }, [el("span", { class: "overline" }, t("absence.reported"))]));
  if (!entries.length) {
    view.append(emptyBlock("check", t("absence.empty.title"), t(absenceOlderSource(data) ? "absence.empty.olderText" : "absence.empty.text")));
    if (absenceOlderSource(data) && data.export) view.append(olderExportButton());
    return view;
  }
  const today = isoDate(new Date());
  const current = entries.filter((entry) => (entry.till_date || entry.from_date || "") >= today);
  const past = entries.filter((entry) => (entry.till_date || entry.from_date || "") < today);
  if (current.length) {
    const rows = el("div", { class: "rows" });
    for (const entry of current) rows.append(absenceRow(entry));
    view.append(rows);
  } else if (!past.length) {
    view.append(emptyBlock("check", t("absence.empty.title"), t(absenceOlderSource(data) ? "absence.empty.olderText" : "absence.empty.text")));
  } else {
    view.append(noteBlock(t("absence.none")));
  }
  if (past.length) view.append(absenceHistorySection(past));
  if (absenceOlderSource(data) && data.export) view.append(olderExportButton());
  if (phones.length) view.append(absencePhonesSection(phones));
  return view;
}

function absenceOlderSource(data) {
  return !!data && data.source === "older_page";
}

async function startOlderAbsenceForm(button) {
  if (button.disabled) return;
  button.disabled = true;
  const school = openAbsenceSchoolId();
  try {
    const result = await getJson(`api/absences/older-form?connection=${encodeURIComponent(school)}`);
    if (result && result.ok && result.form) startAbsenceForm("absence", undefined, result.form);
    else toast(apiMessage(result, "absence.older.formFailed"), "bad");
  } catch (error) {
    if (!handleApiFailure(error, school)) toast(apiMessage(error && error.body, "absence.older.formFailed"), "bad");
  } finally {
    button.disabled = false;
  }
}

function absenceProfiles(form, data) {
  if (form && form.type === "absence" && form.schema) return form.schema.profiles || [];
  return (data && data.children) || [];
}

function absenceFormTitle(form) {
  return form && form.type === "absence" ? t("absence.entry.kind.absence") : absenceTypeLabel(form && form.type);
}

function absencePhonesSection(phones) {
  const wrap = el("div", { style: "margin-top:28px" });
  wrap.append(el("div", { class: "section-head" }, [el("span", { class: "overline" }, t("absence.phones.title"))]));
  const rows = el("div", { class: "rows" });
  for (const phone of phones) {
    const number = phone.number || "";
    rows.append(
      el("a", { class: "row read", href: `tel:${number}` }, [
        el("span", { class: "row-dot" }, [icon("phone", 14)]),
        el("div", { class: "row-main" }, [
          iservText("div", { class: "row-title" }, phone.label || t("absence.phone.fallback")),
          iservText("div", { class: "row-sub" }, number),
        ]),
      ])
    );
  }
  wrap.append(rows);
  return wrap;
}

function absenceHistorySection(past) {
  const wrap = el("div", { style: "margin-top:20px" });
  const open = state.absenceHistoryOpen;
  wrap.append(
    el("button", {
      class: "section-head",
      type: "button",
      style: "width:100%;background:none;border:0;padding:0;cursor:pointer;",
      "aria-expanded": String(open),
      onclick: () => { state.absenceHistoryOpen = !state.absenceHistoryOpen; rerender(); },
    }, [
      el("span", { class: "overline" }, t("absence.history.title", { count: formatNumber(past.length) })),
      el("span", { class: `ico-slot chev-toggle${open ? " open" : ""}`, html: iconSvg("chevron", 16) }),
    ])
  );
  if (open) {
    const rows = el("div", { class: "rows" });
    for (const entry of past) rows.append(absenceRow(entry));
    wrap.append(rows);
  }
  return wrap;
}

function absenceDayWithTime(day, time) {
  const shown = showDate(day);
  return shown && time ? `${shown} ${t("absence.fact.time", { time })}` : shown;
}

function absenceDates(entry) {
  const from = absenceDayWithTime(entry.from_date, entry.from_time);
  const sameDay = !entry.till_date || entry.till_date === entry.from_date;
  const till = sameDay && !entry.till_time ? "" : absenceDayWithTime(entry.till_date || entry.from_date, entry.till_time);
  if (from && till && from !== till) return dateRange(from, till);
  return from || till || "";
}

function absenceChildName(entry, full) {
  const children = (state.absence && state.absence.data && state.absence.data.children) || [];
  if (children.length < 2) return "";
  const found = children.find((child) => String(child.id) === String(entry.student_id));
  if (!found) return "";
  return full ? found.name : firstName(found.name) || found.name;
}

function absenceEntryLabel(entry) {
  if (entry.label_key) {
    const base = t(entry.label_key);
    return entry.target_key ? t("absence.label.withTarget", { label: base, target: t(entry.target_key) }) : base;
  }
  return entry.label || t("absence.entry.fallback");
}

function absenceLockedReason(entry) {
  if (entry.locked_reason_key) return t(entry.locked_reason_key);
  return entry.locked_reason || t("absence.locked.fallback");
}

function dayOptions(list) {
  return (list || []).map((option) => ({
    value: option.value,
    label: option.label_key ? t(option.label_key) : formatWeekdayDate(option.value) || option.label,
  }));
}

function absenceRow(entry) {
  const statusTag = entry.status ? STATUS_TAGS[entry.status] || null : null;
  const sub = [
    absenceChildName(entry),
    absenceDates(entry),
    entry.pickup_time ? t("absence.pickup", { time: entry.pickup_time }) : "",
    entry.comment || entry.subject || "",
  ]
    .filter(Boolean)
    .join(" · ");
  const tags = [];
  if (entry.from_history) tags.push(el("span", { class: "tag" }, t("absence.tag.history")));
  if (statusTag) tags.push(el("span", { class: `tag ${statusTag[0]}` }, t(statusTag[1])));
  if ((entry.attachments || []).length) tags.push(el("span", { class: "row-clip" }, [icon("clip", 14)]));
  return el("button", {
    class: openRowClass("row read", "absence", entry.id),
    type: "button",
    onclick: () => openAbsenceSheet(entry),
  }, [
    el("span", { class: "row-dot" }),
    el("div", { class: "row-main" }, [
      iservText("div", { class: "row-title" }, absenceEntryLabel(entry)),
      sub ? iservText("div", { class: "row-sub" }, sub) : null,
    ]),
    tags.length ? el("div", { class: "row-side" }, tags) : null,
  ]);
}

function absenceTechEntries(entry) {
  const technical = entry.technical || {};
  if (entry.source === "older_page") {
    return [
      { label: t("absence.tech.id"), value: technical.id, kind: "text" },
      { label: t("absence.tech.createdAt"), value: technical.created_at ? showDate(technical.created_at) : "", kind: "text" },
      { label: t("absence.tech.classCode"), value: technical.class_code, kind: "text" },
    ];
  }
  const entries = [
    { label: t("absence.tech.id"), value: technical.id, kind: "text" },
    { label: t("absence.tech.createdAt"), value: technical.created_at, kind: "epoch" },
  ];
  if (entry.kind === "sick") {
    entries.push(
      { label: t("absence.tech.reporter"), value: technical.reporter, kind: "text" },
      { label: t("absence.tech.dutyToReport"), value: technical.duty_to_report, kind: "bool" },
      { label: t("absence.tech.classCode"), value: technical.class_code, kind: "text" },
      { label: t("absence.tech.writtenConfirmation"), value: technical.has_written_confirmation, kind: "bool" },
      { label: t("absence.tech.needsOfficial"), value: technical.needs_official_confirmation, kind: "bool" },
      { label: t("absence.tech.hasOfficial"), value: technical.has_official_confirmation, kind: "bool" },
      { label: t("absence.tech.counted"), value: technical.counted_in_statistics, kind: "bool" }
    );
  } else {
    entries.push(
      { label: t("absence.tech.updatedAt"), value: technical.updated_at, kind: "epoch" },
      { label: t("absence.tech.author"), value: technical.author, kind: "text" },
      { label: t("absence.tech.responseAuthor"), value: technical.response_author, kind: "text" }
    );
  }
  return entries;
}

function sickNotePdfBlock(entry) {
  const rules = (state.absence && state.absence.data && state.absence.data.rules) || {};
  const dutyHint = (rules.duty_hint || "").trim();
  const school = openAbsenceSchoolId();
  const path = `api/absences/sick-note-pdf?id=${encodeURIComponent(entry.id)}${school ? `&connection=${encodeURIComponent(school)}` : ""}`;
  const button = el("button", { type: "button", class: "btn" }, [icon("clip", 18), t("absence.sickNote.pdf")]);
  button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.disabled = true;
    try {
      await openAppFile(path, t("absence.sickNote.pdfFilename"), button);
    } catch (error) {
      toast(error.userMessage || t("common.attachmentOpenFailed"), "bad");
    } finally {
      button.disabled = false;
    }
  });
  return el("div", { style: "margin-top:24px" }, [button, dutyHint ? noteBlock(dutyHint) : null]);
}

function absenceDetailParts(entry) {
  const facts = [
    [t("absence.fact.kind"), absenceEntryLabel(entry)],
    [t("absence.fact.range"), absenceDates(entry) || t("common.none")],
  ];
  const who = absenceChildName(entry, true);
  if (who) facts.splice(1, 0, [t("absence.fact.child"), who]);
  if (hasPeriodNumber(entry.from_period)) {
    facts.push([
      t("absence.fact.hours"),
      t("absence.fact.hoursRange", {
        from: formatNumber(entry.from_period),
        till: formatNumber(hasPeriodNumber(entry.till_period) ? entry.till_period : entry.from_period),
      }),
    ]);
  }
  if (entry.pickup_time) facts.push([t("absence.fact.pickup"), t("absence.fact.time", { time: entry.pickup_time })]);
  if (entry.subject) facts.push([t("absence.fact.subject"), entry.subject]);
  if (entry.comment) facts.push([t("absence.fact.comment"), entry.comment]);
  if (entry.weekly) facts.push([t("absence.fact.repeat"), t("absence.fact.weekly")]);
  if (entry.weekly && entry.repeat_until) facts.push([t("absence.fact.repeatUntil"), showDate(entry.repeat_until)]);
  if (entry.status && STATUS_TAGS[entry.status]) facts.push([t("absence.fact.status"), t(STATUS_TAGS[entry.status][1])]);
  const body = [factList(facts)];
  if (entry.answer) body.push(el("div", { class: "card", style: "margin-top:16px" }, [el("div", { class: "body-html", dir: "auto", richHtml: entry.answer })]));
  const attachments = entry.attachments || [];
  if (attachments.length) {
    body.push(el("div", { class: "section-head", style: "margin-top:24px" }, [el("span", { class: "overline" }, t("common.attachments"))]));
    body.push(attachmentRows(attachments));
  }
  if (entry.kind === "sick") body.push(sickNotePdfBlock(entry));
  if (entry.source === "older_page" && entry.detail && !entry.unconfirmed) body.push(olderAttachmentsBlock(entry));
  const foot = entry.deletable
    ? el("button", { class: "btn destructive", type: "button", onclick: () => withdrawAbsence(entry) }, [icon("trash", 18), t("absence.withdraw")])
    : noteBlock(absenceLockedReason(entry));
  return { title: absenceEntryLabel(entry), body, foot: [foot], extra: techDetailsButton(absenceTechEntries(entry)) };
}

function openAbsenceSheet(entry) {
  const detail = { kind: "absence", entry };
  if (detailPlacement(detail.kind, layoutMode(), state.view) === "pane") return openDetail(detail);
  openSheet(detailSheetFactory(detail));
}

async function withdrawAbsence(entry) {
  const ok = await confirmAction({
    title: t("absence.withdraw.confirmTitle", { label: absenceEntryLabel(entry) }),
    text: t("absence.withdraw.text"),
    confirmLabel: t("absence.withdraw"),
    destructive: true,
  });
  if (!ok) {
    openAbsenceSheet(entry);
    return;
  }
  const school = openAbsenceSchoolId();
  dropSheet();
  state.detail = null;
  state.absence = null;
  rerender();
  try {
    const result = await postJson("api/absences/delete", {
      connection_id: school,
      type: entry.kind,
      id: entry.id,
      target: entry.target || "",
    }, ABSENCE_SUBMIT_TIMEOUT_MS);
    const good = !!(result && result.ok);
    toast(apiMessage(result, good ? "absence.withdraw.done" : "absence.withdraw.failed"), good ? "good" : "bad");
  } catch (error) {
    if (!handleApiFailure(error)) toast(t(isTimeoutError(error) ? "api.absence.withdrawUnclear" : "absence.withdraw.failed"), "bad");
  }
  loadAbsences();
}

function absenceChildColor(children, id) {
  const index = children.findIndex((c) => String(c.id) === String(id));
  return CHILD_COLORS[(index < 0 ? 0 : index) % CHILD_COLORS.length];
}

function daycareLeadDays(rules) {
  const lead = Math.max(0, rules.daycare_min_days || 0);
  if (lead > 0) return lead;
  const cutoff = /^(\d{1,2}):(\d{2})$/.exec(rules.daycare_cutoff || "");
  if (!cutoff) return 0;
  const now = new Date();
  return now.getHours() * 60 + now.getMinutes() >= Number(cutoff[1]) * 60 + Number(cutoff[2]) ? 1 : 0;
}

const ABSENCE_DEFAULT_FROM_TIME = "08:00";
const ABSENCE_DEFAULT_TILL_TIME = "14:00";
const ABSENCE_CONDITIONAL_STEPS = ["sickHours", "leaveFrom", "leaveDayTime", "deregisterWhen", "daycareWhen", "olderWhen", "olderDayTime"];
const ABSENCE_FLOW_TEXTS = {
  back: "absence.wizard.back",
  goal: "absence.wizard.progress.goal",
  progress: "absence.wizard.progress",
  progressTotal: "absence.wizard.progress.total",
  pending: "absence.wizard.progress.pending",
  failed: "absence.submit.failed",
};

let absenceFlow = null;

function absenceTypeList(data) {
  return ((data && data.types) || []).filter((key) => ABSENCE_TYPES[key]);
}

function absenceDefaultType(data) {
  const types = absenceTypeList(data);
  if (types.includes("sick")) return "sick";
  return types[0] || "sick";
}

const ABSENCE_STEP_TITLES = {
  sickPeriods: "absence.wizard.step.sick.periods",
  leaveTill: "absence.wizard.step.leave.till",
  leaveTimes: "absence.wizard.step.leave.times",
  repeatUntil: "absence.wizard.step.repeatUntil",
  daycarePickup: "absence.wizard.step.daycare.pickup",
  olderTill: "absence.wizard.step.leave.till",
  olderTimes: "absence.wizard.step.leave.times",
};

const ABSENCE_REVEALS = {
  sickHours: { step: "sickPeriods", when: (form) => form.hours_mode === "byLesson" },
  daycareKind: { step: "daycarePickup", when: (form) => form.daycare_kind === "early_end" },
};

function absenceStepHost(id) {
  for (const host of Object.keys(ABSENCE_REVEALS)) {
    if (ABSENCE_REVEALS[host].step === id) return host;
  }
  return id;
}

function absenceRevealedStep(id, form) {
  const reveal = ABSENCE_REVEALS[id];
  return reveal && form && reveal.when(form) ? reveal.step : "";
}

function absenceRevealName(id) {
  const reveal = ABSENCE_REVEALS[id];
  return reveal ? t(ABSENCE_STEP_TITLES[reveal.step]) : "";
}

function absenceAnnounceReveal(id, shown) {
  const name = absenceRevealName(id);
  if (!name || !absenceFlow) return;
  absenceFlow.announce(t(shown ? "absence.wizard.fieldShown" : "absence.wizard.fieldHidden", { name }));
}

function absenceAnnounceStep(stepId, added) {
  if (!absenceFlow) return;
  absenceFlow.announce(
    t(added ? "absence.wizard.stepAdded" : "absence.wizard.stepRemoved", { name: t(ABSENCE_STEP_TITLES[stepId]) })
  );
}

function absencePath(form, data) {
  if (!form || !data) return [];
  const rules = data.rules || {};
  const ids = [];
  if (form.type === "absence") return olderAbsencePath(form);
  if (absenceTypeList(data).length > 1) ids.push("type");
  if ((data.children || []).length > 1) ids.push("child");
  if (form.type === "sick") {
    ids.push("sickWhen");
    if (rules.sick_by_lesson) {
      ids.push("sickHours");
      if (form.hours_mode === "byLesson") ids.push("sickPeriods");
    }
  } else if (form.type === "leave") {
    ids.push("leaveFrom");
    if (form.duration === "more") ids.push("leaveTill");
    ids.push("leaveDayTime");
    if (form.time_mode === "custom") ids.push("leaveTimes");
    ids.push("leaveSubject", "leaveBody");
  } else if (form.type === "deregister") {
    if ((data.deregister_options || []).length !== 1) ids.push("deregisterTarget");
    ids.push("deregisterWhen");
    if (form.repeat === "weekly") ids.push("repeatUntil");
  } else {
    ids.push("daycareKind");
    if (form.daycare_kind === "early_end") ids.push("daycarePickup");
    ids.push("daycareWhen");
    if (form.repeat === "weekly") ids.push("repeatUntil");
    if (rules.daycare_reason_required) ids.push("daycareReason");
  }
  ids.push("review");
  return ids.filter((id) => {
    const host = absenceStepHost(id);
    return host === id || !ids.includes(host);
  });
}

function absenceCurrentPath() {
  return absencePath(state.absenceForm, state.absence && state.absence.data);
}

function absenceIsDetour(id) {
  return !!id && !absenceCurrentPath().includes(id);
}

function absenceFlowText(name, vars) {
  const key = ABSENCE_FLOW_TEXTS[name];
  return key ? t(key, vars) : "";
}

function absenceFlowLead() {
  const data = state.absence.data;
  const children = absenceProfiles(state.absenceForm, data);
  if (children.length < 2) return null;
  const child = children.find((entry) => String(entry.id) === String(state.absenceForm.student_id));
  if (!child) return null;
  const name = child.name || "";
  const avatar = iservText("span", { class: "avatar" }, (name || "?").trim().charAt(0).toUpperCase());
  avatar.style.background = absenceChildColor(children, child.id);
  return el("button", {
    class: "sw-lead-btn",
    type: "button",
    "aria-label": name,
    onclick: () => absenceOpenStep("child"),
  }, [avatar]);
}

function absenceFlowTrailing() {
  return el("button", {
    class: "icon-btn",
    type: "button",
    "aria-label": t("absence.wizard.exit"),
    onclick: absenceExit,
  }, [icon("close", 18)]);
}

function absenceExit() {
  leaveAbsenceForm(() => {
    closeAbsenceForm();
    render();
  });
}

function closeAbsenceForm() {
  if (absenceFlow) absenceFlow.destroy();
  absenceFlow = null;
  document.removeEventListener("visibilitychange", absenceRecheckLimits);
  state.absenceForm = null;
  state.absenceFormDefault = null;
}

function wizRefresh() {
  if (absenceFlow) absenceFlow.render();
}

function absenceOpenStep(id) {
  if (!absenceFlow) return;
  absenceFlow.returnTo("review");
  absenceFlow.go(absenceStepHost(id));
}

function absenceRecheckLimits() {
  if (document.hidden || !absenceFlow || !state.absenceForm) return;
  absenceFlow.sync();
}

function absenceRedirect(id) {
  if (id !== "review" || !state.absenceForm) return id;
  const problem = absenceProblemEntry(state.absenceForm, state.absence.data);
  if (!problem) return id;
  return { step: problem.step, status: problem.text };
}

function absenceFlowStart(startAt) {
  if (absenceFlow) absenceFlow.destroy();
  absenceFlow = window.StepFlow.create({
    text: absenceFlowText,
    steps: absenceCurrentPath,
    detour: absenceIsDetour,
    redirect: absenceRedirect,
    step: absenceStep,
    pending: (id) => ABSENCE_CONDITIONAL_STEPS.includes(id) && !ABSENCE_REVEALS[id],
    title: () => absenceFormTitle(state.absenceForm),
    lead: absenceFlowLead,
    trailing: absenceFlowTrailing,
    onExit: absenceExit,
  });
  document.addEventListener("visibilitychange", absenceRecheckLimits);
  absenceFlow.start(startAt || absenceCurrentPath()[0]);
}

function startAbsenceForm(type, studentId, schema) {
  const data = state.absence.data;
  const children = schema ? schema.profiles || [] : data.children || [];
  const rules = data.rules || {};
  const chosen = type || absenceDefaultType(data);
  const form = {
    type: chosen,
    student_id: studentId != null ? String(studentId) : children.length === 1 ? String(children[0].id) : "",
  };
  if (chosen === "absence") {
    Object.assign(form, olderAbsenceDefaults(schema));
  } else if (chosen === "sick") {
    const options = data.day_options || { from: [], till: [] };
    form.day_from = (options.from[0] || {}).value || "";
    form.day_till = (options.till[0] || {}).value || "";
    form.hours_mode = "full";
    form.from_period = "";
    form.till_period = "";
    form.duty_to_report = false;
    form.comment = "";
  } else if (chosen === "leave") {
    const first = isoDate(addDays(new Date(), Math.max(0, rules.leave_min_days || 0)));
    form.from_date = first;
    form.till_date = first;
    form.duration = "one";
    form.from_time = ABSENCE_DEFAULT_FROM_TIME;
    form.till_time = ABSENCE_DEFAULT_TILL_TIME;
    form.time_mode = "school";
    form.subject = t("absence.leave.subjectPlaceholder", { date: showDate(first) });
    form.subject_auto = true;
    form.body = "";
    form.attachments = [];
  } else if (chosen === "deregister") {
    form.deregister_from = (data.deregister_options || [])[0] || "";
    form.date = isoDate(new Date());
    form.repeat = "once";
    form.repeat_until = "";
  } else {
    form.daycare_kind = "deregister";
    form.date = isoDate(addDays(new Date(), daycareLeadDays(rules)));
    form.pickup_time = (rules.daycare_pickup_times || [])[0] || "";
    form.repeat = "once";
    form.repeat_until = "";
    form.reason = "";
  }
  dropSheet();
  state.absenceForm = form;
  state.absenceFormDefault = copy(form);
  absenceFlowStart();
  render();
}

function absenceChildLabel(child) {
  const name = firstName(child.name) || child.name || "";
  const className = child.class_name || "";
  return className ? t("absence.wizard.childLine", { name, class: className }) : name;
}

function absenceChoice(title, active, onclick) {
  return el("button", { class: "opt", type: "button", "aria-pressed": String(active), onclick }, [el("b", {}, title)]);
}

function absenceSegment(options) {
  return el("div", { class: "opt-row" }, options.map((option) =>
    el("button", { class: "opt", type: "button", "aria-pressed": String(option.active), onclick: option.onclick }, [
      el("b", {}, option.label),
    ])
  ));
}

function withHint(field, text) {
  if (text) field.append(el("span", { class: "hint" }, text));
  return field;
}

function absenceChooseType(key) {
  if (key === state.absenceForm.type) return;
  const keep = state.absenceForm.student_id;
  leaveAbsenceForm(() => startAbsenceForm(key, keep || undefined));
}

function absenceSetHoursMode(key) {
  const form = state.absenceForm;
  if ((form.hours_mode || "full") === key) return;
  const dropped = key === "full" && !!(form.from_period || form.till_period);
  form.hours_mode = key;
  if (key === "full") {
    form.from_period = "";
    form.till_period = "";
  } else {
    const numbers = (state.absence.data.period_labels || []).map((entry) => String(entry.number));
    form.from_period = numbers[0] || "";
    form.till_period = numbers[numbers.length - 1] || "";
  }
  wizRefresh();
  if (dropped) absenceFlow.status(t("absence.wizard.periodsDropped"), "");
  absenceAnnounceReveal("sickHours", key === "byLesson");
}

function absenceSetRepeat(key) {
  const form = state.absenceForm;
  if (form.repeat === key) return;
  form.repeat = key;
  if (key === "once") form.repeat_until = "";
  wizRefresh();
  absenceAnnounceStep("repeatUntil", key === "weekly");
}

function absenceSyncSubject() {
  const form = state.absenceForm;
  if (!form.subject_auto) return;
  form.subject = t("absence.leave.subjectPlaceholder", { date: showDate(form.from_date) });
}

function absenceSickCutoffHint(rules) {
  if (!rules.sick_cutoff) return "";
  return rules.sick_cutoff_message || t("absence.sick.cutoff", { time: rules.sick_cutoff });
}

function absenceStep(id) {
  const form = state.absenceForm;
  const data = state.absence && state.absence.data;
  if (!form || !data) return { question: "", body: [], nextLabel: "" };
  const builder = ABSENCE_STEP_BUILDERS[id] || OLDER_STEP_BUILDERS[id];
  if (!builder) return { question: "", body: [], nextLabel: t("common.next") };
  const step = builder(form, data, data.rules || {});
  const revealed = absenceRevealedStep(id, form);
  if (revealed) {
    step.body = [].concat(step.body || [], [
      el("div", { class: "sw-reveal" }, [].concat(ABSENCE_STEP_BUILDERS[revealed](form, data, data.rules || {}).body || [])),
    ]);
  }
  if (!step.nextLabel) step.nextLabel = t("common.next");
  const blocker = absenceStepBlock(id, form, data);
  if (blocker) {
    step.block = blocker.hint;
    step.blockFocus = () => document.querySelector(".sw-body .inp, .sw-body .sel, .sw-body .txt");
  }
  if (absenceIsDetour(id)) {
    step.nextLabel = t("absence.wizard.toReview");
    step.nextTarget = "review";
  }
  return step;
}

const ABSENCE_STEP_BUILDERS = {
  type(form, data) {
    return {
      list: true,
      question: t("absence.sheet.type"),
      hint: ABSENCE_TYPES[form.type] ? t(ABSENCE_TYPES[form.type].hint) : "",
      body: [
        el("div", { class: "sw-list" }, absenceTypeList(data).map((key) =>
          absenceChoice(t(ABSENCE_TYPES[key].label), form.type === key, () => absenceChooseType(key))
        )),
      ],
    };
  },
  child(form, data) {
    const children = absenceProfiles(form, data);
    return {
      list: true,
      question: t("absence.sheet.child"),
      body: [
        el("div", { class: "sw-list" }, children.map((child) =>
          absenceChoice(
            absenceChildLabel(child),
            String(child.id) === String(form.student_id),
            () => {
              form.student_id = String(child.id);
              wizRefresh();
            }
          )
        )),
      ],
    };
  },
  sickWhen(form, data, rules) {
    const options = data.day_options || { from: [], till: [] };
    return {
      question: t("absence.wizard.step.sick.when"),
      body: [
        withHint(
          selectField(t("absence.field.fromDay"), form.day_from, dayOptions(options.from), (value) => {
            form.day_from = value;
            if (form.day_till < value) form.day_till = value;
            wizRefresh();
          }),
          absenceSickCutoffHint(rules)
        ),
        selectField(
          t("absence.field.tillDay"),
          form.day_till,
          dayOptions(options.till).filter((item) => item.value >= form.day_from),
          (value) => {
            form.day_till = value;
          }
        ),
      ],
    };
  },
  sickHours(form) {
    const mode = form.hours_mode || "full";
    return {
      question: t("absence.wizard.step.sick.hours"),
      body: [
        absenceSegment([
          { label: t("absence.hours.full"), active: mode === "full", onclick: () => absenceSetHoursMode("full") },
          { label: t("absence.hours.byLesson"), active: mode === "byLesson", onclick: () => absenceSetHoursMode("byLesson") },
        ]),
      ],
    };
  },
  sickPeriods(form, data) {
    const periods = (data.period_labels || []).map((entry) => ({ value: String(entry.number), label: entry.label }));
    return {
      question: t("absence.wizard.step.sick.periods"),
      body: [
        selectField(t("absence.field.fromPeriod"), form.from_period, periods, (value) => {
          form.from_period = value;
          wizRefresh();
        }),
        selectField(t("absence.field.tillPeriod"), form.till_period, periods, (value) => {
          form.till_period = value;
          wizRefresh();
        }),
      ],
    };
  },
  sickComment(form) {
    return {
      question: t("absence.wizard.step.sick.comment"),
      body: [
        textField(t("absence.field.optionalComment"), form.comment, (value) => {
          form.comment = value;
        }),
      ],
    };
  },
  leaveFrom(form, data, rules) {
    const min = isoDate(addDays(new Date(), Math.max(0, rules.leave_min_days || 0)));
    const lead = rules.leave_min_days
      ? t("absence.leave.lead", { days: formatNumber(rules.leave_min_days), date: showDate(min) })
      : "";
    return {
      question: t("absence.wizard.step.leave.from"),
      body: [
        withHint(
          dateField(t("absence.field.fromDay"), form.from_date, min, (value) => {
            form.from_date = value;
            if (form.till_date < value) form.till_date = value;
            absenceSyncSubject();
            wizRefresh();
          }),
          lead
        ),
        absenceSegment([
          {
            label: t("absence.duration.oneDay"),
            active: form.duration !== "more",
            onclick: () => {
              if (form.duration === "one") return;
              form.duration = "one";
              form.till_date = form.from_date;
              wizRefresh();
              absenceAnnounceStep("leaveTill", false);
            },
          },
          {
            label: t("absence.duration.moreDays"),
            active: form.duration === "more",
            onclick: () => {
              if (form.duration === "more") return;
              form.duration = "more";
              wizRefresh();
              absenceAnnounceStep("leaveTill", true);
            },
          },
        ]),
      ],
    };
  },
  leaveTill(form) {
    return {
      question: t("absence.wizard.step.leave.till"),
      body: [
        dateField(t("absence.field.tillDay"), form.till_date, form.from_date, (value) => {
          form.till_date = value;
          wizRefresh();
        }),
      ],
    };
  },
  leaveDayTime(form) {
    return {
      question: t("absence.wizard.step.leave.dayTime"),
      body: [
        absenceSegment([
          {
            label: t("absence.time.schoolDay", { from: ABSENCE_DEFAULT_FROM_TIME, till: ABSENCE_DEFAULT_TILL_TIME }),
            active: form.time_mode !== "custom",
            onclick: () => {
              if (form.time_mode === "school") return;
              form.time_mode = "school";
              form.from_time = ABSENCE_DEFAULT_FROM_TIME;
              form.till_time = ABSENCE_DEFAULT_TILL_TIME;
              wizRefresh();
              absenceAnnounceStep("leaveTimes", false);
            },
          },
          {
            label: t("absence.time.custom"),
            active: form.time_mode === "custom",
            onclick: () => {
              if (form.time_mode === "custom") return;
              form.time_mode = "custom";
              wizRefresh();
              absenceAnnounceStep("leaveTimes", true);
            },
          },
        ]),
      ],
    };
  },
  leaveTimes(form) {
    return {
      question: t("absence.wizard.step.leave.times"),
      body: [
        timeField(t("absence.field.start"), form.from_time, (value) => {
          form.from_time = value;
          wizRefresh();
        }),
        timeField(t("absence.field.end"), form.till_time, (value) => {
          form.till_time = value;
          wizRefresh();
        }),
      ],
    };
  },
  leaveSubject(form) {
    return {
      question: t("absence.wizard.step.leave.subject"),
      body: [
        inputField(t("absence.field.subject"), form.subject, "", (value) => {
          form.subject = value;
          form.subject_auto = false;
          absenceFlow.sync();
        }),
      ],
    };
  },
  leaveBody(form) {
    return {
      question: t("absence.wizard.step.leave.body"),
      body: [
        withHint(
          textField(t("absence.field.request"), form.body, (value) => {
            form.body = value;
            absenceFlow.sync();
          }),
          t("absence.leave.requestHint")
        ),
      ],
    };
  },
  leaveAttachments(form) {
    return {
      question: t("absence.wizard.step.leave.attachments"),
      body: [absenceAttachmentsField(form)],
    };
  },
  deregisterTarget(form, data) {
    return {
      list: true,
      question: t("absence.deregister.target"),
      body: [
        el("div", { class: "sw-list" }, (data.deregister_options || []).map((key) =>
          absenceChoice(targetLabel(key), form.deregister_from === key, () => {
            form.deregister_from = key;
            wizRefresh();
          })
        )),
      ],
    };
  },
  deregisterWhen(form) {
    return {
      question: t("absence.wizard.step.deregister.when"),
      body: [
        dateField(t("absence.field.on"), form.date, isoDate(new Date()), (value) => {
          form.date = value;
          wizRefresh();
        }),
        absenceRepeatSegment(form),
      ],
    };
  },
  repeatUntil(form) {
    return {
      question: t("absence.wizard.step.repeatUntil"),
      body: [
        withHint(
          dateField(t("absence.repeat.until"), form.repeat_until, form.date, (value) => {
            form.repeat_until = value;
            wizRefresh();
          }),
          t("absence.repeat.info")
        ),
      ],
    };
  },
  daycareKind(form) {
    return {
      list: true,
      question: t("absence.wizard.step.daycare.kind"),
      hint: t(form.daycare_kind === "early_end" ? "absence.daycare.earlyEnd.hint" : "absence.daycare.deregister.hint"),
      body: [
        el("div", { class: "sw-list" }, [
          absenceChoice(t("absence.daycare.deregister.title"), form.daycare_kind === "deregister", () =>
            absenceSetDaycareKind("deregister")
          ),
          absenceChoice(t("absence.daycare.earlyEnd.title"), form.daycare_kind === "early_end", () =>
            absenceSetDaycareKind("early_end")
          ),
        ]),
      ],
    };
  },
  daycarePickup(form, data, rules) {
    const times = rules.daycare_pickup_times || [];
    const free = rules.daycare_custom_pickup || !times.length;
    return {
      question: t("absence.wizard.step.daycare.pickup"),
      body: [
        free
          ? timeField(t("absence.field.pickup"), form.pickup_time, (value) => {
              form.pickup_time = value;
              wizRefresh();
            })
          : selectField(
              t("absence.field.pickup"),
              form.pickup_time,
              times.map((time) => ({ value: time, label: t("absence.fact.time", { time }) })),
              (value) => {
                form.pickup_time = value;
                wizRefresh();
              }
            ),
      ],
    };
  },
  daycareWhen(form, data, rules) {
    const lead = daycareLeadDays(rules);
    const hint = lead > 0 && rules.daycare_cutoff ? t("absence.daycare.cutoff", { time: rules.daycare_cutoff }) : "";
    return {
      question: t("absence.wizard.step.daycare.when"),
      body: [
        withHint(
          dateField(t("absence.field.date"), form.date, isoDate(addDays(new Date(), lead)), (value) => {
            form.date = value;
            wizRefresh();
          }),
          hint
        ),
        absenceRepeatSegment(form),
      ],
    };
  },
  daycareReason(form, data, rules) {
    return {
      question: t("absence.wizard.step.daycare.reason"),
      body: [
        textField(t(rules.daycare_reason_required ? "absence.field.reason" : "absence.field.reasonOptional"), form.reason, (value) => {
          form.reason = value;
          absenceFlow.sync();
        }),
      ],
    };
  },
  review(form, data) {
    const sick = form.type === "sick";
    const hint = sick
      ? t("absence.review.sendsNow") + " " + t("absence.sick.warning")
      : t("absence.review.sendsNow");
    return {
      question: t("absence.wizard.step.review"),
      body: [absenceReviewBody(form, data)],
      hint,
      nextLabel: t(sick ? "absence.confirm.sick.button" : "absence.confirm.button"),
      busyLabel: t("common.sending"),
      onNext: submitAbsence,
    };
  },
};

function absenceSetDaycareKind(kind) {
  const form = state.absenceForm;
  if (form.daycare_kind === kind) return;
  form.daycare_kind = kind;
  wizRefresh();
  absenceAnnounceReveal("daycareKind", kind === "early_end");
}

function absenceRepeatSegment(form) {
  return absenceSegment([
    { label: t("absence.repeat.once"), active: form.repeat !== "weekly", onclick: () => absenceSetRepeat("once") },
    { label: t("absence.repeat.weekly"), active: form.repeat === "weekly", onclick: () => absenceSetRepeat("weekly") },
  ]);
}

function absenceReviewBody(form, data) {
  const wrap = el("div", { class: "sw-review" });
  if (form.type === "sick") wrap.append(absenceDutyCard(form, data));
  wrap.append(absenceFactCard(form, data));
  return wrap;
}

function absenceDutyText(data) {
  const rules = (data && data.rules) || {};
  return String(rules.duty_hint || "").trim() || t("absence.sick.dutyHint");
}

function absenceDutySheet(text) {
  return sheet(t("absence.review.dutyExplain"), [iservText("p", { class: "dlg-text" }, text)]);
}

function absenceDutyCard(form, data) {
  const box = el("input", { type: "checkbox" });
  box.checked = !!form.duty_to_report;
  box.addEventListener("change", () => {
    form.duty_to_report = box.checked;
  });
  const text = absenceDutyText(data);
  return el("div", { class: "field-group sw-duty" }, [
    el("label", { class: "cell check" }, [box, el("span", {}, t("absence.field.dutyToReport"))]),
    el("button", {
      class: "cell sw-duty-more",
      type: "button",
      onclick: () => openSheet(() => absenceDutySheet(text)),
    }, [
      el("span", {}, t("absence.review.dutyExplain")),
      el("span", { class: "sw-fact-go chev-next", html: iconSvg("chevron", 14) }),
    ]),
  ]);
}

function absenceFactCard(form, data) {
  const card = el("div", { class: "sw-facts" });
  for (const fact of absenceReviewFacts(form, data)) {
    const parts = [
      el("span", { class: "sw-fact-label" }, fact.label),
      el("span", { class: "sw-fact-value", dir: "auto" }, fact.value),
    ];
    if (!fact.step) {
      card.append(el("div", { class: "sw-fact fixed" }, parts));
      continue;
    }
    card.append(
      el("button", {
        class: "sw-fact",
        type: "button",
        "aria-label": t("absence.wizard.change", { field: fact.label }),
        onclick: () => absenceOpenStep(fact.step),
      }, parts.concat([el("span", { class: "sw-fact-go chev-next", html: iconSvg("chevron", 14) })]))
    );
  }
  return card;
}

function absenceSickHoursText(form, data) {
  if (form.from_period) {
    return t("absence.fact.hoursRange", {
      from: formatNumber(form.from_period),
      till: formatNumber(form.till_period || form.from_period),
    });
  }
  const last = lastAvailablePeriod(data);
  return last ? t("absence.confirm.hoursDefault", { till: formatNumber(last) }) : "";
}

function absenceRange(from, till) {
  return from === till ? showDate(from) : t("absence.confirm.range", { from: showDate(from), till: showDate(till) });
}

function absenceJoin(first, second) {
  return second ? t("absence.wizard.factJoin", { first, second }) : first;
}

function absenceReviewFacts(form, data) {
  data = data || {};
  const rules = data.rules || {};
  const children = absenceProfiles(form, data);
  const facts = [];
  facts.push({
    label: t("absence.fact.child"),
    value: childNameForForm(),
    step: children.length > 1 ? "child" : "",
  });
  if (form.type === "absence") return facts.concat(olderAbsenceFacts(form));
  facts.push({ label: t("absence.fact.kind"), value: absenceTypeLabel(form.type), step: "" });
  if (form.type === "sick") {
    facts.push({
      label: t("absence.fact.range"),
      value: absenceJoin(absenceRange(form.day_from, form.day_till), absenceSickHoursText(form, data)),
      step: "sickWhen",
    });
    if (rules.sick_comment) {
      facts.push({
        label: t("absence.fact.comment"),
        value: form.comment || t("absence.wizard.none"),
        step: "sickComment",
      });
    }
    return facts;
  }
  if (form.type === "leave") {
    const times = form.time_mode === "custom" ? `${form.from_time}–${form.till_time}` : "";
    facts.push({
      label: t("absence.fact.range"),
      value: absenceJoin(absenceRange(form.from_date, form.till_date), times),
      step: "leaveFrom",
    });
    facts.push({ label: t("absence.fact.subject"), value: form.subject, step: "leaveSubject" });
    facts.push({
      label: t("absence.fact.attachments"),
      value: (form.attachments || []).length
        ? tCount("absence.attachments.count", (form.attachments || []).length)
        : t("absence.wizard.none"),
      step: "leaveAttachments",
    });
    return facts;
  }
  const repeat = form.repeat === "weekly" && form.repeat_until ? t("absence.confirm.weeklyUntil") + " " + showDate(form.repeat_until) : "";
  if (form.type === "deregister") {
    facts.push({ label: t("absence.confirm.target"), value: targetLabel(form.deregister_from), step: "deregisterTarget" });
    facts.push({ label: t("absence.fact.range"), value: absenceJoin(showDate(form.date), repeat), step: "deregisterWhen" });
    return facts;
  }
  facts.push({
    label: t("absence.confirm.daycareKind"),
    value: t(form.daycare_kind === "early_end" ? "absence.daycare.earlyEnd.title" : "absence.daycare.deregister.title"),
    step: "daycareKind",
  });
  if (form.daycare_kind === "early_end") {
    facts.push({
      label: t("absence.fact.pickup"),
      value: form.pickup_time ? t("absence.fact.time", { time: form.pickup_time }) : t("absence.wizard.none"),
      step: "daycarePickup",
    });
  }
  facts.push({ label: t("absence.fact.range"), value: absenceJoin(showDate(form.date), repeat), step: "daycareWhen" });
  facts.push({
    label: t("absence.fact.reason"),
    value: form.reason || t("absence.wizard.none"),
    step: "daycareReason",
  });
  return facts;
}

function absenceAttachmentsField(form) {
  form.attachments = form.attachments || [];
  const wrap = el("div", { class: "field-group" }, [el("span", { class: "lbl" }, t("absence.attachments.label"))]);
  const list = el("div", { class: "rows" });
  const input = el("input", { type: "file", multiple: "multiple", style: "display:none" });
  const renderList = () => {
    list.replaceChildren();
    form.attachments.forEach((file, index) => {
      const oversized = file.size > MAX_ATTACHMENT_BYTES;
      const attachmentName = file.name || "";
      const remove = el("button", { class: "search-clear", type: "button", "aria-label": t("absence.attachments.remove", { name: attachmentName }) }, [icon("close", 14)]);
      remove.addEventListener("click", () => {
        form.attachments.splice(index, 1);
        renderList();
        if (absenceFlow) absenceFlow.sync();
      });
      list.append(
        el("div", { class: "row read disabled" }, [
          el("span", { class: "row-dot" }, [icon("clip", 14)]),
          el("div", { class: "row-main" }, [
            iservText("div", { class: "row-title full" }, attachmentName),
            oversized ? el("div", { class: "row-sub", style: "color:var(--danger)" }, t("absence.attachments.oversized")) : null,
          ]),
          remove,
        ])
      );
    });
  };
  renderList();
  input.addEventListener("change", () => {
    form.attachments = form.attachments.concat(Array.from(input.files));
    input.value = "";
    renderList();
    if (absenceFlow) absenceFlow.sync();
  });
  const addBtn = el("button", { class: "btn ghost slim", type: "button" }, [icon("plus", 14), t("absence.attachments.add")]);
  addBtn.addEventListener("click", () => input.click());
  wrap.append(list, addBtn, input);
  return wrap;
}

function selectField(label, value, options, onchange) {
  const select = el("select", { class: "sel" });
  for (const option of options) {
    const node = el("option", { value: option.value }, option.label);
    if (String(option.value) === String(value)) node.selected = true;
    select.append(node);
  }
  select.addEventListener("change", () => onchange(select.value));
  return el("label", { class: "field" }, [
    el("span", { class: "lbl" }, label),
    el("div", { class: "sel-wrap" }, [select, el("span", { class: "caret", html: iconSvg("chevron", 14) })]),
  ]);
}

function inputField(label, value, placeholder, oninput) {
  const input = el("input", {
    class: "inp",
    type: "text",
    value: value || "",
    placeholder: placeholder || "",
    autocomplete: "off",
    enterkeyhint: "next",
    "aria-label": label,
  });
  input.addEventListener("input", () => oninput(input.value));
  return el("label", { class: "field" }, [el("span", { class: "lbl" }, label), input]);
}

function textField(label, value, oninput) {
  const area = el("textarea", { class: "txt", rows: "4", autocomplete: "off", "aria-label": label });
  area.value = value || "";
  area.addEventListener("input", () => oninput(area.value));
  return el("label", { class: "field text" }, [el("span", { class: "lbl" }, label), area]);
}

function dateField(label, value, min, onchange) {
  const input = el("input", { class: "inp", type: "date", value: value || "", min: min || null });
  input.addEventListener("change", () => onchange(input.value));
  return el("label", { class: "field" }, [el("span", { class: "lbl" }, label), input]);
}

function timeField(label, value, onchange) {
  const input = el("input", { class: "inp", type: "time", value: value || "" });
  input.addEventListener("change", () => onchange(input.value));
  return el("label", { class: "field" }, [el("span", { class: "lbl" }, label), input]);
}

function absenceAttachmentsProblem(form) {
  const attachments = form.attachments || [];
  if (attachments.some((file) => file.size > MAX_ATTACHMENT_BYTES)) {
    return { text: t("absence.attachments.oversized"), hint: t("absence.attachments.oversized.short") };
  }
  const total = attachments.reduce((sum, file) => sum + file.size, 0);
  if (total > MAX_TOTAL_ATTACHMENT_BYTES) {
    return { text: t("absence.attachments.totalOversized"), hint: t("absence.attachments.totalOversized.short") };
  }
  return null;
}

function absenceNeed(labelKey) {
  return t("absence.wizard.need", { field: t(labelKey) });
}

function absenceDayStale(form) {
  return !!form.day_from && form.day_from < isoDate(new Date());
}

function absenceDaycareStale(form, rules) {
  return !!form.date && form.date < isoDate(addDays(new Date(), daycareLeadDays(rules)));
}

function absenceProblems(form, data) {
  data = data || {};
  const rules = data.rules || {};
  const children = data.children || [];
  const list = [];
  const push = (step, text, hint) => list.push({ step: absenceStepHost(step), text, hint: hint || text });
  if (!form.student_id) push("child", t("absence.problem.child"), t("absence.wizard.required"));
  if (form.type === "absence") {
    for (const problem of olderAbsenceProblems(form)) push(problem.step, problem.text, problem.hint);
    return list;
  }
  const attachments = absenceAttachmentsProblem(form);
  if (attachments) push("leaveAttachments", attachments.text, attachments.hint);
  if (form.type === "sick") {
    if (form.from_period && !form.till_period) {
      push("sickPeriods", t("absence.problem.periodIncomplete"), absenceNeed("absence.field.tillPeriod"));
    } else if (form.from_period && form.till_period && Number(form.till_period) < Number(form.from_period)) {
      push("sickPeriods", t("absence.problem.periodOrder"), t("absence.problem.periodOrder"));
    }
    if (absenceDayStale(form)) push("sickWhen", t("absence.problem.dateStale"), t("absence.problem.dateStale"));
  }
  if (form.type === "leave") {
    if (form.till_date < form.from_date) push("leaveTill", t("absence.problem.range"), t("absence.problem.range"));
    if (
      form.from_date === form.till_date &&
      form.from_time &&
      form.till_time &&
      form.till_time <= form.from_time
    ) {
      push("leaveTimes", t("absence.problem.timeOrder"), t("absence.problem.timeOrder"));
    }
    if (!String(form.subject || "").trim()) {
      push("leaveSubject", t("absence.problem.subject"), absenceNeed("absence.field.subject"));
    }
    if (!String(form.body || "").trim()) push("leaveBody", t("absence.problem.body"), absenceNeed("absence.field.request"));
  }
  if (form.type === "deregister" && !form.deregister_from) {
    push("deregisterTarget", t("absence.problem.deregisterTarget"), t("absence.wizard.required"));
  }
  if (form.type === "daycare") {
    if (form.daycare_kind === "early_end" && !form.pickup_time) {
      push("daycarePickup", t("absence.problem.pickup"), absenceNeed("absence.field.pickup"));
    }
    if (rules.daycare_reason_required && !String(form.reason || "").trim()) {
      push("daycareReason", t("absence.problem.reason"), absenceNeed("absence.field.reason"));
    }
    if (absenceDaycareStale(form, rules)) push("daycareWhen", t("absence.problem.dateStale"), t("absence.problem.dateStale"));
  }
  if (form.repeat === "weekly") {
    if (!form.repeat_until) push("repeatUntil", t("absence.problem.repeatUntil"), absenceNeed("absence.repeat.until"));
    else if (form.repeat_until < (form.date || "")) {
      push("repeatUntil", t("absence.problem.repeatBeforeDate"), t("absence.problem.repeatBeforeDate"));
    }
  }
  return list;
}

function absenceProblemEntry(form, data) {
  return absenceProblems(form, data)[0] || null;
}

function absenceStepBlock(id, form, data) {
  return absenceProblems(form, data).find((entry) => entry.step === id) || null;
}

function hasPeriodNumber(value) {
  return value !== null && value !== undefined && value !== "";
}

function lastAvailablePeriod(data) {
  const numbers = (data.period_labels || []).map((entry) => Number(entry.number)).filter((number) => !Number.isNaN(number));
  return numbers.length ? Math.max(...numbers) : null;
}

function childNameForForm() {
  const data = state.absence.data;
  const children = absenceProfiles(state.absenceForm, data);
  const found = children.find((child) => String(child.id) === String(state.absenceForm.student_id));
  return (found && found.name) || (children[0] && children[0].name) || t("absence.child.fallback");
}

function absencePayload(form, children) {
  const payload = Object.assign({}, form, {
    student_id: form.student_id || (children[0] ? children[0].id : ""),
    connection_id: openAbsenceSchoolId(),
  });
  delete payload.attachments;
  delete payload.duration;
  delete payload.time_mode;
  delete payload.subject_auto;
  if (form.repeat !== "weekly") payload.repeat_until = "";
  if (form.type === "deregister") {
    payload.weekly = form.repeat === "weekly";
    delete payload.repeat;
  }
  return payload;
}

const ABSENCE_SUBMIT_TIMEOUT_MS = 120000;

function newAbsenceRequestId() {
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

function absencePost(payload, attachments) {
  const body = { ...payload, connection_id: payload.connection_id || openAbsenceSchoolId() };
  return attachments.length
    ? postFormData("api/absences", body, attachments)
    : postJson("api/absences", body, ABSENCE_SUBMIT_TIMEOUT_MS);
}

function absenceSettled(message, kind) {
  closeAbsenceForm();
  state.absence = null;
  toast(message, kind);
  loadAbsences();
  return true;
}

async function submitAbsence() {
  const form = state.absenceForm;
  const data = state.absence.data;
  const problem = absenceProblemEntry(form, data);
  if (problem) return problem.text;
  if (form.type === "absence") return submitOlderAbsence(form);
  const attachments = form.attachments || [];
  const payload = absencePayload(form, data.children || []);
  delete payload.request_id;
  delete payload.request_shape;
  const shape = JSON.stringify(payload) + attachments.map((file) => `${file.name}:${file.size}`).join("|");
  if (!form.request_id || form.request_shape !== shape) form.request_id = newAbsenceRequestId();
  form.request_shape = shape;
  payload.request_id = form.request_id;
  try {
    let result = await absencePost(payload, attachments);
    if (result && result.already_sent) {
      if (!(await olderAskSendAgain())) return t("api.absence.older.alreadySent");
      form.request_id = newAbsenceRequestId();
      Object.assign(payload, { request_id: form.request_id, send_again: true });
      result = await absencePost(payload, attachments);
    }
    if (result && result.ok) return absenceSettled(apiMessage(result, "absence.submit.ok"), "good");
    if (result && result.uncertain) return absenceSettled(apiMessage(result, "absence.older.sendUnclear"), "bad");
    toast(apiMessage(result, "absence.submit.rejected"), "bad");
    return t("absence.review.rejected");
  } catch (error) {
    if (handleApiFailure(error, payload.connection_id)) return t("absence.submit.failed");
    if (isTimeoutError(error) || /^http 5/.test(String(error && error.message))) return absenceSettled(t("absence.older.sendUnclear"), "bad");
    toast(t("absence.submit.failed"), "bad");
    return t("absence.submit.failed");
  }
}

const OLDER_SUBMIT_TIMEOUT_MS = 120000;
const OLDER_ERROR_STEPS = {
  profile: "child",
  from: "olderWhen",
  till: "olderTill",
  from_time: "olderTimes",
  till_time: "olderTimes",
  whole_day: "olderDayTime",
  kind: "olderKind",
  reason: "olderReason",
  files: "olderFiles",
};

function olderAbsenceDefaults(schema) {
  const today = isoDate(new Date());
  const first = schema.min && schema.min > today ? schema.min : today;
  const extra = {};
  for (const field of schema.extras || []) {
    if (field.type === "checkbox") extra[field.name] = false;
    else if (field.type === "select") extra[field.name] = ((field.options || [])[0] || {}).value || "";
    else extra[field.name] = "";
  }
  return {
    schema,
    from_date: first,
    till_date: first,
    duration: "one",
    time_mode: "school",
    from_time: ABSENCE_DEFAULT_FROM_TIME,
    till_time: ABSENCE_DEFAULT_TILL_TIME,
    reason: "",
    kind: "",
    extra,
    attachments: [],
    errors: {},
  };
}

function olderAbsencePath(form) {
  const schema = form.schema || {};
  const ids = [];
  if ((schema.profiles || []).length > 1) ids.push("child");
  ids.push("olderWhen");
  if (schema.till && form.duration === "more") ids.push("olderTill");
  if (olderTimesAsked(form)) {
    ids.push("olderDayTime");
    if (olderCustomTimes(form)) ids.push("olderTimes");
  }
  if (schema.kind) ids.push("olderKind");
  if (schema.reason) ids.push("olderReason");
  if ((schema.extras || []).length) ids.push("olderDetails");
  if (schema.files) ids.push("olderFiles");
  ids.push("review");
  return ids;
}

function olderManyDays(form) {
  return !!(form.schema && form.schema.till) && form.duration === "more";
}

function olderTimesAsked(form) {
  const schema = form.schema || {};
  return !!schema.times && !(schema.whole_day && olderManyDays(form));
}

function olderCustomTimes(form) {
  return olderTimesAsked(form) && form.time_mode === "custom";
}

function olderErrorStep(form, key) {
  const step = OLDER_ERROR_STEPS[key] || "olderDetails";
  const path = olderAbsencePath(form);
  if (path.includes(step)) return step;
  if (step === "olderTill") return "olderWhen";
  return "review";
}

function olderError(field, form, key) {
  const text = (form.errors || {})[key];
  if (!text) return field;
  field.append(iservText("span", { class: "err" }, text));
  const input = field.querySelector(".inp, .sel, .txt");
  if (input) input.classList.add("bad");
  return field;
}

function olderSetting(form, key, apply) {
  return (value) => {
    if (form.errors) delete form.errors[key];
    apply(value);
  };
}

function olderTimesText(form) {
  const schema = form.schema || {};
  if (!schema.times) return "";
  if (olderCustomTimes(form)) return `${form.from_time}–${form.till_time}`;
  return schema.whole_day ? t("absence.hours.full") : t("absence.time.schoolDay", { from: form.from_time, till: form.till_time });
}

function olderFieldLabel(field, fallbackKey) {
  return (field && field.label) || t(fallbackKey);
}

function olderOptionLabel(field, value) {
  const found = ((field && field.options) || []).find((option) => String(option.value) === String(value));
  return found ? found.label : "";
}

function olderExtraValue(field, value) {
  if (field.type === "checkbox") return t(value ? "common.yes" : "common.no");
  if (field.type === "select") return olderOptionLabel(field, value) || t("absence.wizard.none");
  if (field.type === "date") return value ? showDate(value) : t("absence.wizard.none");
  return value || t("absence.wizard.none");
}

function olderAbsenceFacts(form) {
  const schema = form.schema || {};
  const facts = [];
  facts.push({
    label: t("absence.fact.kind"),
    value: schema.kind ? olderOptionLabel(schema.kind, form.kind) || t("absence.wizard.none") : t("absence.entry.kind.absence"),
    step: schema.kind ? "olderKind" : "",
  });
  const till = schema.till && form.duration === "more" ? form.till_date : form.from_date;
  facts.push({ label: t("absence.fact.range"), value: absenceJoin(absenceRange(form.from_date, till), olderTimesText(form)), step: "olderWhen" });
  if (schema.reason) {
    facts.push({ label: olderFieldLabel(schema.reason, "absence.fact.reason"), value: form.reason || t("absence.wizard.none"), step: "olderReason" });
  }
  for (const field of schema.extras || []) {
    facts.push({ label: field.label || field.name, value: olderExtraValue(field, form.extra[field.name]), step: "olderDetails" });
  }
  if (schema.files) {
    const count = (form.attachments || []).length;
    facts.push({ label: t("absence.fact.attachments"), value: count ? tCount("absence.attachments.count", count) : t("absence.wizard.none"), step: "olderFiles" });
  }
  return facts;
}

function olderEmpty(field, value) {
  if (field.type === "checkbox") return value !== true;
  return !String(value || "").trim();
}

function olderAbsenceProblems(form) {
  const schema = form.schema || {};
  const list = [];
  const push = (step, text, hint) => list.push({ step, text, hint: hint || text });
  if (!form.from_date) push("olderWhen", t("api.absence.error.date"));
  if (schema.till && form.duration === "more" && form.till_date < form.from_date) push("olderTill", t("absence.problem.range"));
  if (olderCustomTimes(form)) {
    if (!form.from_time || !form.till_time) push("olderTimes", t("api.absence.older.error.time"));
    else if ((form.duration !== "more" || form.till_date === form.from_date) && form.till_time <= form.from_time) {
      push("olderTimes", t("absence.problem.timeOrder"));
    }
  }
  if (schema.kind && schema.kind.required && !form.kind) {
    push("olderKind", t("absence.wizard.need", { field: olderFieldLabel(schema.kind, "absence.fact.kind") }), t("absence.wizard.required"));
  }
  if (schema.reason && schema.reason.required && !String(form.reason || "").trim()) {
    push("olderReason", t("absence.problem.reason"), absenceNeed("absence.field.reason"));
  }
  for (const field of schema.extras || []) {
    if (field.required && olderEmpty(field, form.extra[field.name])) {
      push("olderDetails", t("absence.wizard.need", { field: field.label || field.name }));
    }
  }
  if (schema.files) {
    const files = form.attachments || [];
    const sizes = absenceAttachmentsProblem(form);
    if (sizes) push("olderFiles", sizes.text, sizes.hint);
    else if (schema.files.required && !files.length) push("olderFiles", t("absence.wizard.need", { field: t("absence.fact.attachments") }));
    else if (!schema.files.multiple && files.length > 1) push("olderFiles", t("api.absence.older.filesNotTaken"));
  }
  return list;
}

function olderExtraField(form, field) {
  const label = field.label || field.name;
  const set = olderSetting(form, field.name, (value) => {
    form.extra[field.name] = value;
    absenceFlow.sync();
  });
  if (field.type === "checkbox") {
    const box = el("input", { type: "checkbox" });
    box.checked = form.extra[field.name] === true;
    box.addEventListener("change", () => set(box.checked));
    return olderError(el("div", { class: "field-group" }, [el("label", { class: "cell check" }, [box, iservText("span", {}, label)])]), form, field.name);
  }
  const value = form.extra[field.name];
  let node;
  if (field.type === "select") node = selectField(label, value, field.options || [], set);
  else if (field.type === "date") node = dateField(label, value, field.min || null, set);
  else if (field.type === "time") node = timeField(label, value, set);
  else if (field.type === "textarea") node = textField(label, value, set);
  else node = inputField(label, value, "", set);
  return olderError(node, form, field.name);
}

const OLDER_STEP_BUILDERS = {
  olderWhen(form) {
    const schema = form.schema || {};
    const body = [
      olderError(dateField(t("absence.field.fromDay"), form.from_date, schema.min || null, olderSetting(form, "from", (value) => {
        form.from_date = value;
        if (form.till_date < value) form.till_date = value;
        wizRefresh();
      })), form, "from"),
    ];
    if (schema.till) {
      body.push(absenceSegment([
        { label: t("absence.duration.oneDay"), active: form.duration !== "more", onclick: () => absenceSetOlderDuration("one") },
        { label: t("absence.duration.moreDays"), active: form.duration === "more", onclick: () => absenceSetOlderDuration("more") },
      ]));
    }
    return { question: t("absence.wizard.step.leave.from"), body };
  },
  olderTill(form) {
    return {
      question: t("absence.wizard.step.leave.till"),
      body: [
        olderError(dateField(t("absence.field.tillDay"), form.till_date, form.from_date, olderSetting(form, "till", (value) => {
          form.till_date = value;
          wizRefresh();
        })), form, "till"),
      ],
    };
  },
  olderDayTime(form) {
    const schema = form.schema || {};
    const whole = schema.whole_day
      ? t("absence.hours.full")
      : t("absence.time.schoolDay", { from: ABSENCE_DEFAULT_FROM_TIME, till: ABSENCE_DEFAULT_TILL_TIME });
    return {
      question: t("absence.wizard.step.leave.dayTime"),
      body: [
        olderError(absenceSegment([
          { label: whole, active: form.time_mode !== "custom", onclick: () => absenceSetOlderTimeMode("school") },
          { label: t("absence.time.custom"), active: form.time_mode === "custom", onclick: () => absenceSetOlderTimeMode("custom") },
        ]), form, "whole_day"),
      ],
    };
  },
  olderTimes(form) {
    return {
      question: t("absence.wizard.step.leave.times"),
      body: [
        olderError(timeField(t("absence.field.start"), form.from_time, olderSetting(form, "from_time", (value) => {
          form.from_time = value;
          wizRefresh();
        })), form, "from_time"),
        olderError(timeField(t("absence.field.end"), form.till_time, olderSetting(form, "till_time", (value) => {
          form.till_time = value;
          wizRefresh();
        })), form, "till_time"),
      ],
    };
  },
  olderKind(form) {
    const field = form.schema.kind;
    return {
      list: true,
      question: t("absence.wizard.step.older.kind"),
      body: [
        olderError(el("div", { class: "sw-list" }, (field.options || []).map((option) =>
          absenceChoice(option.label, String(form.kind) === String(option.value), olderSetting(form, "kind", () => {
            form.kind = option.value;
            wizRefresh();
          }))
        )), form, "kind"),
      ],
    };
  },
  olderReason(form) {
    const field = form.schema.reason;
    const label = field.label || t(field.required ? "absence.field.reason" : "absence.field.reasonOptional");
    return {
      question: t("absence.wizard.step.sick.comment"),
      body: [
        olderError(textField(label, form.reason, olderSetting(form, "reason", (value) => {
          form.reason = value;
          absenceFlow.sync();
        })), form, "reason"),
      ],
    };
  },
  olderDetails(form) {
    return {
      question: t("absence.wizard.step.older.details"),
      body: (form.schema.extras || []).map((field) => olderExtraField(form, field)),
    };
  },
  olderFiles(form) {
    return {
      question: t("absence.wizard.step.leave.attachments"),
      body: [olderError(absenceAttachmentsField(form), form, "files")],
    };
  },
};

function absenceSetOlderDuration(key) {
  const form = state.absenceForm;
  if ((form.duration || "one") === key) return;
  form.duration = key;
  if (key === "one") form.till_date = form.from_date;
  wizRefresh();
  absenceAnnounceStep("olderTill", key === "more");
}

function absenceSetOlderTimeMode(key) {
  const form = state.absenceForm;
  if ((form.time_mode || "school") === key) return;
  form.time_mode = key;
  if (key === "school") {
    form.from_time = ABSENCE_DEFAULT_FROM_TIME;
    form.till_time = ABSENCE_DEFAULT_TILL_TIME;
  }
  if (form.errors) delete form.errors.whole_day;
  wizRefresh();
  absenceAnnounceStep("olderTimes", key === "custom");
}

function olderAbsencePayload(form) {
  const schema = form.schema || {};
  const timed = olderCustomTimes(form) || (!!schema.times && !schema.whole_day);
  return {
    connection_id: openAbsenceSchoolId(),
    type: "absence",
    student_id: form.student_id,
    from_date: form.from_date,
    till_date: schema.till && form.duration === "more" ? form.till_date : form.from_date,
    whole_day: !!schema.whole_day && !olderCustomTimes(form),
    from_time: timed ? form.from_time : "",
    till_time: timed ? form.till_time : "",
    reason: form.reason || "",
    kind: form.kind || "",
    extra: Object.assign({}, form.extra),
  };
}

function olderAskSendAgain() {
  return confirmAction({
    title: t("absence.older.sendAgainTitle"),
    text: t("api.absence.older.alreadySent"),
    confirmLabel: t("absence.older.sendAgain"),
  });
}

function olderPost(payload, files) {
  const body = { ...payload, connection_id: payload.connection_id || absenceSchoolId() };
  return files.length ? postFormData("api/absences", body, files) : postJson("api/absences", body, OLDER_SUBMIT_TIMEOUT_MS);
}

async function submitOlderAbsence(form) {
  const payload = olderAbsencePayload(form);
  const files = form.attachments || [];
  const key = olderSendKey(payload);
  if (olderLiveSends().some((send) => send.school === payload.connection_id && send.key === key)) {
    if (!(await olderAskSendAgain())) return t("api.absence.older.alreadySent");
    payload.send_again = true;
  }
  let result;
  try {
    result = await olderPost(payload, files);
    if (result && result.already_sent && !payload.send_again) {
      if (!(await olderAskSendAgain())) return t("api.absence.older.alreadySent");
      payload.send_again = true;
      result = await olderPost(payload, files);
    }
  } catch (error) {
    if (handleApiFailure(error, payload.connection_id)) return t("absence.submit.failed");
    olderRemember(payload, key);
    closeAbsenceForm();
    state.absence = null;
    toast(t("absence.older.sendUnclear"), "bad");
    loadAbsences();
    return true;
  }
  if (result && result.uncertain) olderRemember(payload, key);
  if (result && (result.ok || result.uncertain)) {
    closeAbsenceForm();
    state.absence = null;
    toast(apiMessage(result, "absence.submit.ok"), result.ok ? "good" : "bad");
    loadAbsences();
    return true;
  }
  const message = apiMessage(result, "absence.submit.rejected");
  const fields = Object.assign({}, (result && result.field_errors) || {});
  if (!Object.keys(fields).length && result && result.field) fields[result.field] = message;
  const keys = Object.keys(fields);
  toast(message, "bad");
  if (keys.length) {
    form.errors = fields;
    const step = olderErrorStep(form, keys[0]);
    if (step !== "review") return { step };
  }
  const general = ((result && result.errors) || []).join(" ");
  return general || message;
}

function olderEntryQuery(entry, school) {
  return `id=${encodeURIComponent(entry.id)}${school ? `&connection=${encodeURIComponent(school)}` : ""}`;
}

function olderAttachmentsBlock(entry) {
  const school = openAbsenceSchoolId();
  const content = el("div", { style: "margin-top:24px" }, [noteBlock(t("common.loading"))]);
  const wrap = el("div", { class: "older-attachments" }, [content]);
  loadOlderAttachments(entry, school, wrap, content);
  return wrap;
}

function olderSectionHead(text) {
  return el("div", { class: "section-head", style: "margin-top:24px" }, [el("span", { class: "overline" }, text)]);
}

const OLDER_DETAIL_KEEP_MS = 60000;
const olderDetails = new Map();

function olderDetail(entry, school) {
  const key = `${school}|${entry.id}`;
  const kept = olderDetails.get(key);
  if (kept && Date.now() - kept.at < OLDER_DETAIL_KEEP_MS) return kept.answer;
  const answer = getJson(`api/absences/older-detail?${olderEntryQuery(entry, school)}`)
    .catch(() => null)
    .then((result) => {
      if (!result || !result.ok) olderDetails.delete(key);
      return result;
    });
  olderDetails.set(key, { at: Date.now(), answer });
  return answer;
}

async function loadOlderAttachments(entry, school, wrap, content) {
  const result = await olderDetail(entry, school);
  if (!result || !result.ok) {
    content.replaceChildren(noteBlock(apiMessage(result, "absence.older.detailFailed")));
    return;
  }
  const files = (result.attachments || []).map((file) => ({
    filename: file.name,
    url: `api/absences/older-attachment?${olderEntryQuery(entry, school)}&key=${encodeURIComponent(file.key)}`,
  }));
  const log = result.log || [];
  if (!files.length && !result.can_upload && !log.length) {
    wrap.remove();
    return;
  }
  const parts = [];
  if (files.length || result.can_upload) parts.push(olderSectionHead(t("common.attachments")));
  if (files.length) parts.push(attachmentRows(files));
  for (const file of result.attachments || []) {
    if (file.deletable) parts.push(olderRemoveButton(entry, school, file));
  }
  if (result.can_upload) parts.push(olderUploadButton(entry, school));
  if (log.length) {
    parts.push(olderSectionHead(t("absence.older.log")));
    parts.push(el("div", { class: "rows" }, log.map((line) => el("div", { class: "row read" }, [
      el("div", { class: "row-main" }, [iservText("div", { class: "row-sub" }, line)]),
    ]))));
  }
  content.replaceChildren(...parts);
}

async function removeOlderAttachment(entry, school, file) {
  const ok = await confirmAction({
    title: t("absence.older.removeConfirm", { name: file.name }),
    text: t("absence.older.removeText"),
    confirmLabel: t("absence.older.remove"),
    destructive: true,
  });
  if (ok) {
    olderDetails.delete(`${school}|${entry.id}`);
    try {
      const result = await postJson("api/absences/older-attachment/delete", { connection_id: school, id: entry.id, key: file.key });
      toast(apiMessage(result, "absence.withdraw.failed"), result && result.ok ? "good" : "bad");
    } catch (error) {
      if (!handleApiFailure(error, school)) toast(t("absence.withdraw.failed"), "bad");
    }
  }
  openAbsenceSheet(entry);
}

function olderRemoveButton(entry, school, file) {
  return el("button", {
    class: "btn ghost slim",
    type: "button",
    style: "margin-top:8px",
    onclick: () => removeOlderAttachment(entry, school, file),
  }, [icon("trash", 14), iservText("span", {}, t("absence.older.removeAttachment", { name: file.name }))]);
}

function olderExportButton() {
  const school = openAbsenceSchoolId();
  const button = el("button", { class: "btn ghost slim", type: "button", style: "margin-top:20px" }, [icon("download", 14), t("absence.older.export")]);
  button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.disabled = true;
    try {
      const loaded = await fetchAppFile(`api/absences/older-export${school ? `?connection=${encodeURIComponent(school)}` : ""}`, "absences.csv");
      await saveFile(loaded.blob, loaded.filename);
    } catch (error) {
      toast(error.userMessage || t("api.absence.older.exportUnreadable"), "bad");
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

const OLDER_SEND_HOLD_MS = 10 * 60 * 1000;
let olderSends = [];

function olderSendKey(payload) {
  return `${payload.student_id}|${payload.from_date}|${payload.till_date}`;
}

function olderRemember(payload, key) {
  olderSends = olderLiveSends().filter((send) => send.school !== payload.connection_id || send.key !== key);
  olderSends.push({ school: payload.connection_id, key, payload, at: Date.now() });
}

function olderLiveSends() {
  olderSends = olderSends.filter((send) => Date.now() - send.at < OLDER_SEND_HOLD_MS);
  return olderSends;
}

function olderSettleSends(data, school) {
  if (!absenceOlderSource(data)) return;
  const listed = (data.entries || []).filter((entry) => !entry.unconfirmed).map((entry) => olderSendKey(entry));
  olderSends = olderLiveSends().filter((send) => send.school !== school || !listed.includes(send.key));
}

function olderLocalEntries(data, school) {
  if (!absenceOlderSource(data)) return [];
  const shown = (data.entries || []).map((entry) => olderSendKey(entry));
  return olderLiveSends().filter((send) => send.school === school && !shown.includes(send.key)).map((send, index) => ({
    id: `older:local:${index}`,
    kind: "absence",
    source: "older_page",
    label_key: "absence.entry.kind.absence",
    from_date: send.payload.from_date,
    till_date: send.payload.till_date,
    from_time: send.payload.from_time,
    till_time: send.payload.till_time,
    student_id: send.payload.student_id,
    status: "unconfirmed",
    unconfirmed: true,
    deletable: false,
    locked_reason_key: "api.absence.older.pending",
    technical: { id: "", created_at: "", class_code: "" },
  }));
}

const olderUploads = new Set();

function olderUploadButton(entry, school) {
  const input = el("input", { type: "file", style: "display:none" });
  const busy = `${school}|${entry.id}`;
  const button = el("button", { class: "btn ghost slim", type: "button" }, [icon("plus", 14), t("absence.attachments.add")]);
  button.disabled = olderUploads.has(busy);
  button.addEventListener("click", () => {
    if (!olderUploads.has(busy)) input.click();
  });
  input.addEventListener("change", async () => {
    const file = input.files && input.files[0];
    input.value = "";
    if (!file || olderUploads.has(busy)) return;
    olderUploads.add(busy);
    button.disabled = true;
    try {
      await olderSendUpload(entry, school, file);
    } finally {
      olderUploads.delete(busy);
      button.disabled = false;
    }
  });
  return el("div", { class: "field-group", style: "margin-top:12px" }, [button, input, el("span", { class: "hint" }, t("absence.older.attachHint"))]);
}

async function olderSendUpload(entry, school, file) {
  if (file.size > MAX_ATTACHMENT_BYTES) {
    toast(t("absence.attachments.oversized"), "bad");
    return;
  }
  const ok = await confirmAction({
    title: t("absence.older.attachConfirm", { name: file.name }),
    text: t("absence.older.attachHint"),
    confirmLabel: t("absence.confirm.button"),
  });
  if (!ok) {
    openAbsenceSheet(entry);
    return;
  }
  try {
    olderDetails.delete(`${school}|${entry.id}`);
    const result = await postFormData("api/absences/older-attachment", { connection_id: school, id: entry.id }, [file]);
    const good = !!(result && result.ok);
    toast(apiMessage(result, "absence.submit.failed"), good ? "good" : "bad");
  } catch (error) {
    if (!handleApiFailure(error, school)) toast(t("absence.submit.failed"), "bad");
  }
  openAbsenceSheet(entry);
}
