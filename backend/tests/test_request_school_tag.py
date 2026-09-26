import logging
import re
from types import SimpleNamespace

import requests

from app import requestlog
from app.messenger import MessengerService
from app.store import Store
from tests.support import SCHOOL_TWO, add_school, connection_service
from tests.test_service_modules import ProbeClient

REPORT_LINE = re.compile(
    r"\biserv: (?P<tag>[\w-]+) (?P<method>[A-Z]+) (?P<path>\S+) (?P<status>\d+) \S+ (?P<length>\d+)B (?P<duration>\d+)ms"
)
SCHOOL = "b2c3d4e5"


def answered(session, url, status=200, body=b"<html></html>", content_type="text/html"):
    response = requests.Response()
    response.status_code = status
    response.url = url
    response._content = body
    response.headers["Content-Type"] = content_type
    response.request = requests.Request("GET", url).prepare()
    response.connection = session.get_adapter(url)
    return response


def labelled_session(school):
    session = requestlog.install(requests.Session())
    requestlog.tag_school(SimpleNamespace(session=session), school)
    return session


def lines(caplog):
    return [record.getMessage() for record in caplog.records if record.name == "iserv"]


def test_a_request_line_ends_with_the_school_of_its_session(caplog):
    session = labelled_session(SCHOOL)
    with caplog.at_level(logging.INFO, logger="iserv"):
        requestlog.log_response(answered(session, "https://school-two.example/iserv/parentletter/parent/index"))
    assert lines(caplog) == ["letters GET /iserv/parentletter/parent/index 200 text/html 13B 0ms school#b2c3d4e5"]


def test_the_school_tag_keeps_the_report_pattern_intact(caplog):
    session = labelled_session(SCHOOL)
    with caplog.at_level(logging.INFO, logger="iserv"):
        requestlog.log_response(answered(session, "https://school-two.example/_matrix/client/v3/sync", body=b"{}"))
    match = REPORT_LINE.search("iserv: " + lines(caplog)[0])
    assert match and match.group("tag") == "messenger" and match.group("length") == "2"


def test_two_schools_write_their_own_tags(caplog):
    first = labelled_session("a1b2c3d4")
    second = labelled_session(SCHOOL)
    with caplog.at_level(logging.INFO, logger="iserv"):
        requestlog.log_response(answered(first, "https://school-one.example/iserv/"))
        requestlog.log_response(answered(second, "https://school-two.example/iserv/"))
    assert [line.rsplit(" ", 1)[1] for line in lines(caplog)] == ["school#a1b2c3d4", "school#b2c3d4e5"]


def test_an_unlabelled_session_writes_the_line_as_before(caplog):
    session = requestlog.install(requests.Session())
    with caplog.at_level(logging.INFO, logger="iserv"):
        requestlog.log_response(answered(session, "https://school.example/iserv/"))
    assert lines(caplog) == ["start GET /iserv/ 200 text/html 13B 0ms"]


class SessionClient(ProbeClient):
    def __init__(self, url):
        super().__init__(url)
        self.session = requestlog.install(requests.Session())


def test_signing_in_labels_the_iserv_session_with_its_school(tmp_path):
    store = Store(tmp_path / "data")
    connection_id = add_school(store, SCHOOL_TWO)
    connection = connection_service(store, connection_id, SessionClient)
    client = connection.iserv_session()
    assert requestlog.school_of(client.session.get_adapter(SCHOOL_TWO)) == connection_id


def test_the_matrix_session_is_labelled_with_its_school():
    service = MessengerService(
        SimpleNamespace(id=SCHOOL, store=SimpleNamespace(load_secrets=lambda: {})),
        matrix_client_factory=lambda base_url, token: SimpleNamespace(session=requests.Session()),
    )
    service.store = SimpleNamespace(
        load_secrets=lambda: {"messenger_access_token": "tok", "messenger_matrix_base_url": "https://school-two.example"}
    )
    client = service._matrix_client()
    assert requestlog.school_of(client.session.get_adapter("https://school-two.example/")) == SCHOOL
