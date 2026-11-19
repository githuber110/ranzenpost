const SOURCE_NEW = "school-app";
const SOURCE_OLD = "time-table";
const SOURCE_KEYS = [SOURCE_NEW, SOURCE_OLD];
const SOURCE_HINT_STORE = "sourceHintDismissed";

function sourceFacts(data) {
  const sources = data && data.sources && typeof data.sources === "object" ? data.sources : null;
  if (!sources || !SOURCE_KEYS.every((key) => sources[key] && typeof sources[key] === "object")) return null;
  return sources;
}

function sourceCount(facts) {
  return facts && Number.isFinite(facts.changes) ? facts.changes : null;
}

function connectionSourceChoice(connectionId) {
  const entry = connectionOf(connectionId);
  return entry && entry.timetable_choice === SOURCE_OLD ? SOURCE_OLD : SOURCE_NEW;
}

function sourceChosen(data) {
  return data && data.source_choice === SOURCE_OLD ? SOURCE_OLD : SOURCE_NEW;
}

function sourceOther(key) {
  return key === SOURCE_OLD ? SOURCE_NEW : SOURCE_OLD;
}

function sourceLabel(key) {
  return t(key === SOURCE_OLD ? "source.old" : "source.new");
}

function sourceChoiceOffered(connectionId) {
  const entry = connectionOf(connectionId);
  return !!entry && (entry.timetable_both === true || entry.timetable_choice === SOURCE_OLD);
}

function sourceChoiceSettingRows(connectionId) {
  if (!sourceChoiceOffered(connectionId)) return [];
  return [settingRow(t("source.row"), sourceLabel(connectionSourceChoice(connectionId)), () => openSourceSheet(connectionId), "source-setting")];
}

function sourceFactLine(facts) {
  if (!facts) return "";
  const count = sourceCount(facts);
  const parts = [count === null ? t("source.unknown") : tCount("source.changes", count)];
  if (facts.last_updated) parts.push(t("source.updated", { time: showDateTime(facts.last_updated) }));
  return parts.join(" · ");
}

function sourceChildFacts(connectionId) {
  return state.children
    .filter((child) => schoolOfChild(child) === connectionId)
    .map((child) => ({ child, facts: sourceFacts(overviewWeekData(child.key, 0)) }))
    .filter((entry) => entry.facts);
}

function sourceOptionFacts(key, rows) {
  if (!rows.length) return [el("small", {}, t("source.unknown"))];
  if (rows.length === 1) return [el("small", {}, sourceFactLine(rows[0].facts[key]))];
  return rows.map((row) => el("small", {}, `${childFirstName(row.child)}: ${sourceFactLine(row.facts[key])}`));
}

function openSourceSheet(connectionId) {
  openSheet(() => sourceSheet(connectionId));
}

function sourceSheet(connectionId) {
  const rows = sourceChildFacts(connectionId);
  const chosen = connectionSourceChoice(connectionId);
  return sheet(t("source.row"), [
    el("p", { class: "sheet-hint" }, t("source.sheet.text")),
    el("div", { class: "opt-list" }, SOURCE_KEYS.map((key) =>
      el("button", {
        class: "opt source-opt",
        type: "button",
        "data-source": key,
        "aria-pressed": String(chosen === key),
        onclick: () => chooseSource(connectionId, key),
      }, [el("span", {}, [el("b", {}, sourceLabel(key)), ...sourceOptionFacts(key, rows)])])
    )),
  ]);
}

async function chooseSource(connectionId, key) {
  closeSheet();
  const result = await persistConnection(connectionId, { timetable_choice: key });
  announceSave(result);
}

function sourceHintStore(connectionId) {
  return `${SOURCE_HINT_STORE}:${connectionId}`;
}

function sourceHintDismissed(connectionId, data) {
  return readStoredText(sourceHintStore(connectionId)) === String(data.start_date || "");
}

function dismissSourceHint(connectionId, data) {
  writeStoredText(sourceHintStore(connectionId), String(data.start_date || ""));
  rerender();
}

function sourceHintDue(data) {
  const facts = sourceFacts(data);
  if (!facts || data.week_offset !== 0) return false;
  const chosen = sourceCount(facts[sourceChosen(data)]);
  const other = sourceCount(facts[sourceOther(sourceChosen(data))]);
  return chosen === 0 && other !== null && other > 0;
}

function sourceNotice(data) {
  const connectionId = currentConnectionId();
  if (!data || !connectionId) return null;
  if (data.source_choice_missing) {
    return el("div", { class: "note source-note", role: "status" }, [
      icon("alert", 16),
      el("span", {}, t("source.missing")),
      el("button", { class: "link-btn", type: "button", onclick: () => openSourceSheet(connectionId) }, t("source.change")),
    ]);
  }
  if (!sourceHintDue(data) || sourceHintDismissed(connectionId, data)) return null;
  const other = sourceOther(sourceChosen(data));
  const count = sourceCount(sourceFacts(data)[other]);
  return el("div", { class: "note source-note", role: "status" }, [
    icon("alert", 16),
    el("span", {}, tCount(other === SOURCE_OLD ? "source.hint.old" : "source.hint.new", count)),
    el("button", { class: "btn slim source-switch", type: "button", onclick: () => chooseSource(connectionId, other) }, t("source.switch")),
    el("button", { class: "link-btn source-later", type: "button", onclick: () => dismissSourceHint(connectionId, data) }, t("source.later")),
  ]);
}
