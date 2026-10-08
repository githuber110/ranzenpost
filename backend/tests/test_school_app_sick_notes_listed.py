import pytest

from app.iserv.dsa import DieSchulAppClient
from app.iserv.errors import DataError


class Reply:
    def __init__(self, status, payload=None, broken=False):
        self.status_code = status
        self.payload = payload
        self.broken = broken
        self.headers = {}
        self.url = "https://school.example/iserv/dieschulapp/api/1.0/sickNotes/userSelection/"
        self.text = ""

    def json(self):
        if self.broken:
            raise ValueError("no json")
        return self.payload


class Session:
    def __init__(self, reply):
        self.reply = reply

    def get(self, url, timeout=None, **kwargs):
        return self.reply


def listed(reply):
    client = DieSchulAppClient.__new__(DieSchulAppClient)
    client.session = Session(reply)
    client.base_url = "https://school.example"
    client.timeout = 5
    client._checked = lambda response: response
    return client.sick_note_children_listed()


def test_only_a_json_list_counts_as_a_listed_answer():
    assert listed(Reply(200, [])) == []
    assert listed(Reply(200, [{"id": 7, "displayname": "Alex Example"}]))[0]["id"] == 7


@pytest.mark.parametrize("reply", [Reply(403, []), Reply(404, []), Reply(200, None), Reply(200, {}), Reply(200, broken=True)])
def test_a_refusal_or_a_shapeless_answer_is_not_a_listed_answer(reply):
    assert listed(reply) is None


def test_an_expired_school_app_session_is_an_error():
    with pytest.raises(DataError):
        listed(Reply(401, []))
