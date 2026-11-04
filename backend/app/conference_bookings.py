import logging
from urllib.parse import urljoin

from requests import RequestException

from . import berlin, messages
from .conference_outcomes import (
    REQUEST_ID,
    STATE_DONE,
    STATE_INVALID,
    STATE_PENDING,
    STATE_REFUSED,
    STATE_UNCERTAIN,
    SUBMIT_INVALID_REQUEST_KEY,
    SUBMIT_NO_PROFILE_KEY,
    SUBMIT_REJECTED_KEY,
    SUBMIT_SIGNED_OUT_KEY,
    SUBMIT_STALE_KEY,
    SUBMIT_UNCERTAIN_KEY,
    SUBMIT_UNCONFIRMED_KEY,
)
from .failure import failure_cause
from .iserv.conference_booking import (
    HOSTS_PARAM,
    HOSTS_PER_REQUEST,
    appointments_path,
    booking_cells,
    bookings_path,
    children_of,
    conference_id_of,
    conference_path,
    is_booking_page,
    json_of,
    read_appointments,
    read_conference,
    school_messages,
)
from .iserv.dsa import names_one_child
from .iserv.forms import browser_headers, find_login_form, parse_forms
from .iserv.pages import path_of, status_of

logger = logging.getLogger(__name__)

ACTION_BOOK = "book"
ACTION_CHANGE = "change"
ACTION_CANCEL = "cancel"
ACTIONS = (ACTION_BOOK, ACTION_CHANGE, ACTION_CANCEL)
WINDOW_OPEN = "open"
WINDOW_BEFORE = "before"
WINDOW_AFTER = "after"
WINDOW_UNKNOWN = "unknown"
DONE_KEYS = {
    ACTION_BOOK: "api.conferences.booking.booked",
    ACTION_CHANGE: "api.conferences.booking.changed",
    ACTION_CANCEL: "api.conferences.booking.cancelled",
}
TAKEN_KEY = "api.conferences.booking.taken"
GONE_KEY = "api.conferences.booking.gone"
CLOSED_KEY = "api.conferences.booking.closed"
CHILD_KEY = "api.conferences.booking.child"
REFUSED_KEY = "api.conferences.booking.refused"


def _text(value):
    return value if isinstance(value, str) else ""


