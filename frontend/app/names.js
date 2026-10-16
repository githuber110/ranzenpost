function openNamesPage() {
  state.namesPage = { connectionId: editingConnectionId(), schoolId: state.settingsSchoolId, saving: false };
  discardPageForm();
  openSettingsPage(SETTINGS_PAGE_NAMES);
}

function closeNamesPage() {
  const page = state.namesPage;
  state.namesPage = null;
  discardPageForm();
  state.settingsPage = null;
  dropSheet();
  if (page && page.schoolId && connectionOf(page.schoolId)) state.settingsSchoolId = page.schoolId;
  showSettingsChange();
}

function namesPageConnection() {
  return (state.namesPage && state.namesPage.connectionId) || editingConnectionId();
}

function namesPageView() {
  const config = connectionConfig(namesPageConnection());
  const draft = pageState(() => ({
    subjects: copy(config.subjects || {}),
    teachers: copy(config.teachers || {}),
  }));
  const saving = !!(state.namesPage && state.namesPage.saving);
  const save = el("button", {
    class: "btn names-save",
    type: "button",
    disabled: saving ? "disabled" : null,
    onclick: saveNamesPage,
  }, saving ? [el("span", { class: "spin" }), t("common.saving")] : t("common.save"));
  return el("div", { class: "names-page" }, [
    namesGroup("subjects", draft.subjects, (code) => subjectRow(code, draft.subjects[code])),
    namesGroup("teachers", draft.teachers, (code) => teacherRow(code, draft.teachers[code])),
    el("div", { class: "btn-stack names-actions" }, [save]),
  ]);
}

async function saveNamesPage() {
  const page = state.namesPage;
  const draft = state.pageForm;
  if (!page || !draft || page.saving) return;
  page.saving = true;
  rerender();
  const result = await persistConnection(page.connectionId, { subjects: draft.subjects, teachers: draft.teachers });
  page.saving = false;
  if (!result.ok && !result.handled) {
    toast(result.message || t("common.saveFailed"), "bad");
    return;
  }
  if (state.namesPage === page) closeNamesPage();
  announceSave(result);
}

function namesGroup(kind, entries, build) {
  const codes = sortedCodes(entries);
  const head = el("div", { class: "section-head names-head" }, [
    el("span", { class: "overline" }, t(`settings.${kind}`)),
    el("span", { class: "names-count" }, t(`settings.${kind}.count`, { count: formatNumber(codes.length) })),
  ]);
  const inner = codes.length
    ? el("div", { class: "field-group" }, codes.map(build))
    : el("p", { class: "dlg-text" }, t(`settings.${kind}.empty`));
  return el("div", { class: "names-block" }, [head, inner]);
}

function sortedCodes(entries) {
  return Object.keys(entries || {}).sort((a, b) => a.localeCompare(b, currentLanguage(), { numeric: true, sensitivity: "base" }));
}

