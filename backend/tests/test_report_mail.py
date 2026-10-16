import json
import logging

from app import reportmail
from tests.mail_fakes import FakeImap
from tests.mail_fakes import FakeSieveTransport
from tests.test_mail_imap import service_with_mail
from tests.test_mail_settings import service_with_web

PHP_DATA = {
    "mailboxes": {
        "folders": {
            "inbox": {"mailboxId": "abc1234", "type": "inbox", "name": "Posteingang", "unreadCount": 1, "totalCount": 4},
            "sent": {"mailboxId": "def5678901234", "type": "sent", "name": "Gesendet", "unreadCount": 0, "totalCount": 9},
        },
        "customFolders": [],
    },
    "serverConfig": {
        "autoCompleteUrls": {
            "users": "/iserv/core/api/autocomplete/users",
            "groups": "/iserv/addressbook/api/c0ffee12345/lookup",
        },
        "domains": ["school.example"],
    },
    "userData": {"id": "6f1f6f8e-1111-4c2b-9b9b-111111111111", "reportsUrl": "/iserv/mail/api/reports"},
}


class Page:
    def __init__(self, text, status=200, url="https://school.example/iserv/mail"):
        self.text = text
        self.status_code = status
        self.url = url


class Fetcher:
    def __init__(self, pages):
        self.pages = pages
        self.asked = []

    def fetch(self, path, params=None):
        self.asked.append(path)
        return self.pages[path]

    def fetch_capped(self, path, limit, timeout, expired=None):
        self.asked.append(path)
        return self.pages[path]


def mail_page():
    return Page(
        '<html><script type="application/json" id="php-data">%s</script>'
        '<script src="/iserv/mail/static/assets/index-a1b2c3d4.js"></script></html>' % json.dumps(PHP_DATA)
    )


SCRIPT = Page("const a = fetch(`/iserv/mail/api/v1/message/${box}/${uid}`); const b = `/iserv/mail/preview/${box}/${uid}`; const c = '/iserv/static/x.png';")


def test_server_config_paths_are_shown_as_path_words_and_ids_stay_masked():
    lines = reportmail.php_data_lines(mail_page().text)
    text = "\n".join(lines)
    assert "- #php-data serverConfig paths: 2" in lines
    assert "serverConfig.autoCompleteUrls.users: /iserv/core/api/autocomplete/users" in text
    assert "c0ffee12345" not in text
    assert "- #php-data folders: 2 (types: inbox, sent)" in lines
    assert "/iserv/mail/api/reports" in text
    assert "Posteingang" not in text and "abc1234" not in text


def test_a_page_without_php_data_says_so():
    assert reportmail.php_data_lines("<html></html>") == ["- #php-data: not on the page"]
    assert reportmail.php_data_lines('<script id="php-data">{broken</script>') == ["- #php-data: unreadable"]


def test_the_mail_app_script_paths_are_listed_unmasked():
    lines = reportmail.script_api_lines([SCRIPT.text])
    assert lines == ["- Mail app API paths in scripts: /iserv/mail/api/v1/message/<expr>/<expr> | /iserv/mail/preview/<expr>/<expr>"]


def test_the_web_part_reads_the_page_and_its_mail_scripts():
    fetcher = Fetcher({"/iserv/mail": mail_page(), "/iserv/mail/static/assets/index-a1b2c3d4.js": SCRIPT})
    text = "\n".join(reportmail.web_lines(fetcher))
    assert "HTTP 200" in text and "/iserv/mail/api/v1/message/<expr>/<expr>" in text


def test_the_imap_part_names_structure_only(tmp_path):
    service, _, school, _, _ = service_with_mail(tmp_path, FakeImap)
    lines = reportmail.imap_lines(service.connection(school).mail().structure())
    text = "\n".join(lines)
    assert "capabilities: IMAP4REV1, MOVE, SPECIAL-USE, UIDPLUS" in text
    assert "roles: archive, drafts, folder, inbox, sent, trash" in text
    assert "IMAP inbox: 2 mails, 1 unread" in text
    assert "text/plain" in text
    assert "Rückmeldung" not in text and "office@school.example" not in text


def test_a_refused_imap_sign_in_is_a_line_not_a_failure(tmp_path):
    service, _, school, _, _ = service_with_mail(tmp_path, lambda: FakeImap(password="other"))
    lines = reportmail.mail_lines(None, service.connection(school), greet=lambda host: ["SIEVE"])
    assert "- IMAP: not read (api.mail.signInRefused)" in lines


def test_a_part_of_the_mail_report_that_could_not_be_read_leaves_its_cause_in_the_log(caplog):
    class Unreachable:
        def mail(self):
            raise TimeoutError("school.example")

    def refuse(host):
        raise ConnectionRefusedError(host)

    with caplog.at_level(logging.INFO, logger="app.reportmail"):
        assert "- IMAP: not read (TimeoutError)" in reportmail.mail_lines(None, Unreachable())
        reportmail.greeting_lines("school.example", connect=refuse)
    lines = [record.getMessage() for record in caplog.records if record.name == "app.reportmail"]
    assert any(line.startswith("mail report: imap not read: TimeoutError") for line in lines)
    assert any(line.startswith("mail report: sieve greeting not read: ConnectionRefusedError") for line in lines)
    assert not any("school.example" in line for line in lines)