class ConferenceBookings:
    def __init__(self, conferences):
        self.conferences = conferences

    def _now(self):
        return berlin.local_from_epoch(self.conferences.clock())

    def _authorised(self, listed):
        if listed is None:
            return [], 0
        known = self.conferences._known_profiles()
        kept = []
        for child in listed:
            if names_one_child(child["name"], known):
                kept.append(child)
        withheld = len(listed) - len(kept)
        if withheld:
            logger.info("conference booking: %d children withheld, they match no known profile of this account", withheld)
        return kept, withheld

    @staticmethod
    def _appointments(client, conference_id, hosts):
        found = []
        ids = [host["id"] for host in hosts]
        for start in range(0, len(ids), HOSTS_PER_REQUEST):
            params = [(HOSTS_PARAM, value) for value in ids[start:start + HOSTS_PER_REQUEST]]
            found.extend(read_appointments(json_of(client.fetch_or_raise(appointments_path(conference_id), params))))
        return found

    @staticmethod
    def _host_of(appointment, hosts):
        for host in hosts:
            if appointment["host"] and appointment["host"] == host["id"]:
                return host
        for host in hosts:
            if appointment["user"] and appointment["user"] == host["user"]:
                return host
        return None

    def _read(self, client, conference_id, html):
        conference = read_conference(json_of(client.fetch_or_raise(conference_path(conference_id))))
        children, withheld = self._authorised(children_of(html))
        appointments = self._appointments(client, conference_id, conference["hosts"])
        allowed = {child["id"] for child in children}
        names = {child["id"]: child["name"] for child in children}
        slots = {slot["id"]: slot for slot in conference["slots"]}
        mine = []
        taken = []
        for appointment in appointments:
            host = self._host_of(appointment, conference["hosts"])
            taken.append({"slot": appointment["slot"], "host": host["id"] if host is not None else appointment["host"]})
            if not appointment["editable"] and not allowed & set(appointment["children"]):
                continue
            slot = slots.get(appointment["slot"])
            own = appointment["children"]
            mine.append({
                "id": appointment["id"],
                "slot": appointment["slot"],
                "host": host["id"] if host is not None else appointment["host"],
                "teacher": host["name"] if host is not None else appointment["name"],
                "location": host["location"] if host is not None else "",
                "moment": slot["begin"] if slot else None,
                "begin": slot["begin"].strftime("%H:%M") if slot else "",
                "end": slot["end"].strftime("%H:%M") if slot else "",
                "children": [{"id": child, "name": names[child]} for child in own if child in allowed],
                "child_ids": sorted(own),
                "editable": (
                    appointment["editable"] and bool(own) and set(own) <= allowed
                    and slot is not None and not self._slot_closed(slot)
                ),
            })
        return {
            "conference_id": conference_id,
            "conference": conference,
            "children": children,
            "withheld": withheld,
            "mine": mine,
            "taken": taken,
            "ids": {appointment["id"] for appointment in appointments if appointment["id"]},
            "window": self._window(conference),
        }

    def _window(self, conference):
        today = self._now().date()
        if conference["booking_begin"] is not None and today < conference["booking_begin"]:
            return WINDOW_BEFORE
        if conference["booking_end"] is not None and today > conference["booking_end"]:
            return WINDOW_AFTER
        if conference["booking_begin"] is None or conference["booking_end"] is None:
            return WINDOW_UNKNOWN
        return WINDOW_OPEN

    def _slot_closed(self, slot):
        return slot["blocked"] or slot["begin"] < self._now()

    def _public(self, path, state):
        conference = state["conference"]
        days = {}
        for slot in sorted(conference["slots"], key=lambda item: item["begin"]):
            days.setdefault(slot["begin"].date().isoformat(), []).append({
                "id": slot["id"],
                "begin": slot["begin"].strftime("%H:%M"),
                "end": slot["end"].strftime("%H:%M"),
                "closed": self._slot_closed(slot),
            })
        hosts = sorted(conference["hosts"], key=lambda host: host["name"].casefold())
        return {
            "page": self.conferences.token(path),
            "title": conference["title"],
            "blocks": [],
            "forms": [],
            "notices": [],
            "booking": {
                "description": conference["description"],
                "window": {
                    "state": state["window"],
                    "begin": conference["booking_begin"].isoformat() if conference["booking_begin"] else "",
                    "end": conference["booking_end"].isoformat() if conference["booking_end"] else "",
                },
                "hosts": [{"id": host["id"], "name": host["name"], "short": host["short"], "location": host["location"]} for host in hosts],
                "days": [{"date": day, "slots": slots} for day, slots in days.items()],
                "taken": state["taken"],
                "mine": [self._public_booking(entry) for entry in state["mine"]],
                "children": state["children"],
                "withheld": state["withheld"],
                "profiles_missing": not state["children"],
            },
        }

    @staticmethod
    def _public_booking(entry):
        public = {key: value for key, value in entry.items() if key not in ("moment", "child_ids")}
        public["date"] = entry["moment"].date().isoformat() if entry["moment"] is not None else ""
        return public

    def page(self, client, path, response):
        conference_id = conference_id_of(path)
        return self._public(path, self._read(client, conference_id, response.text))

    def submit(self, token, action, values, request_id, confirmed):
        path = self.conferences._path(token)
        conference_id = conference_id_of(path)
        if action not in ACTIONS or conference_id is None:
            return messages.result(False, SUBMIT_INVALID_REQUEST_KEY, state=STATE_REFUSED)
        if confirmed is not True:
            return messages.result(False, SUBMIT_UNCONFIRMED_KEY, state=STATE_REFUSED)
        if not REQUEST_ID.match(request_id):
            return messages.result(False, SUBMIT_INVALID_REQUEST_KEY, state=STATE_REFUSED)
        return self.conferences._exclusive(token, lambda: self._read_and_send(path, token, conference_id, action, values, request_id))

    def _read_and_send(self, path, token, conference_id, action, values, request_id):
        client = self.conferences.connection._session()
        response = client.fetch_or_raise(path)
        if not is_booking_page(response.text):
            logger.info("conference booking refused before sending: the school page is no longer a booking page")
            return messages.result(False, SUBMIT_STALE_KEY, state=STATE_REFUSED)
        state = self._read(client, conference_id, response.text)
        checked = self._checked(action, values, state)
        if isinstance(checked, str):
            logger.info("conference booking refused before sending: %s", checked)
            return messages.result(False, checked, state=STATE_REFUSED, page=self._public(path, state))
        return self._send(client, path, token, request_id, action, checked, state, response.url)

    def _checked_children(self, values, state):
        allowed = {child["id"] for child in state["children"]}
        given = values.get("children")
        chosen = [_text(value) for value in given] if isinstance(given, list) else []
        if not chosen or any(value not in allowed for value in chosen):
            return None
        return sorted(set(chosen))

    def _checked(self, action, values, state):
        if action == ACTION_BOOK:
            return self._checked_book(values, state)
        booking = next((entry for entry in state["mine"] if entry["id"] and entry["id"] == _text(values.get("booking"))), None)
        if booking is None or not booking["editable"]:
            return GONE_KEY
        if action == ACTION_CANCEL:
            return {"booking": booking, "method": "DELETE", "payload": None}
        children = self._checked_children(values, state)
        if children is None:
            return CHILD_KEY
        return {
            "booking": booking,
            "method": "PUT",
            "payload": {"id": booking["id"], "timeslotId": booking["slot"], "hostId": booking["host"], "childrenIds": children},
            "children": children,
            "before": booking["child_ids"],
        }

    def _checked_book(self, values, state):
        if state["window"] in (WINDOW_BEFORE, WINDOW_AFTER):
            return CLOSED_KEY
        conference = state["conference"]
        slot_id = _text(values.get("slot"))
        host_id = _text(values.get("host"))
        slot = next((entry for entry in conference["slots"] if entry["id"] == slot_id), None)
        host = next((entry for entry in conference["hosts"] if entry["id"] == host_id), None)
        if slot is None or host is None or self._slot_closed(slot) or {"slot": slot_id, "host": host_id} in state["taken"]:
            return TAKEN_KEY
        if not state["children"]:
            return SUBMIT_NO_PROFILE_KEY
        children = self._checked_children(values, state)
        if children is None:
            return CHILD_KEY
        return {
            "booking": {
                "id": "",
                "slot": slot_id,
                "host": host_id,
                "teacher": host["name"],
                "moment": slot["begin"],
                "begin": slot["begin"].strftime("%H:%M"),
                "end": slot["end"].strftime("%H:%M"),
            },
            "method": "POST",
            "payload": {"timeslotId": slot_id, "hostId": host_id, "childrenIds": children},
            "children": children,
        }

    def _fresh(self, client, path, conference_id):
        try:
            response = client.fetch_or_raise(path)
            return self._read(client, conference_id, response.text)
        except Exception as error:
            logger.warning("conference booking could not be read again: %s", failure_cause(error))
            return None

    @staticmethod
    def _arrived(action, checked, state, accepted):
        booking = checked["booking"]
        if action == ACTION_BOOK:
            return any(entry["slot"] == booking["slot"] and entry["host"] == booking["host"] for entry in state["mine"])
        if action == ACTION_CANCEL:
            return booking["id"] not in state["ids"]
        current = next((entry for entry in state["mine"] if entry["id"] == booking["id"]), None)
        if current is None or current["child_ids"] != checked["children"]:
            return False
        return accepted or checked["before"] != checked["children"]

    def _send(self, client, path, token, request_id, action, checked, state, page_url):
        conference_id = state["conference_id"]
        booking_id = checked["booking"]["id"]
        target = urljoin(page_url, bookings_path(conference_id, booking_id))
        self.conferences._record(request_id, token, STATE_PENDING)
        self.conferences._note_own_change({"row": booking_cells(checked["booking"])})
        try:
            return self._sent_answer(client, path, token, request_id, action, checked, conference_id, target, page_url)
        except Exception:
            self.conferences._record(request_id, token, STATE_UNCERTAIN)
            raise

    def _sent_answer(self, client, path, token, request_id, action, checked, conference_id, target, page_url):
        try:
            sent = client.send_json(checked["method"], target, checked["payload"], browser_headers(page_url))
        except RequestException as error:
            logger.warning("conference booking outcome unknown: the request to the school failed: %s", failure_cause(error))
            return self._settled(client, path, token, request_id, action, checked, {"post_status": 0, "post_redirects": 0}, SUBMIT_UNCERTAIN_KEY, False)
        status = status_of(sent)
        history = getattr(sent, "history", None) or []
        text = getattr(sent, "text", "") or ""
        url = str(getattr(sent, "url", "") or target)
        diagnosis = {"post_status": status, "post_path": path_of(url), "post_redirects": len(history)}
        if find_login_form(parse_forms(text, url)) is not None:
            logger.warning("conference booking outcome unknown: the school asked to sign in again")
            return self._settled(client, path, token, request_id, action, checked, diagnosis, SUBMIT_SIGNED_OUT_KEY, False)
        if not history and 400 <= status < 500:
            return self._refused(client, path, conference_id, request_id, status, text, diagnosis)
        return self._settled(client, path, token, request_id, action, checked, diagnosis, SUBMIT_UNCERTAIN_KEY, 200 <= status < 300)

    def _refused(self, client, path, conference_id, request_id, status, text, diagnosis):
        errors = school_messages(text)
        logger.info("conference booking refused by the school with status %d", status)
        self.conferences._forget_request(request_id)
        fresh = self._fresh(client, path, conference_id)
        extra = {"state": STATE_INVALID, "errors": errors, "diagnosis": diagnosis}
        if fresh is not None:
            extra["page"] = self._public(path, fresh)
        if errors:
            return messages.result(False, REFUSED_KEY, **extra)
        return messages.result(False, SUBMIT_REJECTED_KEY, {"status": status}, **extra)

    def _settled(self, client, path, token, request_id, action, checked, diagnosis, unsure_key, accepted):
        self.conferences._note_own_change({"row": booking_cells(checked["booking"])})
        conference_id = conference_id_of(path)
        fresh = self._fresh(client, path, conference_id)
        page = self._public(path, fresh) if fresh is not None else None
        if fresh is not None and self._arrived(action, checked, fresh, accepted):
            logger.info("conference booking sent and confirmed by the appointments read again")
            self.conferences._record(request_id, token, STATE_DONE)
            return messages.result(True, DONE_KEYS[action], state=STATE_DONE, page=page, diagnosis=diagnosis)
        logger.warning("conference booking outcome unknown: the appointments read again show no matching change")
        self.conferences._record(request_id, token, STATE_UNCERTAIN)
        return messages.result(False, unsure_key, state=STATE_UNCERTAIN, page=page, diagnosis=diagnosis)
