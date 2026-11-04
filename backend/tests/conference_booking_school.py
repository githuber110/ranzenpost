import json
from types import SimpleNamespace

from app.iserv.errors import DataError

ORIGIN = "https://school.example"
CONFERENCE = "0b1f8f7a-6f6e-4f0a-9d3e-1c2b3a4d5e6f"
LIST_PATH = "/iserv/parentconference/attendee/"
WIZARD_PATH = "/iserv/parentconference/attendee/appointments/conference/" + CONFERENCE
API = "/iserv/parentconference/api"
CONFERENCE_PATH = API + "/conference/" + CONFERENCE
APPOINTMENTS_PATH = API + "/conferences/" + CONFERENCE + "/attendee/appointments"
BOOKINGS_PATH = API + "/conferences/" + CONFERENCE + "/bookings"
HOSTS = [
    {"id": "host-1", "userId": "user.muster", "userName": "Frau Muster", "location": "R 101", "abbreviation": "MU"},
    {"id": "host-2", "userId": "user.beispiel", "userName": "Herr Beispiel", "location": None, "abbreviation": None},
]
SLOTS = [
    {"id": "slot-1", "begin": "2026-11-17T15:00:00+01:00", "end": "2026-11-17T15:15:00+01:00", "blocked": False},
    {"id": "slot-2", "begin": "2026-11-17T15:20:00+01:00", "end": "2026-11-17T15:35:00+01:00", "blocked": False},
    {"id": "slot-3", "begin": "2026-11-17T15:40:00+01:00", "end": "2026-11-17T15:55:00+01:00", "blocked": True},
    {"id": "slot-4", "begin": "2026-11-19T15:00:00+01:00", "end": "2026-11-19T15:15:00+01:00", "blocked": False},
]
KIM = {"id": "kim.muster", "display": "Kim Muster"}
LOU = {"id": "lou.muster", "display": "Lou Muster"}
STRANGER = {"id": "nora.fremd", "display": "Nora Fremd"}
LOGIN_PAGE = '<form method="post" action="/iserv/auth/login"><input name="_username"><input type="password" name="_password"></form>'


def wizard_page(children):
    return (
        '<html data-asset-path="/iserv/"><body><div id="content"><h1>Elternsprechtage</h1>'
        '<script id="attendee-children" type="application/json">%s</script>'
        '<div id="attendee-wizard"></div></div></body></html>' % json.dumps(children)
    )


def answer(path, text, status=200, history=None):
    return SimpleNamespace(status_code=status, url=ORIGIN + path, text=text, history=list(history or []), headers={})


class BookingSchool:
    def __init__(self, children=(KIM, LOU)):
        self.children = list(children)
        self.hosts = [dict(host) for host in HOSTS]
        self.slots = [dict(slot) for slot in SLOTS]
        self.appointments = []
        self.sent = []
        self.fetched = []
        self.next_booking = 1
        self.refusal = None
        self.lost_answer = None
        self.signed_out = False
        self.silent = False
        self.unavailable = set()

    def booked_by_other(self, slot, host):
        self.appointments.append({
            "id": "other-%s" % slot, "editable": False, "timeslotId": slot, "hostId": host, "host": self._host(host),
            "children": [{"id": "x.other", "name": "Fremdes Kind"}],
        })

    def book_mine(self, slot="slot-1", host="host-1", children=("kim.muster",), editable=True):
        booking = "booking-%d" % self.next_booking
        self.next_booking += 1
        self.appointments.append({
            "id": booking, "editable": editable, "timeslotId": slot, "hostId": host, "host": self._host(host),
            "children": [self._child(child) for child in children],
        })
        return booking

    def _host(self, host_id):
        host = next(entry for entry in self.hosts if entry["id"] == host_id)
        return {"id": host["userId"], "name": host["userName"]}

    def _child(self, child_id):
        listed = next((entry for entry in self.children if entry["id"] == child_id), {"display": child_id})
        return {"id": child_id, "name": listed["display"]}

    def _conference(self):
        return {
            "id": CONFERENCE, "title": "Elternsprechtag", "description": "<p>Bitte tragen Sie sich ein.</p>",
            "begin": "2026-11-17T00:00:00+01:00", "end": "2026-11-19T00:00:00+01:00",
            "bookingBegin": "2026-11-04T00:00:00+01:00", "bookingEnd": "2026-11-12T00:00:00+01:00",
            "hosts": self.hosts, "attendees": [], "attendeeGroups": [], "timeslots": self.slots,
        }

    def fetch(self, path, params=None):
        self.fetched.append((path, list(params or [])))
        clean = path.split("?", 1)[0]
        if clean in self.unavailable:
            return answer(clean, json.dumps({"message": "kaputt"}), status=500)
        if clean == WIZARD_PATH:
            return answer(clean, wizard_page(self.children))
        if clean == CONFERENCE_PATH:
            return answer(clean, json.dumps(self._conference()))
        if clean == APPOINTMENTS_PATH:
            wanted = {value for key, value in params or [] if key == "hosts[]"}
            listed = [entry for entry in self.appointments if entry["hostId"] in wanted]
            return answer(clean, json.dumps({"appointments": listed}))
        return answer(clean, "<h1>Nicht gefunden</h1>", status=404)

    def fetch_or_raise(self, path, params=None):
        response = self.fetch(path, params)
        if response.status_code != 200:
            raise DataError("request failed: %d" % response.status_code)
        return response

    def send_json(self, method, url, payload=None, headers=None):
        self.sent.append((method, url, payload, headers))
        path = url[len(ORIGIN):]
        if self.signed_out:
            return answer("/iserv/auth/login", LOGIN_PAGE, history=[answer(path, "", status=302)])
        if self.refusal is not None:
            return answer(path, json.dumps(self.refusal[1]), status=self.refusal[0])
        if self.silent:
            return answer(path, "{}")
        if method == "POST" and path == BOOKINGS_PATH:
            booking = self.book_mine(payload["timeslotId"], payload["hostId"], payload["childrenIds"])
            return self._done(path, {"id": booking})
        booking = path.rsplit("/", 1)[1]
        current = next((entry for entry in self.appointments if entry["id"] == booking), None)
        if current is None:
            return answer(path, json.dumps({"messages": ["Nicht gefunden"]}), status=404)
        if method == "DELETE":
            self.appointments.remove(current)
            return self._done(path, {"message": "ok"})
        current["children"] = [self._child(child) for child in payload["childrenIds"]]
        return self._done(path, {"id": booking})

    def _done(self, path, body):
        if self.lost_answer is not None:
            raise self.lost_answer
        return answer(path, json.dumps(body))


class Connection:
    id = "s1"

    def __init__(self, school, profiles=None):
        self.school = school
        self.profiles = profiles if profiles is not None else [
            {"child_id": "1", "name": "Kim Muster"},
            {"child_id": "2", "name": "Lou Muster"},
        ]

    def _session(self):
        return self.school

    def stored_children(self):
        return self.profiles
