import pytest

from custom_components.ranzenpost.api import AuthError, ConnectionError, Event, Lesson, NotFoundError, RanzenpostApi


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body
        self.released = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.released = True

    async def json(self):
        return self.body


class FakeSession:
    def __init__(self, response):
        self.response = response

    def request(self, method, url, params=None, json=None, headers=None):
        self.sent = (method, url, params, json)
        return self.response


@pytest.mark.parametrize(
    ("status", "raised"),
    [(200, None), (401, AuthError), (404, NotFoundError), (500, ConnectionError)],
)
async def test_every_answer_is_released_after_reading(status, raised):
    response = FakeResponse(status, {"ok": True})
    api = RanzenpostApi(FakeSession(response), "addon-host", 8099, "a" * 43)

    if raised is None:
        assert await api._get("/api/integration/info") == {"ok": True}
    else:
        with pytest.raises(raised):
            await api._get("/api/integration/info")
    assert response.released is True

def _event_json(**extra):
    return {"uid": "u", "start": "2026-09-02T08:00:00+02:00", "end": "2026-09-02T08:45:00+02:00", **extra}


def test_an_event_from_an_older_app_leaves_the_substitution_unknown():
    assert Event.from_json(_event_json()).substitution is None
    assert Event.from_json(_event_json(substitution=True)).substitution is True
    assert Event.from_json(_event_json(substitution=False)).substitution is False


def test_a_move_keeps_only_a_known_direction():
    assert Event.from_json(_event_json()).moved == ""
    assert Event.from_json(_event_json(moved="here")).moved == "here"
    assert Event.from_json(_event_json(moved="sideways")).moved == ""
    lesson = Lesson.from_json(_event_json(moved="away", cancelled=True))
    assert lesson.as_attributes()["moved"] == "away"