function subjectRow(code, subject) {
  const swatch = el("button", { class: "swatch swatch-trigger", type: "button", "aria-label": t("settings.subjects.color", { code }) });
  const applySwatchColor = () => {
    const vars = RanzenpostColour.cellVars(subject.color || SUBJECT_COLOR_NAMES[hashIndex(code, SUBJECT_COLOR_NAMES.length)]);
    swatch.style.background = vars.fill;
  };
  applySwatchColor();
  swatch.addEventListener("click", () => openColorDialog(subject, applySwatchColor, subject.code || code));
  const input = iservText("input", { class: "inp", type: "text", value: subject.label || "", placeholder: code, "aria-label": t("settings.subjects.name", { code }) });
  input.addEventListener("input", () => { subject.label = input.value; });
  const codeInput = iservText("input", {
    class: "inp subject-code-input",
    type: "text",
    value: subject.code || code,
    placeholder: code,
    maxlength: "6",
    "aria-label": t("settings.subjects.code", { code }),
  });
  codeInput.addEventListener("input", () => {
    subject.code = codeInput.value.trim().toUpperCase();
    delete subject.derived;
  });
  const codeOpen = !!subject.code && subject.code !== code && !subject.derived;
  const codeField = el("label", { class: "field subject-code", hidden: codeOpen ? null : "hidden" }, [el("span", { class: "lbl" }, t("settings.names.code")), codeInput]);
  const fields = el("div", { class: codeOpen ? "subject-fields code-open" : "subject-fields" }, [
    el("label", { class: "field subject-name" }, [el("span", { class: "lbl" }, t("settings.names.name")), input]),
    codeField,
  ]);
  const codeToggle = el("button", {
    class: "link-btn subject-code-toggle",
    type: "button",
    hidden: codeOpen ? "hidden" : null,
    "aria-label": t("settings.names.codeChangeFor", { code }),
    onclick: () => {
      codeField.hidden = false;
      codeToggle.hidden = true;
      fields.classList.add("code-open");
      codeInput.focus();
    },
  }, t("settings.names.codeChange"));
  return el("div", { class: "cell" }, [
    el("div", { class: "cell-head" }, [swatch, iservText("span", { class: "field-label" }, code), codeToggle]),
    fields,
  ]);
}

function closeColorDialog() {
  const close = state.colorDialogClose;
  state.colorDialogClose = null;
  if (close) close();
}

function colourSwatch(name, selected, onPick) {
  const button = el("button", {
    class: "swatch-btn",
    type: "button",
    "data-color": name,
    "aria-label": t(`colour.${name}`),
    title: t(`colour.${name}`),
    "aria-pressed": String(selected),
    onclick: () => onPick(name),
  }, [icon("check", 18)]);
  button.style.background = `var(--subject-${name}-fill)`;
  button.style.color = `var(--subject-${name}-ink)`;
  return button;
}

function colourPreviewCell(code, tone) {
  const cell = el("div", { class: "tt-cell subject subject-bar colour-preview-cell" }, [iservText("span", { class: "sub" }, code)]);
  cell.style.setProperty("--subject-cell-fill", tone.fill);
  cell.style.setProperty("--subject-cell-ink", tone.ink);
  cell.style.setProperty("--subject-bar", tone.bar);
  return cell;
}

function colourPreview(code, value) {
  const colour = RanzenpostColour.resolve(value || RanzenpostColour.DEFAULT_NAME);
  return el("div", { class: "colour-preview" }, [
    el("div", { class: "colour-stage light" }, [colourPreviewCell(code, colour.light), el("span", { class: "colour-stage-label" }, t("settings.color.preview.light"))]),
    el("div", { class: "colour-stage dark" }, [colourPreviewCell(code, colour.dark), el("span", { class: "colour-stage-label" }, t("settings.color.preview.dark"))]),
  ]);
}

