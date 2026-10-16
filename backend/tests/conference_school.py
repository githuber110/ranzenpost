from pathlib import Path
from types import SimpleNamespace

from app.iserv.conferences import ARCHIVE_PATH, LIST_PATH

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ORIGIN = "https://school.example"
DETAIL_PATH = "/iserv/parentconference/attendee/conference/7"
TEACHER_PATH = DETAIL_PATH + "/teacher/12"
BOOK_PATH = TEACHER_PATH + "/book"
CANCEL_PATH = "/iserv/parentconference/attendee/booking/{booking}/delete"
SHARED_CANCEL_PATH = "/iserv/parentconference/attendee/booking/delete"
BOOK_TOKEN = "token-book-1"
SLOTS = {"101": "14:00 - 14:10", "103": "14:20 - 14:30"}
CHILD_VALUE = "501"
FORM_ERROR = '<div class="alert alert-danger">Das Formular enthält Fehler.</div>'
CHILD_ERROR = '<span class="help-block">Bitte wählen Sie ein Kind aus.</span>'
BOOKED_NOTICE = '<div class="alert alert-success">Der Termin wurde gebucht.</div>'
CANCELLED_NOTICE = '<div class="alert alert-success">Der Termin wurde abgesagt.</div>'
TAKEN_WARNING = '<div class="alert alert-warning">Der Termin ist bereits vergeben.</div>'
MIXED_NOTICE = BOOKED_NOTICE + '<div class="alert alert-danger">Die Bestätigung konnte nicht gesendet werden.</div>'
EMPTY_ARCHIVE = (
    '<div id="content"><h1>Elternsprechtage Archiv</h1>'
    '<div class="alert alert-info">Derzeit sind keine Elternsprechtage verfügbar.</div></div>'
)


def read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def answer(path, text, status=200, history=None):
    return SimpleNamespace(status_code=status, url=ORIGIN + path, text=text, history=list(history or []), headers={})


