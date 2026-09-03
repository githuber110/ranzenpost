(function () {
  const el = (tag, attrs = {}, children = []) => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "class") node.className = value;
      else if (key === "html") node.innerHTML = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else if (value !== null && value !== undefined && value !== false) node.setAttribute(key, value);
    }
    for (const child of [].concat(children)) {
      if (child || child === 0) node.append(child.nodeType ? child : document.createTextNode(child));
    }
    return node;
  };

  function requestBase() {
    const url = new URL(document.baseURI || window.location.href);
    url.search = "";
    url.hash = "";
    const path = url.pathname;
    const cut = path.lastIndexOf("/") + 1;
    const last = path.slice(cut);
    url.pathname = last.includes(".") ? path.slice(0, cut) : path.endsWith("/") ? path : `${path}/`;
    return url.toString();
  }

  const REQUEST_BASE = requestBase();
  const requestUrl = (path) => new URL(path, REQUEST_BASE).toString();

  async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (body) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(requestUrl(path), opts);
    if (!res.ok) throw new Error("http " + res.status);
    return res.json();
  }

  let phonesDone = false;

  function label(key, vars) {
    return window.t ? window.t(key, vars) : key;
  }

  function countLabel(key, count) {
    return window.tCount ? window.tCount(key, count) : label(key, { count });
  }

  function need(fieldKey) {
    return label("wizard.need", { field: label(fieldKey) });
  }

  const WIZARD_TEXTS = {
    back: "common.back",
    goal: "wizard.progress.goal",
    progress: "wizard.progress",
    progressTotal: "wizard.progress.total",
    failed: "wizard.error.service.text",
  };

  async function saveLanguage(choice, after) {
    if (window.applyLanguageChoice) await window.applyLanguageChoice(choice);
    let saved = false;
    try {
      const config = (await api("GET", "api/config")) || {};
      config.language = choice;
      await api("POST", "api/config", config);
      saved = true;
    } catch (error) {
      saved = false;
    }
    if (window.rememberLanguageChoice) window.rememberLanguageChoice(choice, saved);
    after();
  }

  function languageRow(onChange) {
    const choices = window.languageChoices ? window.languageChoices() : ["system"];
    const active = window.currentLanguageChoice ? window.currentLanguageChoice() : "system";
    const select = el("select", { class: "wz-input wz-language", "aria-label": label("wizard.language.label") });
    for (const choice of choices) {
      const option = el("option", { value: choice }, label(`language.${choice}`));
      if (choice === active) option.selected = true;
      select.append(option);
    }
    select.addEventListener("change", () => saveLanguage(select.value, onChange));
    return el("label", { class: "wz-language-row" }, [
      el("span", { class: "wz-label" }, label("wizard.language.label")),
      select,
    ]);
  }

  function stepList(state) {
    const steps = state && state.has_2fa === false ? ["url", "login", "child"] : ["url", "login", "connect", "child"];
    return steps.concat(["phones"]);
  }

  function errorText(err) {
    if (err && err.message_key) return label(err.message_key, err.message_vars);
    return (err && err.message) || "";
  }

  function renderWizard(container, onDone) {
    phonesDone = false;
    let wzState = {};
    let flow = null;
    let fields = {};
    let draft = { url: "", username: "" };
    let children = { status: "idle", list: [], picked: "" };
    let school = { status: "idle", phones: [], regions: [], region: "", suggestion: null, rows: [], select: null, typed: null };

    const mount = (node) => container.replaceChildren(node);

    let bannerSerial = 0;

    function errorBanner() {
      const err = wzState && wzState.error;
      if (!err || err.code === "paused" || err.code === "locked") return null;
      const text = errorText(err);
      if (!text) return null;
      bannerSerial += 1;
      return el("div", { class: "wz-error", role: "alert", "data-attempt": String(bannerSerial) }, text);
    }

    function loadingCard() {
      return el("div", { class: "wz" }, [el("div", { class: "card wz-card wz-loading" }, label("common.loading"))]);
    }

    function fatalCard(title, text) {
      return el("div", { class: "wz" }, [
        el("div", { class: "card wz-card" }, [
          el("h2", { class: "wz-title" }, title),
          el("p", { class: "wz-sub" }, text),
          el("button", { class: "btn-primary", type: "button", onclick: load }, label("common.retry")),
        ]),
      ]);
    }

    function waitCard() {
      const message = errorText(wzState.error) || label("wizard.wait.text");
      return el("div", { class: "wz" }, [
        el("div", { class: "card wz-card" }, [
          el("div", { class: "wz-wait" }, [
            el("span", { class: "wz-wait-icon" }, "⏳"),
            el("div", {}, [el("b", {}, label("wizard.wait.title")), el("p", { class: "wz-sub" }, message)]),
          ]),
          el("button", { class: "btn-primary", type: "button", onclick: load }, label("common.retry")),
        ]),
      ]);
    }

    function resetPanel() {
      if (!flow || flow.node.querySelector(".sw-confirm")) return;
      let panel;
      const close = () => panel.remove();
      const confirm = () => {
        close();
        flow.destroy();
        flow = null;
        mount(loadingCard());
        api("POST", "api/wizard/reset")
          .then((next) => route(next))
          .catch(() => mount(fatalCard(label("wizard.error.action.title"), label("wizard.error.service.text"))));
      };
      panel = el("div", { class: "card wz-card wz-confirm sw-confirm", role: "alertdialog", "aria-modal": "true", "aria-label": label("wizard.reset.aria") }, [
        el("p", { class: "dlg-text" }, label("wizard.reset.text")),
        el("div", { class: "btn-stack" }, [
          el("button", { class: "btn destructive", type: "button", onclick: confirm }, label("wizard.nav.restart")),
          el("button", { class: "btn ghost", type: "button", onclick: close }, label("common.cancel")),
        ]),
      ]);
      flow.node.append(panel);
    }

    function trailing() {
      return el("button", { class: "wz-nav reset", type: "button", onclick: resetPanel }, label("wizard.nav.restart"));
    }

    function textInput(attrs) {
      return el("input", Object.assign({ class: "wz-input", autocomplete: "off" }, attrs));
    }

    function urlBody() {
      fields = {};
      fields.url = textInput({
        type: "text",
        name: "url",
        dir: "ltr",
        inputmode: "url",
        autocapitalize: "none",
        spellcheck: "false",
        placeholder: label("wizard.url.placeholder"),
        value: draft.url || wzState.school_url || "",
        "aria-label": label("wizard.url.label"),
      });
      fields.url.addEventListener("input", () => {
        draft.url = fields.url.value;
        flow.sync();
      });
      return [
        el("p", { class: "wz-sub" }, label("wizard.url.text")),
        errorBanner(),
        languageRow(() => flow.render()),
        el("label", { class: "wz-label" }, label("wizard.url.label")),
        fields.url,
      ];
    }

    function loginBody() {
      fields = {};
      fields.username = textInput({
        type: "text",
        name: "username",
        dir: "ltr",
        autocomplete: "username",
        autocapitalize: "none",
        spellcheck: "false",
        placeholder: label("wizard.login.username.placeholder"),
        value: draft.username || wzState.username || "",
        "aria-label": label("wizard.login.username.label"),
      });
      fields.password = textInput({
        type: "password",
        name: "password",
        autocomplete: "current-password",
        placeholder: label("common.password"),
        "aria-label": label("common.password"),
      });
      fields.username.addEventListener("input", () => {
        draft.username = fields.username.value;
        flow.sync();
      });
      fields.password.addEventListener("input", () => flow.sync());
      return [
        el("p", { class: "wz-sub" }, label("wizard.login.text")),
        errorBanner(),
        el("label", { class: "wz-label" }, label("wizard.login.username.label")),
        fields.username,
        el("label", { class: "wz-label" }, label("common.password")),
        fields.password,
        el("div", { class: "wz-lock" }, [el("span", { class: "wz-lock-icon" }, "🔒"), label("wizard.login.privacy")]),
      ];
    }

    function connectBody() {
      fields = {};
      const second = !!wzState.awaiting_confirm;
      fields.code = textInput({
        class: "wz-input wz-code",
        type: "text",
        name: "code",
        inputmode: "numeric",
        pattern: "[0-9]*",
        maxlength: "6",
        autocomplete: "one-time-code",
        placeholder: label("wizard.connect.code.placeholder"),
        "aria-label": label("wizard.connect.code.aria"),
      });
      fields.code.addEventListener("input", () => flow.sync());
      return [
        el("p", { class: "wz-sub" }, label(second ? "wizard.connect.second.text" : "wizard.connect.text")),
        second && wzState.stale_tokens
          ? el("div", { class: "wz-warn" }, countLabel("wizard.connect.staleTokens", wzState.stale_tokens))
          : null,
        errorBanner(),
        el("label", { class: "wz-label" }, label(second ? "wizard.connect.code.labelNext" : "wizard.connect.code.label")),
        fields.code,
        el("div", { class: "wz-hint-line" }, label(second ? "wizard.connect.hintNext" : "wizard.connect.hint")),
      ];
    }

    function childBody() {
      if (children.status === "loading") return [el("p", { class: "wz-sub" }, label("common.loading"))];
      if (children.status === "error") {
        return [
          el("div", { class: "wz-error", role: "alert" }, label("wizard.error.service.text")),
          el("button", { class: "wz-skip", type: "button", onclick: loadChildren }, label("common.reload")),
        ];
      }
      if (!children.list.length) {
        return [
          el("p", { class: "wz-sub" }, label("wizard.child.none.text")),
          el("button", { class: "wz-skip", type: "button", onclick: loadChildren }, label("common.reload")),
        ];
      }
      const list = el("div", { class: "wz-children" });
      for (const child of children.list) {
        const initial = (child.name || "?").trim().charAt(0).toUpperCase();
        const name = child.class_name
          ? label("child.nameWithClass", { name: child.name, class: child.class_name })
          : child.name || child.child_id;
        const button = el("button", {
          class: "wz-child",
          type: "button",
          "aria-pressed": String(children.picked === child.child_id),
          onclick: () => {
            children.picked = child.child_id;
            flow.render();
          },
        }, [el("span", { class: "wz-child-avatar" }, initial), el("span", { class: "wz-child-name" }, name)]);
        list.append(button);
      }
      return [list];
    }

    function phoneRow(entry) {
      const description = textInput({
        type: "text",
        placeholder: label("common.phone.label"),
        value: (entry && entry.label) || "",
        "aria-label": label("common.phone.label"),
      });
      const number = textInput({
        class: "wz-input wz-phone-number",
        type: "tel",
        inputmode: "tel",
        autocomplete: "tel",
        placeholder: label("common.phone.number"),
        value: (entry && entry.number) || "",
        "aria-label": label("common.phone.number"),
      });
      const remove = el("button", { class: "wz-phone-remove", type: "button", "aria-label": label("common.phone.remove") }, "✕");
      return { node: el("div", { class: "wz-phone-row" }, [description, remove, number]), label: description, number, remove };
    }

    function holidayRegionRow() {
      const select = el("select", { class: "wz-input wz-language", "aria-label": label("holidays.settings.label") });
      select.append(el("option", { value: "" }, label("holidays.settings.off")));
      for (const region of school.regions) select.append(el("option", { value: region.code }, label(region.name_key)));
      const suggestion = school.suggestion;
      const suggested = !school.region && suggestion && suggestion.confidence === "high" ? suggestion.region || "" : "";
      select.value = school.region || suggested || "";
      school.select = select;
      const hints = suggested && suggestion.origin_key
        ? [label(suggestion.origin_key), label("holidays.suggestion.confirm")]
        : [label("holidays.wizard.hint")];
      const node = el("div", { class: "wz-holiday-row" }, [
        el("label", { class: "wz-language-row" }, [el("span", { class: "wz-label" }, label("holidays.wizard.title")), select]),
      ]);
      for (const hint of hints) node.append(el("div", { class: "wz-hint-line" }, hint));
      return node;
    }

    function phonesBody() {
      if (school.status === "loading") return [el("p", { class: "wz-sub" }, label("common.loading"))];
      if (school.status === "error") {
        return [
          el("div", { class: "wz-error", role: "alert" }, label("wizard.phones.loadError")),
          el("button", { class: "wz-skip", type: "button", onclick: loadSchool }, label("common.reload")),
          el("button", { class: "wz-skip", type: "button", onclick: finishPhones }, label("common.skip")),
        ];
      }
      const typed = school.typed;
      school.typed = null;
      school.rows = [];
      const list = el("div", { class: "wz-phones" });
      const addRow = (entry) => {
        const row = phoneRow(entry);
        row.remove.addEventListener("click", () => {
          const index = school.rows.indexOf(row);
          if (index < 0) return;
          school.rows.splice(index, 1);
          row.node.remove();
          if (!school.rows.length) addRow(null);
        });
        school.rows.push(row);
        list.append(row.node);
        return row;
      };
      const stored = (typed || school.phones).filter((entry) => entry && (entry.label || entry.number));
      if (stored.length) stored.forEach((entry) => addRow(entry));
      else addRow(null);
      const add = el("button", { class: "wz-phone-add", type: "button" }, label("wizard.phones.add"));
      add.addEventListener("click", () => addRow(null).label.focus());
      return [
        el("p", { class: "wz-sub" }, label("wizard.school.text")),
        el("div", { class: "wz-label" }, label("wizard.school.phones")),
        list,
        add,
        el("div", { class: "wz-hint-line" }, label("wizard.phones.example")),
        holidayRegionRow(),
        el("button", { class: "wz-skip", type: "button", onclick: finishPhones }, label("common.skip")),
      ];
    }

    function post(path, body) {
      return api("POST", path, body).then((next) => {
        route(next);
        return {};
      });
    }

    function stepFor(id) {
      if (id === "url") {
        return {
          question: label("wizard.url.title"),
          body: urlBody,
          block: () => (fields.url && fields.url.value.trim() ? "" : need("wizard.url.label")),
          blockFocus: () => fields.url,
          nextLabel: label("common.next"),
          busyLabel: label("common.pleaseWait"),
          onNext: () => post("api/wizard/url", { url: fields.url.value.trim() }),
        };
      }
      if (id === "login") {
        return {
          question: label("wizard.login.title"),
          body: loginBody,
          block: () => {
            if (!fields.username || !fields.username.value.trim()) return need("wizard.login.username.label");
            if (!fields.password || !fields.password.value) return need("common.password");
            return "";
          },
          blockFocus: () => (fields.username && !fields.username.value.trim() ? fields.username : fields.password),
          nextLabel: label("wizard.login.submit"),
          busyLabel: label("common.pleaseWait"),
          onNext: () =>
            post("api/wizard/login", {
              username: fields.username.value.trim(),
              password: fields.password.value,
            }),
        };
      }
      if (id === "connect") {
        const second = !!wzState.awaiting_confirm;
        return {
          question: label(second ? "wizard.connect.second.title" : "wizard.connect.title"),
          body: connectBody,
          hint: label("wizard.connect.privacy"),
          block: () => (fields.code && fields.code.value.trim() ? "" : need("wizard.connect.code.label")),
          blockFocus: () => fields.code,
          nextLabel: label(second ? "wizard.connect.finish" : "common.next"),
          busyLabel: label("common.pleaseWait"),
          onNext: () => post("api/wizard/connect", { code: fields.code.value.trim() }),
        };
      }
      if (id === "child") {
        const empty = children.status === "ready" && !children.list.length;
        return {
          list: true,
          scroll: true,
          question: label(empty ? "wizard.child.none.title" : "wizard.child.title"),
          body: childBody,
          hint: empty ? "" : label("wizard.child.text"),
          block: () => {
            if (empty || children.status !== "ready") return "";
            return children.picked ? "" : need("wizard.child.title");
          },
          nextLabel: label(empty ? "wizard.child.none.finish" : "common.next"),
          busyLabel: label("common.pleaseWait"),
          onNext: () => {
            if (empty) return post("api/wizard/skip-child");
            const child = children.list.find((entry) => entry.child_id === children.picked);
            if (!child) return false;
            return post("api/wizard/child", {
              child_id: child.child_id,
              name: child.name || "",
              class_name: child.class_name || "",
            });
          },
        };
      }
      return {
        scroll: true,
        question: label("wizard.school.title"),
        body: phonesBody,
        nextLabel: label("wizard.phones.save"),
        busyLabel: label("common.saving"),
        onNext: saveSchool,
      };
    }

    function saveSchool() {
      if (school.status !== "ready") {
        finishPhones();
        return Promise.resolve({});
      }
      return api("GET", "api/config")
        .then((config) => {
          const next = config || {};
          next.phones = school.rows
            .map((row) => ({ label: row.label.value.trim(), number: row.number.value.trim() }))
            .filter((entry) => entry.number);
          next.holiday_region = school.select ? school.select.value : "";
          return api("POST", "api/config", next);
        })
        .then(() => {
          finishPhones();
          return {};
        })
        .catch(() => label("wizard.phones.saveError"));
    }

    function finishPhones() {
      phonesDone = true;
      if (flow) flow.destroy();
      flow = null;
      onDone();
    }

    function refresh() {
      if (!flow) return;
      if (flow.node.parentNode !== container) mount(flow.node);
      flow.render();
    }

    function ensureFlow(step) {
      if (!flow) {
        flow = window.StepFlow.create({
          text: (name, vars) => (WIZARD_TEXTS[name] ? label(WIZARD_TEXTS[name], vars) : ""),
          steps: () => stepList(wzState),
          step: stepFor,
          title: () => label("wizard.title"),
          trailing,
          hideBack: (id) => id === "url",
          onBack: (id) => {
            if (id === "url") return true;
            if (id === "phones") {
              rescueTypedPhones();
              wzState = Object.assign({}, wzState, { step: "child" });
              ensureFlow("child");
              loadChildren();
              return true;
            }
            mount(loadingCard());
            flow.destroy();
            flow = null;
            api("POST", "api/wizard/back")
              .then((next) => route(next))
              .catch(() => mount(fatalCard(label("wizard.error.action.title"), label("wizard.error.service.text"))));
            return true;
          },
        });
      }
      if (flow.node.parentNode !== container) mount(flow.node);
      if (flow.current() !== step) flow.go(step);
      else flow.render();
    }

    function rescueTypedPhones() {
      if (!school.rows || !school.rows.length) return;
      school.typed = school.rows.map((row) => ({
        label: row.label.value.trim(),
        number: row.number.value.trim(),
      }));
    }

    function loadChildren() {
      children = { status: "loading", list: [], picked: children.picked };
      refresh();
      api("GET", "api/children")
        .then((list) => {
          const items = Array.isArray(list) ? list : [];
          const keep = items.some((entry) => entry.child_id === children.picked) ? children.picked : "";
          children = { status: "ready", list: items, picked: keep || (items.length === 1 ? items[0].child_id : "") };
          refresh();
        })
        .catch(() => {
          children = { status: "error", list: [], picked: children.picked };
          refresh();
        });
    }

    function loadSchool() {
      school = Object.assign({}, school, { status: "loading" });
      refresh();
      api("GET", "api/config")
        .then(async (config) => {
          const regions = await api("GET", "api/holidays/regions")
            .then((data) => (data && data.regions) || [])
            .catch(() => []);
          const suggestion = await api("GET", "api/holidays/region-suggestion").catch(() => null);
          school = {
            status: "ready",
            phones: config && Array.isArray(config.phones) ? config.phones : [],
            regions,
            region: (config && config.holiday_region) || "",
            suggestion,
            rows: [],
            select: null,
            typed: school.typed,
          };
          refresh();
        })
        .catch(() => {
          school = Object.assign({}, school, { status: "error" });
          refresh();
        });
    }

    function route(state, ignoreBlock) {
      if (!state) {
        finishPhones();
        return;
      }
      wzState = state;
      if (state.step === "done") {
        if (phonesDone) {
          finishPhones();
          return;
        }
        ensureFlow("phones");
        if (school.status === "idle" || school.status === "error") loadSchool();
        return;
      }
      const code = state.error && state.error.code;
      if (!ignoreBlock && (code === "paused" || code === "locked")) {
        if (flow) flow.destroy();
        flow = null;
        mount(waitCard());
        return;
      }
      ensureFlow(state.step === "child" ? "child" : state.step);
      if (state.step === "child" && children.status !== "ready") loadChildren();
    }

    async function load() {
      mount(loadingCard());
      try {
        route(await api("GET", "api/wizard"));
      } catch (e) {
        mount(fatalCard(label("wizard.error.load.title"), label("wizard.error.load.text")));
      }
    }

    load();
  }

  window.renderWizard = renderWizard;
})();
