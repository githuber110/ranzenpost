import { apiGlobals } from "./api.js";
import { domGlobals } from "./dom.js";
import { formatGlobals } from "./format.js";
import { i18nGlobals } from "./i18nGlobals.js";
import { shellGlobals } from "./shell.js";
import { storeGlobals } from "./store.js";

window.RanzenpostI18n = i18nGlobals();
window.RanzenpostApi = apiGlobals();
window.RanzenpostFormat = formatGlobals();
window.RanzenpostDom = domGlobals();
window.RanzenpostShell = shellGlobals();
window.RanzenpostStore = storeGlobals();
