import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
APP_JS = FRONTEND / "app.js"

SEND_ENDPOINT = "api/messenger/send"
SEND_FUNCTION = "sendMessengerMessage"
TOP_LEVEL_FUNCTION = re.compile(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", re.M)
BACKGROUND_FUNCTIONS = (
    "pollMessengerRoom",
    "startMessengerPoll",
    "loadMessengerRooms",
    "loadMessengerHistory",
    "refreshActiveView",
    "loadRest",
    "setupVisibilityRefresh",
    "boot",
    "bootOnce",
)


def source():
    return APP_JS.read_text(encoding="utf-8")


def function_spans(text):
    starts = [(match.start(), match.group(1)) for match in TOP_LEVEL_FUNCTION.finditer(text)]
    spans = {}
    for index, (start, name) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        spans.setdefault(name, []).append(text[start:end])
    return spans


def functions_mentioning(text, needle):
    return {name for name, bodies in function_spans(text).items() if any(needle in body for body in bodies)}


def test_the_frontend_calls_the_send_endpoint_from_exactly_one_place():
    text = source()
    assert text.count(SEND_ENDPOINT) == 1
    assert functions_mentioning(text, SEND_ENDPOINT) == {SEND_FUNCTION}


def test_the_send_function_is_reached_only_from_the_composer_click_handler():
    text = source()
    callers = functions_mentioning(text, SEND_FUNCTION + "(")
    assert callers == {SEND_FUNCTION, "messengerComposer"}
    composer = function_spans(text)["messengerComposer"][0]
    wiring = [line.strip() for line in composer.split("\n") if SEND_FUNCTION + "(" in line]
    assert len(wiring) == 1
    assert wiring[0].startswith('button.addEventListener("click"')


def test_no_timer_or_refresh_path_can_reach_the_send_function():
    spans = function_spans(source())
    offenders = []
    for name in BACKGROUND_FUNCTIONS:
        for body in spans.get(name, []):
            if SEND_FUNCTION in body or SEND_ENDPOINT in body:
                offenders.append(name)
    assert offenders == []


def test_the_scanner_would_notice_a_second_send_call_site():
    planted = (
        'function pollMessengerRoom() {\n'
        '  sendMessengerMessage(input);\n'
        "}\n"
        'function messengerComposer() {\n'
        '  button.addEventListener("click", () => sendMessengerMessage(input));\n'
        "}"
    )
    assert functions_mentioning(planted, SEND_FUNCTION + "(") == {
        "pollMessengerRoom",
        "messengerComposer",
    }


def test_the_client_never_names_a_read_marker_or_receipt_route():
    text = source()
    for forbidden in ("read_markers", "/receipt/", "m.fully_read"):
        assert forbidden not in text
