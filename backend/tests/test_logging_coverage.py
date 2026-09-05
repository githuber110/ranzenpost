import re
from pathlib import Path

BACKEND_APP = Path(__file__).resolve().parents[1] / "app"

FOREIGN_CALL = re.compile(r"\b(?:requests|session|self\.session|client|probe)\.(?:get|post|put|delete|request)\s*\(")
IMPORTS_REQUESTS = re.compile(r"^\s*import requests\s*$", re.MULTILINE)
GETS_LOGGER = re.compile(r"logging\.getLogger\(")
WARNS_WITH_TRACE = re.compile(r"logger\.warning\([^)]*exc_info=True", re.DOTALL)

LOGGING_DEBT = {
    "hanotify.py": "reaches Home Assistant, silent today - next wave",
    "haservices.py": "reaches Home Assistant, silent today - next wave",
    "holidays.py": "reaches the public holiday feeds, silent today - next wave",
    "client.py": "the auth core needs its own review before log lines are added",
    "dsa.py": "part of the auth core, same review gate as client.py",
    "iserv_prober.py": "part of the auth core, same review gate as client.py",
    "schoolregion.py": "reaches the school domain, silent today - next wave",
    "server.py": "route shell, the modules behind it carry the logging",
}


def modules_reaching_a_foreign_system():
    found = []
    for path in sorted(BACKEND_APP.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if not IMPORTS_REQUESTS.search(source) and not FOREIGN_CALL.search(source):
            continue
        found.append((path, source))
    return found


def test_every_module_that_reaches_a_foreign_system_can_be_watched_in_the_log():
    silent = []
    for path, source in modules_reaching_a_foreign_system():
        if GETS_LOGGER.search(source):
            continue
        if path.name in LOGGING_DEBT:
            continue
        silent.append(path.name)
    assert silent == [], (
        "a module that talks to a foreign system without a logger fails silently - "
        "the add-on log then says 'no errors have been reported' while the user sees a red card: "
        f"{silent}"
    )


def test_the_logging_debt_list_holds_no_entry_that_is_already_paid():
    reaching = {path.name: source for path, source in modules_reaching_a_foreign_system()}
    stale = []
    for name, reason in LOGGING_DEBT.items():
        assert reason.strip(), f"{name} needs a reason, not an empty string"
        if name not in reaching:
            stale.append(f"{name} no longer reaches a foreign system")
        elif GETS_LOGGER.search(reaching[name]):
            stale.append(f"{name} logs now")
    assert stale == [], f"delete these entries from LOGGING_DEBT: {stale}"


def test_the_messenger_reports_its_failures_with_a_stack_trace():
    for name in ("messenger.py", "messenger_routes.py", "iserv/messenger.py"):
        source = (BACKEND_APP / name).read_text(encoding="utf-8")
        assert GETS_LOGGER.search(source), f"{name} has no logger"
    service = (BACKEND_APP / "messenger.py").read_text(encoding="utf-8")
    routes = (BACKEND_APP / "messenger_routes.py").read_text(encoding="utf-8")
    assert WARNS_WITH_TRACE.search(service), "messenger.py logs no traceback"
    assert WARNS_WITH_TRACE.search(routes), "messenger_routes.py logs no traceback"


def test_the_guard_still_catches_a_module_that_was_stripped_of_its_logger():
    planted = "import requests\n\n\ndef go():\n    return requests.get('https://example.invalid')\n"
    assert IMPORTS_REQUESTS.search(planted)
    assert not GETS_LOGGER.search(planted)
    quiet = "def add(a, b):\n    return a + b\n"
    assert not IMPORTS_REQUESTS.search(quiet)
    assert not FOREIGN_CALL.search(quiet)
