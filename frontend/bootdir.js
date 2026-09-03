(function () {
  var LANGUAGES = ["de", "en", "ar", "tr", "ru", "uk"];
  var RTL_LANGUAGES = ["ar"];
  var PENDING_KEY = "languagePending";

  function storedChoice() {
    try {
      return window.localStorage.getItem(PENDING_KEY) || "";
    } catch (error) {
      return "";
    }
  }

  function normalize(value) {
    var tag = String(value || "").toLowerCase().split("-")[0];
    return LANGUAGES.indexOf(tag) === -1 ? "" : tag;
  }

  function preferred() {
    var list = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language];
    for (var index = 0; index < list.length; index += 1) {
      var tag = normalize(list[index]);
      if (tag) return tag;
    }
    return LANGUAGES[0];
  }

  var language = normalize(storedChoice()) || preferred();
  document.documentElement.setAttribute("lang", language);
  document.documentElement.setAttribute("dir", RTL_LANGUAGES.indexOf(language) === -1 ? "ltr" : "rtl");
})();
