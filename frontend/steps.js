(function () {
  const COMPACT_DROP = 120;

  const make = (tag, attrs, children) => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "html") node.innerHTML = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    }
    for (const child of [].concat(children === undefined || children === null ? [] : children)) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child.nodeType ? child : document.createTextNode(child));
    }
    return node;
  };

  const BACK_SHAPE = '<path d="M14.6 5.4 8 12l6.6 6.6"/>';
  const GOAL_SHAPE = '<path d="m21.2 3.1-18 7 6.5 2.6z"/><path d="m21.2 3.1-8.4 17.8-3.1-8.2z"/>';

  function shapeSvg(shape, size) {
    return (
      '<svg class="ico" viewBox="0 0 24 24" stroke="currentColor" fill="none" aria-hidden="true"' +
      ' style="width:' + size + 'px;height:' + size + 'px">' + shape + "</svg>"
    );
  }

  function textOf(spec, name, vars) {
    const value = spec.text ? spec.text(name, vars) : "";
    return value === undefined || value === null ? "" : String(value);
  }

  function create(spec) {
    const flow = {};
    const root = make("div", { class: "sw" });
    const head = make("div", { class: "sw-head" });
    const titleNode = make("h1", { class: "sw-title" });
    const progress = make("div", { class: "sw-progress" });
    const dots = make("div", { class: "sw-dots", "aria-hidden": "true" });
    const content = make("section", { class: "sw-content", role: "group", "aria-labelledby": "sw-question" });
    const question = make("h2", { class: "sw-question", id: "sw-question", tabindex: "-1" });
    const body = make("div", { class: "sw-body" });
    const foot = make("div", { class: "sw-foot" });
    const status = make("p", { class: "sw-status", "aria-live": "polite" });
    const live = make("div", { class: "sw-live", "aria-live": "polite", role: "status" });
    const nextButton = make("button", { class: "btn sw-next", type: "button" });

    let cursor = "";
    let busy = false;
    let pinned = false;
    let statusText = "";
    let statusKind = "";
    let returnTo = "";
    let baseHeight = 0;
    let compact = false;
    let destroyed = false;

    const backButton = make("button", {
      class: "icon-btn sw-back",
      type: "button",
      html: shapeSvg(BACK_SHAPE, 18),
      onclick: () => flow.back(),
    });
    const goal = make("span", { class: "sw-goal", role: "img", html: shapeSvg(GOAL_SHAPE, 16) });

    head.append(backButton, titleNode, make("div", { class: "sw-head-actions" }));
    progress.append(make("span", { class: "sw-lead" }), dots, goal);
    content.append(question, body);
    foot.append(status, nextButton);
    root.append(head, progress, content, foot, live);

    function path() {
      const list = spec.steps() || [];
      return list.filter((id) => typeof id === "string" && id);
    }

    function detour(id) {
      return !!(spec.detour && spec.detour(id));
    }

    function resolve() {
      const list = path();
      if (!list.length) return "";
      if (detour(cursor)) return cursor;
      if (list.includes(cursor)) return cursor;
      return list[0];
    }

    function setStatus(text, kind) {
      statusText = text || "";
      statusKind = kind || "";
      status.setAttribute("aria-live", statusKind === "block" ? "assertive" : "polite");
      status.className = statusKind ? "sw-status " + statusKind : "sw-status";
      status.textContent = statusText;
    }

    function announce(text) {
      if (!text) return;
      live.textContent = "";
      window.setTimeout(() => {
        if (!destroyed) live.textContent = text;
      }, 30);
    }

    function dotFor(index, current, list) {
      if (index < current) {
        return make("button", {
          class: "sw-dot done",
          type: "button",
          tabindex: "-1",
          onclick: () => flow.go(list[index]),
        });
      }
      if (index === current) return make("span", { class: "sw-dot on" });
      return make("span", { class: "sw-dot", "aria-disabled": "true" });
    }

    function paintProgress(list, index, step) {
      dots.replaceChildren();
      const lead = progress.querySelector(".sw-lead");
      lead.replaceChildren();
      const leadNode = spec.lead ? spec.lead() : null;
      if (leadNode) lead.append(leadNode);
      if (detour(cursor)) {
        progress.classList.add("detour");
        progress.removeAttribute("role");
        progress.removeAttribute("aria-valuenow");
        progress.removeAttribute("aria-valuetext");
        goal.removeAttribute("aria-label");
        return;
      }
      progress.classList.remove("detour");
      list.forEach((unused, position) => dots.append(dotFor(position, index, list)));
      const pending = !!(spec.pending && spec.pending(cursor));
      if (pending) dots.append(make("span", { class: "sw-dot maybe", "aria-disabled": "true" }));
      progress.setAttribute("role", "progressbar");
      progress.setAttribute("aria-valuemin", "1");
      progress.setAttribute("aria-valuenow", String(index + 1));
      if (!pending) progress.setAttribute("aria-valuemax", String(list.length));
      else progress.removeAttribute("aria-valuemax");
      const number = index + 1;
      const spoken = pending
        ? textOf(spec, "progress", { n: number }) + " " + textOf(spec, "pending")
        : textOf(spec, "progressTotal", { n: number, total: list.length });
      progress.setAttribute("aria-valuetext", spoken);
      goal.setAttribute("aria-label", textOf(spec, "goal"));
      if (step && step.question) content.setAttribute("aria-labelledby", "sw-question");
    }

    function paintFoot(step) {
      const blocked = !!(step.block && !busy);
      nextButton.className = step.danger ? "btn sw-next danger" : "btn sw-next";
      nextButton.setAttribute("aria-disabled", blocked ? "true" : "false");
      nextButton.setAttribute("aria-busy", busy ? "true" : "false");
      nextButton.replaceChildren();
      if (busy) {
        nextButton.append(make("span", { class: "spin" }));
        nextButton.append(document.createTextNode(step.busyLabel || step.nextLabel || ""));
      } else {
        nextButton.append(document.createTextNode(step.nextLabel || ""));
      }
      if (pinned) return;
      if (step.block) {
        setStatus(step.block, "block");
        return;
      }
      if (statusKind === "error") return;
      setStatus(step.hint || "", "");
    }

    function paintHead() {
      titleNode.textContent = spec.title ? spec.title() : "";
      const actions = head.querySelector(".sw-head-actions");
      actions.replaceChildren();
      const trailing = spec.trailing ? spec.trailing() : null;
      for (const node of [].concat(trailing || [])) if (node) actions.append(node);
      backButton.setAttribute("aria-label", textOf(spec, "back"));
      backButton.style.visibility = spec.hideBack && spec.hideBack(cursor) ? "hidden" : "visible";
    }

    function focusStep() {
      window.setTimeout(() => {
        if (!destroyed) question.focus();
      }, 0);
    }

    function unwrap(value) {
      return typeof value === "function" ? value() : value;
    }

    function view(step) {
      return Object.assign({}, step, {
        block: unwrap(step.block) || "",
        hint: unwrap(step.hint) || "",
        nextLabel: unwrap(step.nextLabel) || "",
        busyLabel: unwrap(step.busyLabel) || "",
      });
    }

    function paint(options) {
      const list = path();
      cursor = resolve();
      const step = spec.step(cursor) || {};
      const index = list.indexOf(cursor);
      root.setAttribute("data-step", cursor);
      paintHead();
      paintProgress(list, index < 0 ? 0 : index, step);
      question.textContent = step.question || "";
      if (!options || options.body !== false) {
        body.replaceChildren();
        for (const node of [].concat(unwrap(step.body) || [])) if (node) body.append(node);
      }
      content.classList.toggle("list", !!step.list);
      content.classList.toggle("scroll", !!step.scroll);
      const shown = view(step);
      paintFoot(shown);
      fit();
      return shown;
    }

    function fit() {
      root.classList.remove("tight");
      if (content.scrollHeight > content.clientHeight + 1) root.classList.add("tight");
    }

    flow.node = root;

    flow.current = () => cursor;

    flow.path = path;

    flow.render = () => {
      pinned = false;
      return paint();
    };

    flow.sync = () => {
      pinned = false;
      return paint({ body: false });
    };

    flow.status = (text, kind) => setStatus(text, kind);

    flow.announce = announce;

    flow.returnTo = (id) => {
      if (id !== undefined) returnTo = id;
      return returnTo;
    };

    function resolveTarget(id) {
      if (!spec.redirect) return { step: id, status: "" };
      const out = spec.redirect(id);
      if (!out) return { step: id, status: "" };
      if (typeof out === "string") return { step: out, status: "" };
      return { step: out.step || id, status: out.status || "" };
    }

    flow.go = (id) => {
      if (!id) return;
      const dest = resolveTarget(id);
      cursor = dest.step;
      busy = false;
      pinned = !!dest.status;
      setStatus(dest.status, dest.status ? "block" : "");
      const step = paint();
      if (pinned && step.blockFocus) {
        const field = step.blockFocus();
        if (field) {
          field.classList.add("bad");
          window.setTimeout(() => {
            if (!destroyed) field.focus();
          }, 0);
          return;
        }
      }
      focusStep();
    };

    flow.back = () => {
      if (busy) return;
      if (spec.onBack && spec.onBack(cursor) === true) return;
      if (detour(cursor)) {
        flow.go(returnTo || path()[path().length - 1]);
        return;
      }
      const list = path();
      const index = list.indexOf(cursor);
      if (index <= 0) {
        if (spec.onExit) spec.onExit();
        return;
      }
      flow.go(list[index - 1]);
    };

    flow.next = () => {
      if (busy) return;
      pinned = false;
      const step = view(spec.step(cursor) || {});
      if (step.block) {
        setStatus(step.block, "block");
        paint({ body: false });
        const target = step.blockFocus ? step.blockFocus() : null;
        if (target && target.focus) target.focus();
        return;
      }
      const advance = () => {
        if (step.nextTarget) {
          flow.go(step.nextTarget);
          return;
        }
        const list = path();
        const index = list.indexOf(cursor);
        if (index < 0 || index >= list.length - 1) return;
        flow.go(list[index + 1]);
      };
      if (!step.onNext) {
        advance();
        return;
      }
      const outcome = step.onNext();
      if (!outcome || typeof outcome.then !== "function") {
        if (outcome === false) return;
        advance();
        return;
      }
      busy = true;
      setStatus("", "");
      paint({ body: false });
      outcome.then(
        (result) => {
          busy = false;
          if (result === false || typeof result === "string") {
            setStatus(typeof result === "string" ? result : textOf(spec, "failed"), "error");
            paint({ body: false });
            return;
          }
          if (result && typeof result === "object") {
            if (result.step) flow.go(result.step);
            else paint({ body: false });
            return;
          }
          advance();
        },
        () => {
          busy = false;
          setStatus(textOf(spec, "failed"), "error");
          paint({ body: false });
        }
      );
    };

    nextButton.addEventListener("click", () => flow.next());

    root.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        flow.back();
      }
    });

    function applyViewport() {
      const view = window.visualViewport;
      if (!view) return;
      if (!baseHeight) baseHeight = window.innerHeight || view.height;
      const shrunk = baseHeight - view.height > COMPACT_DROP;
      root.style.setProperty("--sw-vh", Math.round(view.height) + "px");
      if (shrunk === compact) return;
      compact = shrunk;
      root.classList.toggle("compact", compact);
    }

    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", applyViewport);
      applyViewport();
    }

    flow.destroy = () => {
      destroyed = true;
      if (window.visualViewport) window.visualViewport.removeEventListener("resize", applyViewport);
    };

    flow.start = (id) => {
      cursor = id || "";
      const step = paint();
      focusStep();
      return step;
    };

    return flow;
  }

  window.StepFlow = { create };
})();
