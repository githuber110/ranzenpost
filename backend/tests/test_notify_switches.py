import json
import re
from pathlib import Path

from app.scheduler import NOTIFY_EVENTS
from app.store import NOTIFY_EVENT_DEFAULTS

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "frontend" / "app.js"
I18N = ROOT / "frontend" / "i18n"
ALWAYS_SENT = {"auth"}
SWITCH = re.compile(r'\["([a-z_]+)", "(settings\.notify\.event\.[A-Za-z_]+)"\]')


def _switches():
    source = APP.read_text(encoding="utf-8")
    block = source[source.index("const NOTIFY_EVENTS = ["):]
    block = block[: block.index("];")]
    return SWITCH.findall(block)


def test_every_push_the_app_sends_can_be_switched_off_except_the_sign_in_alert():
    switched = [event for event, _label in _switches()]
    assert sorted(switched) == sorted(set(NOTIFY_EVENTS) - ALWAYS_SENT)


def test_every_default_on_event_has_a_switch():
    switched = {event for event, _label in _switches()}
    assert set(NOTIFY_EVENT_DEFAULTS) <= switched


def test_every_switch_label_exists_in_every_language():
    labels = [label for _event, label in _switches()]
    for path in sorted(I18N.glob("*.json")):
        texts = json.loads(path.read_text(encoding="utf-8"))
        assert [label for label in labels if not texts.get(label)] == [], path.name
