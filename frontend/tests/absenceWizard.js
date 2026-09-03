export function openWizard(window, type, data, studentId) {
  const run = window.eval(`
    (function (type, data, studentId) {
      state.absence = { data };
      startAbsenceForm(type || undefined, studentId === null ? undefined : studentId);
      return true;
    })
  `);
  run(type || "", data, studentId === undefined ? null : studentId);
  return wizard(window);
}

export function wizard(window) {
  return {
    get form() {
      return window.eval("state.absenceForm");
    },
    get step() {
      return window.eval("absenceFlow.current()");
    },
    get path() {
      return window.eval("absenceCurrentPath()");
    },
    get node() {
      return window.eval("absenceFlow.node");
    },
    get body() {
      return window.eval("absenceFlow.node.querySelector('.sw-body')");
    },
    get status() {
      return window.eval("absenceFlow.node.querySelector('.sw-status')").textContent;
    },
    get question() {
      return window.eval("absenceFlow.node.querySelector('.sw-question')").textContent;
    },
    get nextButton() {
      return window.eval("absenceFlow.node.querySelector('.sw-next')");
    },
    get dots() {
      return Array.from(window.eval("absenceFlow.node.querySelectorAll('.sw-dot')"));
    },
    go(id) {
      window.eval(`absenceFlow.go(${JSON.stringify(id)})`);
    },
    next() {
      window.eval("absenceFlow.next()");
    },
    back() {
      window.eval("absenceFlow.back()");
    },
    options() {
      return Array.from(this.body.querySelectorAll(".opt"));
    },
  };
}

export function tapNext(window) {
  wizard(window).nextButton.click();
}
