import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from .. import berlin
from .errors import DataError

API_ROOT = "/iserv/parentconference/api"
WIZARD_ID = "attendee-wizard"
CHILDREN_ID = "attendee-children"
WIZARD_PATH = re.compile(r"^/iserv/parentconference/attendee/appointments/conference/([0-9A-Za-z-]{1,64})/?$")
HOSTS_PARAM = "hosts[]"
HOSTS_PER_REQUEST = 40
MAX_TEXT = 2000
MAX_NAME = 200
MAX_MESSAGES = 3
SPACE = re.compile(r"\s+")


def _clean(value, limit=MAX_NAME):
    return SPACE.sub(" ", str(value if value is not None else "")).strip()[:limit]


def _plain(value):
    text = BeautifulSoup(str(value or ""), "html.parser").get_text(" ")
    return _clean(text, MAX_TEXT)


def conference_id_of(path):
    match = WIZARD_PATH.match(str(path or "").split("?", 1)[0])
    return match.group(1) if match else None


def is_booking_page(html):
    return BeautifulSoup(html or "", "html.parser").find(id=WIZARD_ID) is not None


def conference_path(conference_id):
    return "%s/conference/%s" % (API_ROOT, conference_id)


def appointments_path(conference_id):
    return "%s/conferences/%s/attendee/appointments" % (API_ROOT, conference_id)


def bookings_path(conference_id, booking_id=""):
    path = "%s/conferences/%s/bookings" % (API_ROOT, conference_id)
    return "%s/%s" % (path, booking_id) if booking_id else path


def children_of(html):
    node = BeautifulSoup(html or "", "html.parser").find(id=CHILDREN_ID)
    if node is None:
        return None
    try:
        listed = json.loads(node.get_text() or "[]")
    except ValueError:
        return None
    if not isinstance(listed, list):
        return None
    children = []
    for entry in listed:
        if isinstance(entry, dict) and _clean(entry.get("id")):
            children.append({"id": _clean(entry["id"]), "name": _clean(entry.get("display"))})
    return children


def json_of(response):
    try:
        data = json.loads(getattr(response, "text", "") or "")
    except ValueError as error:
        raise DataError("the conference answer is not JSON") from error
    if not isinstance(data, dict):
        raise DataError("the conference answer has an unknown shape")
    return data


def moment_of(text):
    try:
        moment = datetime.fromisoformat(str(text or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment
    return berlin.local_from_utc(moment.astimezone(timezone.utc).replace(tzinfo=None))


def _host(entry):
    return {
        "id": _clean(entry.get("id")),
        "user": _clean(entry.get("userId")),
        "name": _clean(entry.get("userName")),
        "short": _clean(entry.get("abbreviation")),
        "location": _clean(entry.get("location")),
    }


def _slot(entry):
    begin = moment_of(entry.get("begin"))
    end = moment_of(entry.get("end"))
    if begin is None or end is None or not _clean(entry.get("id")):
        return None
    return {"id": _clean(entry["id"]), "begin": begin, "end": end, "blocked": entry.get("blocked") is True}


def read_conference(data):
    hosts = data.get("hosts")
    slots = data.get("timeslots")
    if not isinstance(hosts, list) or not isinstance(slots, list):
        raise DataError("the conference answer lacks hosts or time slots")
    read_hosts = [host for host in (_host(entry) for entry in hosts if isinstance(entry, dict)) if host["id"]]
    read_slots = [slot for slot in (_slot(entry) for entry in slots if isinstance(entry, dict)) if slot is not None]
    if (hosts and not read_hosts) or (slots and not read_slots):
        raise DataError("the conference answer has unreadable hosts or time slots")
    begin = moment_of(data.get("bookingBegin"))
    end = moment_of(data.get("bookingEnd"))
    return {
        "title": _plain(data.get("title")),
        "description": _plain(data.get("description")),
        "booking_begin": begin.date() if begin else None,
        "booking_end": end.date() if end else None,
        "hosts": read_hosts,
        "slots": read_slots,
    }


def read_appointments(data):
    listed = data.get("appointments")
    if not isinstance(listed, list):
        raise DataError("the conference answer lacks appointments")
    appointments = []
    for entry in listed:
        if not isinstance(entry, dict):
            continue
        host = entry.get("host") if isinstance(entry.get("host"), dict) else {}
        children = entry.get("children") if isinstance(entry.get("children"), list) else []
        appointments.append({
            "id": _clean(entry.get("id")),
            "editable": entry.get("editable") is True,
            "slot": _clean(entry.get("timeslotId")),
            "host": _clean(entry.get("hostId")),
            "user": _clean(host.get("id")),
            "name": _clean(host.get("name")),
            "children": [_clean(child.get("id")) for child in children if isinstance(child, dict) and _clean(child.get("id"))],
        })
    return appointments


def school_messages(text):
    try:
        data = json.loads(text or "")
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    listed = data.get("messages") if isinstance(data.get("messages"), list) else [data.get("message")]
    return [_plain(message) for message in listed if isinstance(message, str) and _plain(message)][:MAX_MESSAGES]


def booking_cells(entry):
    moment = entry.get("moment")
    cells = []
    if moment is not None:
        cells.append(moment.strftime("%d.%m.%Y"))
    if entry.get("begin"):
        cells.append("%s - %s" % (entry["begin"], entry["end"]))
    if entry.get("teacher"):
        cells.append(entry["teacher"])
    return cells