class ConferenceSchool:
    def __init__(self):
        self.bookings = {}
        self.sent = []
        self.fetched = []
        self.failing_slot = ""
        self.quiet_slot = ""
        self.refusing = False
        self.browser_checks = True
        self.next_booking = 31
        self.shared_cancel = False
        self.others = set()
        self.warning_slot = ""
        self.mixed_slot = ""
        self.unrelated_slot = ""

    def cancel_form(self, booking):
        if self.shared_cancel:
            return (
                '<form method="post" action="%s"><input type="hidden" name="_token" value="token-cancel">'
                '<input type="hidden" name="booking" value="%s">'
                '<button type="submit" class="btn btn-danger btn-xs">Absagen</button></form>' % (SHARED_CANCEL_PATH, booking)
            )
        return (
            '<form method="post" action="%s"><input type="hidden" name="_token" value="token-cancel-%s">'
            '<button type="submit" class="btn btn-danger btn-xs">Absagen</button></form>' % (CANCEL_PATH.format(booking=booking), booking)
        )

    def detail_page(self, notice=""):
        rows = "".join(
            '<tr><td>%s</td><td>Frau Muster</td><td>R 101</td><td>Kim</td><td>%s</td></tr>'
            % (SLOTS[slot], self.cancel_form(booking))
            for booking, slot in sorted(self.bookings.items())
        )
        page = read("conference_detail.html").replace("<!--BOOKINGS-->", rows)
        page = page.replace("<!--FREE-->", str(len(SLOTS) - len(self.bookings)))
        return page.replace("<!--NOTICE-->", notice)

    def teacher_page(self, invalid=False, chosen=""):
        page = read("conference_teacher.html")
        booked = set(self.bookings.values())
        for slot, label in SLOTS.items():
            marker = "<!--S%s-->" % slot
            if slot in booked:
                page = page.replace(marker + "> " + label, " disabled> " + label + " (gebucht)")
            elif slot in self.others:
                page = page.replace(marker + "> " + label, " disabled> " + label + " (belegt)")
            else:
                page = page.replace(marker, " checked" if slot == chosen else "")
        if not self.browser_checks:
            page = page.replace(" required>", ">")
        if invalid:
            page = page.replace("<!--FORM_ERROR-->", FORM_ERROR)
            page = page.replace("<!--CHILD_ERROR_CLASS-->", " has-error")
            page = page.replace("<!--CHILD_ERROR-->", CHILD_ERROR)
        return page

    def page(self, path):
        clean = path.split("?", 1)[0]
        if clean == LIST_PATH:
            return answer(clean, read("conference_overview.html"))
        if clean == ARCHIVE_PATH:
            return answer(clean, EMPTY_ARCHIVE)
        if clean == DETAIL_PATH:
            return answer(clean, self.detail_page())
        if clean == TEACHER_PATH:
            return answer(clean, self.teacher_page())
        return answer(clean, "<h1>Nicht gefunden</h1>", status=404)

    def fetch(self, path, params=None):
        self.fetched.append(path)
        return self.page(path)

    def fetch_or_raise(self, path, params=None):
        from app.iserv.errors import DataError

        response = self.fetch(path, params)
        if response.status_code != 200:
            raise DataError("request failed: %d" % response.status_code)
        return response

    def post_absolute(self, url, data, timeout=30, follow_redirects=True, headers=None):
        pairs = list(data.items()) if isinstance(data, dict) else list(data)
        self.sent.append((url, pairs))
        values = dict(pairs)
        path = url[len(ORIGIN):] if url.startswith(ORIGIN) else url
        if self.refusing:
            return answer(path, "<h1>Zugriff verweigert</h1>", status=403)
        if path == BOOK_PATH:
            return self._book(values)
        if path == SHARED_CANCEL_PATH and str(values.get("_token") or "").startswith("token-cancel") and values.get("booking") in self.bookings:
            del self.bookings[values["booking"]]
            return answer(DETAIL_PATH, self.detail_page(CANCELLED_NOTICE), history=[answer(path, "", status=302)])
        for booking in list(self.bookings):
            if path == CANCEL_PATH.format(booking=booking) and values.get("_token") == "token-cancel-%s" % booking:
                del self.bookings[booking]
                return answer(DETAIL_PATH, self.detail_page(CANCELLED_NOTICE), history=[answer(path, "", status=302)])
        return answer(path, "<h1>Nicht gefunden</h1>", status=404)

    def _book(self, values):
        slot = values.get("booking[slot]", "")
        if values.get("booking[_token]") != BOOK_TOKEN or slot not in SLOTS or slot in self.bookings.values():
            return answer(BOOK_PATH, self.teacher_page(invalid=True), status=200)
        if values.get("booking[child]") != CHILD_VALUE:
            return answer(BOOK_PATH, self.teacher_page(invalid=True, chosen=slot), status=200)
        if slot == self.quiet_slot:
            return answer(BOOK_PATH, self.teacher_page(chosen=slot), status=200)
        if slot == self.warning_slot:
            return answer(DETAIL_PATH, self.detail_page(TAKEN_WARNING), history=[answer(BOOK_PATH, "", status=302)])
        if slot == self.unrelated_slot:
            self.others.add(next(other for other in SLOTS if other != slot))
            return answer(DETAIL_PATH, self.detail_page(), history=[answer(BOOK_PATH, "", status=302)])
        self.bookings[str(self.next_booking)] = slot
        self.next_booking += 1
        if slot == self.failing_slot:
            return answer(BOOK_PATH, "Bad gateway", status=502)
        if slot == self.mixed_slot:
            return answer(DETAIL_PATH, self.detail_page(MIXED_NOTICE), history=[answer(BOOK_PATH, "", status=302)])
        return answer(DETAIL_PATH, self.detail_page(BOOKED_NOTICE), history=[answer(BOOK_PATH, "", status=302)])