def test_the_sieve_greeting_lists_its_words():
    lines = reportmail.greeting_lines("school.example", connect=lambda host: ["IMPLEMENTATION", "SIEVE", "fileinto", "vacation", "SASL", "PLAIN"])
    assert lines == ["- ManageSieve 4190: IMPLEMENTATION, PLAIN, SASL, SIEVE, fileinto, vacation"]

    def refuse(host):
        raise ConnectionRefusedError("no")

    assert reportmail.greeting_lines("school.example", connect=refuse) == ["- ManageSieve 4190: not reached (ConnectionRefusedError)"]


def test_the_settings_forms_and_lookup_are_recorded_as_shape_only(tmp_path):
    service, school, _ = service_with_web(tmp_path)
    lines = reportmail.web_settings_lines(service.connection(school).mail_web().structure())
    text = "\n".join(lines)
    assert "- Mail account data: page size 25, tags 2 (with colour 2), addresses 3, display name yes, auto archive 1, flags: hasActiveVacation" in lines
    assert "  - /iserv/mail/settings/vacation (linked): forms 1" in lines
    assert "  - /iserv/mail/settings (guessed): no settings page (HTTP 200)" in lines
    assert "      - text vacation[subject] (label len 7)" in lines
    assert "      - select signature[default] (label len 12) options 2" in lines
    assert any(line.startswith("      - collection: entries 1, prototype fields: text filter[rules][__name__][name]") for line in lines)
    assert "- Recipient lookup /iserv/core/api/autocomplete/users ?query=: HTTP 200 json list len 2, keys: email, label, type" in lines
    assert "- Calendar entry form /iserv/calendar/create (named on the calendar page): forms 1" in lines
    assert "  - route calendar_create_event_from_mail: /iserv/calendar/api/v1/eventFromMail" in lines
    assert "      - textarea event[description] (label len 12)" in lines
    assert "t0ken" not in text and "Abwesenheitsnotiz" not in text and "Alexa" not in text


def test_the_sieve_scripts_are_named_with_their_extensions_only():
    lines = reportmail.sieve_lines({"scripts": [{"name": "iserv", "active": True, "extensions": ["fileinto", "vacation"]}, {"name": "Max Muster 2019", "active": False, "extensions": []}]})
    assert lines[0] == "- Sieve scripts: 2"
    assert lines[1] == "  - iserv (active), extensions: fileinto, vacation"
    assert "Max Muster" not in lines[2]


def test_the_mail_scripts_follow_their_chunks_and_name_report_todo_and_tag_paths():
    index = Page('import("./chunk-aa11bb22.js");const x="/iserv/mail/static/assets/settings-cc33dd44.js";const y="./vendor.css";')
    chunk = Page('fetch("/iserv/mail/api/v1/report/abuse",{method:"POST"});const t="/iserv/todo/api/v1/tasks/fromMail";')
    settings = Page('const s="/iserv/mail/settings/tags";const n="/iserv/static/x.png";')
    fetcher = Fetcher({
        "/iserv/mail": mail_page(),
        "/iserv/mail/static/assets/index-a1b2c3d4.js": index,
        "/iserv/mail/static/assets/chunk-aa11bb22.js": chunk,
        "/iserv/mail/static/assets/settings-cc33dd44.js": settings,
    })
    lines = reportmail.web_lines(fetcher)
    assert "- Mail scripts read: 3" in lines
    assert "- Mail app API paths in scripts: /iserv/mail/api/v1/report/abuse | /iserv/todo/api/v1/tasks/fromMail" in lines
    assert "- Mail app paths for reports, to-do, tags and settings: /iserv/mail/settings/tags" in lines
    assert "/iserv/mail/static/assets/vendor.css" not in fetcher.asked


def test_the_chunk_paths_stay_inside_the_mail_app():
    found = reportmail.chunk_paths('"./a-1.js" "../../../calendar/x.js" "/iserv/mail/b.mjs" "https://cdn.example/c.js"', "/iserv/mail/static/assets/index.js")
    assert found == ["/iserv/mail/static/assets/a-1.js", "/iserv/mail/b.mjs"]


def test_the_tag_and_general_settings_pages_are_recorded_as_form_shapes():
    general = Page(
        '<form method="post" action="/iserv/mail/settings/general"><select name="general[limit]">'
        '<option value="10">10</option><option value="100">100</option></select>'
        '<input name="general[signature]" value="Mia Musterkind"></form><a href="/iserv/mail/settings/tags">Tags</a>'
        '<script type="application/json" id="data">{"name": "Mia"}</script>',
        url="https://school.example/iserv/mail/settings/general",
    )
    tags = Page("<html></html>", status=404, url="https://school.example/iserv/mail/settings/tags")
    fetcher = Fetcher({"/iserv/mail/settings/tags": tags, "/iserv/mail/settings/general": general})
    lines = reportmail.report_page_lines(fetcher)
    assert lines[0] == "- Mail page /iserv/mail/settings/tags: HTTP 404, final /iserv/mail/settings/tags"
    assert "- Mail page /iserv/mail/settings/general: HTTP 200, final /iserv/mail/settings/general" in lines
    assert "  - Form: /iserv/mail/settings/general (post)" in lines
    assert "    - general[limit] (select, options 2, values 10 / 100)" in lines
    assert "  - mail links: /iserv/mail/settings/tags" in lines
    assert lines[-1] == "- Mail page /iserv/account/settings: not read (KeyError)"
    assert "Musterkind" not in "\n".join(lines) and "(root)" not in "\n".join(lines)
