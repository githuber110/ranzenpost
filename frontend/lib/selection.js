export const SELECTION_AREAS = Object.freeze({
  letters: Object.freeze({ mode: "lettersSelectMode", selected: "lettersSelected" }),
  pinboard: Object.freeze({ mode: "pinboardSelectMode", selected: "pinboardSelected" }),
});

export const SELECTION_KEYS = Object.freeze(
  Object.values(SELECTION_AREAS).flatMap((area) => [area.mode, area.selected])
);

export const ENTER_PULSE_MS = 12;

const emptyArea = ({ mode, selected }) => ({ [mode]: false, [selected]: [] });

export function createSelection({ slot, rerender, vibrate, progress, t, tCount, formatNumber, dom }) {
  const barLabel = (count) => {
    const current = progress();
    if (!current) return tCount("common.selected", count);
    return t("common.bulkProgress", {
      done: formatNumber(current.done),
      total: formatNumber(current.total),
    });
  };

  const barNode = (count, onCancel, actions) => {
    const busy = !!progress();
    return dom.el("div", { class: "select-bar", "aria-busy": busy ? "true" : "false" }, [
      dom.el("div", { class: "select-bar-info" }, [
        dom.el("button", {
          class: "select-bar-cancel",
          type: "button",
          disabled: busy ? "disabled" : null,
          "aria-label": t("common.selection.end"),
          onclick: onCancel,
        }, [dom.icon("close", 16)]),
        dom.el("span", { role: busy ? "status" : null }, barLabel(count)),
      ]),
      dom.el("div", { class: "select-bar-actions" }, actions),
    ]);
  };

  const area = (keys) => {
    const { mode, selected } = keys;

    const reset = () => {
      slot.patch(emptyArea(keys));
    };

    const exit = () => {
      reset();
      rerender();
    };

    const toggleMode = () => {
      slot.patch({ [mode]: !slot.read(mode), [selected]: [] });
      rerender();
    };

    const enter = (key) => {
      if (slot.read(mode)) return;
      slot.patch({ [mode]: true, [selected]: [key] });
      vibrate(ENTER_PULSE_MS);
      rerender();
    };

    const toggleItem = (key) => {
      const current = slot.read(selected);
      const idx = current.indexOf(key);
      slot.patch({ [selected]: idx === -1 ? [...current, key] : current.filter((_, index) => index !== idx) });
      rerender();
    };

    const keepVisible = (visibleKeys) => {
      const current = slot.read(selected);
      if (!current || !current.length) return;
      const allowed = new Set(visibleKeys);
      const kept = current.filter((key) => allowed.has(key));
      if (kept.length !== current.length) slot.patch({ [selected]: kept });
    };

    const bar = (actions) => {
      const count = slot.read(selected).length;
      const disabled = count === 0 ? "disabled" : null;
      const buttons = actions.map((action) =>
        dom.el("button", { class: "btn slim ghost", type: "button", disabled, onclick: action.run }, [
          dom.icon(action.icon, 16),
          action.label,
        ])
      );
      return barNode(count, exit, buttons);
    };

    return Object.freeze({ toggleMode, enter, exit, reset, toggleItem, keepVisible, bar });
  };

  const letters = area(SELECTION_AREAS.letters);
  const pinboard = area(SELECTION_AREAS.pinboard);

  const resetAll = () => {
    slot.patch(Object.assign({}, ...Object.values(SELECTION_AREAS).map(emptyArea)));
  };

  return Object.freeze({ letters, pinboard, resetAll });
}

export function selectionGlobals() {
  return Object.freeze({ createSelection });
}