function openColorDialog(subject, onChange, code) {
  closeColorDialog();
  let close = () => {};
  const initialHex = RanzenpostColour.isHex(subject.color) ? subject.color.toLowerCase() : RanzenpostColour.resolve(subject.color || RanzenpostColour.DEFAULT_NAME).hex;
  const pickName = (name) => {
    subject.color = name;
    subject.color_source = COLOR_SOURCE_USER;
    onChange();
    close();
  };
  const swatches = SUBJECT_COLOR_NAMES.map((name) => colourSwatch(name, subject.color === name, pickName));
  swatches.push(
    el("button", {
      class: "swatch-btn auto",
      type: "button",
      "aria-label": t("settings.color.auto"),
      "aria-pressed": String(!subject.color),
      onclick: () => { subject.color = ""; subject.color_source = COLOR_SOURCE_AUTO; onChange(); close(); },
    }, [icon("restore", 16)])
  );
  const picker = el("input", { class: "colour-picker", type: "color", value: initialHex, "aria-label": t("settings.color.picker") });
  const hexField = el("input", {
    class: "inp colour-hex",
    type: "text",
    dir: "ltr",
    value: initialHex,
    maxlength: "7",
    autocomplete: "off",
    spellcheck: "false",
    inputmode: "text",
    "aria-label": t("settings.color.hex"),
    "aria-invalid": "false",
  });
  const ownChosen = RanzenpostColour.isHex(subject.color);
  const own = el("div", { class: "colour-own", id: "colour-own", "aria-pressed": String(ownChosen), hidden: ownChosen ? null : "hidden" });
  const ownToggle = el("button", {
    class: "link-btn colour-own-toggle",
    type: "button",
    "aria-expanded": String(ownChosen),
    "aria-controls": "colour-own",
    onclick: () => {
      const open = own.hidden;
      own.hidden = !open;
      ownToggle.setAttribute("aria-expanded", String(open));
    },
  }, t("settings.color.own"));
  let preview = colourPreview(code, subject.color);
  const applyHex = (hex) => {
    subject.color = hex;
    subject.color_source = COLOR_SOURCE_USER;
    onChange();
    own.setAttribute("aria-pressed", "true");
    for (const button of swatches) button.setAttribute("aria-pressed", "false");
    const next = colourPreview(code, hex);
    preview.replaceWith(next);
    preview = next;
  };
  picker.addEventListener("input", () => {
    const hex = RanzenpostColour.parseHex(picker.value);
    if (!hex) return;
    hexField.value = hex;
    hexField.setAttribute("aria-invalid", "false");
    applyHex(hex);
  });
  hexField.addEventListener("input", () => {
    const hex = RanzenpostColour.parseHex(hexField.value);
    hexField.setAttribute("aria-invalid", String(!hex));
    if (!hex) return;
    picker.value = hex;
    applyHex(hex);
  });
  hexField.addEventListener("blur", () => {
    const hex = RanzenpostColour.parseHex(hexField.value);
    if (hex) hexField.value = hex;
  });
  own.append(
    el("span", { class: "hint" }, t("settings.color.own.hint")),
    el("div", { class: "colour-own-fields" }, [picker, hexField]),
    preview
  );
  const dialog = el("div", { class: "sheet color-dialog", role: "dialog", "aria-modal": "true" }, [
    el("div", { class: "sheet-head" }, [
      el("div", { class: "sheet-title", tabindex: "-1" }, t("settings.subjects.color", { code })),
      el("div", { class: "sheet-head-actions" }, [
        el("button", { class: "sheet-close", type: "button", "aria-label": t("common.close"), onclick: () => close() }, [icon("close", 16)]),
      ]),
    ]),
    el("div", { class: "sheet-body" }, [
      el("div", { class: "swatch-grid" }, swatches),
      ownToggle,
      own,
    ]),
  ]);
  dialog.addEventListener("click", (event) => event.stopPropagation());
  const scrim = el("div", { class: layoutMode() === "phone" ? "color-dialog-scrim" : "color-dialog-scrim dialog" });
  scrim.addEventListener("click", (event) => { event.stopPropagation(); close(); });
  const onKey = (event) => { if (event.key === "Escape") close(); };
  close = () => {
    scrim.remove();
    document.removeEventListener("keydown", onKey);
    state.colorDialogClose = null;
  };
  document.addEventListener("keydown", onKey);
  scrim.append(dialog);
  (root().querySelector(".scrim") || root()).append(scrim);
  state.colorDialogClose = close;
  window.setTimeout(() => {
    const heading = dialog.querySelector(".sheet-title");
    if (heading && document.contains(heading)) heading.focus();
  }, 0);
}

function teacherRow(code, teacher) {
  const input = iservText("input", { class: "inp", type: "text", value: teacher.label || "", placeholder: code, "aria-label": t("settings.teachers.name", { code }) });
  input.addEventListener("input", () => { teacher.label = input.value; teacher.label_source = ""; });
  return el("div", { class: "cell" }, [
    el("div", { class: "cell-head" }, [iservText("span", { class: "field-label" }, code)]),
    el("label", { class: "field teacher-name" }, [el("span", { class: "lbl" }, t("settings.names.person")), input]),
  ]);
}
