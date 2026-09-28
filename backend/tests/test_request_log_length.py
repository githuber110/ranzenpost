import io
import logging

import pytest
import requests
from requests.adapters import BaseAdapter

from app import requestlog

BODY = b"<html>" + b"x" * 500 + b"</html>"


class ChunkedAdapter(BaseAdapter):
    def __init__(self):
        super().__init__()
        self.raw = None

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        response = requests.Response()
        response.status_code = 200
        response.url = request.url
        response.request = request
        response.headers["Content-Type"] = "text/html"
        response.headers["Transfer-Encoding"] = "chunked"
        self.raw = io.BytesIO(BODY)
        response.raw = self.raw
        response.connection = self
        return response

    def close(self):
        pass


def session_with(adapter):
    session = requestlog.install(requests.Session(), "school.example")
    session.mount("https://", adapter)
    return session


def logged_lengths(caplog):
    return [record.getMessage().split(" ")[5] for record in caplog.records if record.name == "iserv"]


def test_a_chunked_answer_is_logged_with_its_real_length(caplog):
    session = session_with(ChunkedAdapter())
    with caplog.at_level(logging.INFO, logger="iserv"):
        response = session.get("https://school.example/iserv/parentletter/parent/index")
    assert response.content == BODY
    assert logged_lengths(caplog) == [f"{len(BODY)}B"]


def test_a_streamed_answer_is_not_read_by_the_log(caplog):
    adapter = ChunkedAdapter()
    session = session_with(adapter)
    with caplog.at_level(logging.INFO, logger="iserv"):
        session.get("https://school.example/iserv/js/a.js", stream=True)
    assert adapter.raw.tell() == 0
    assert logged_lengths(caplog) == ["0B"]


class BrokenBody(io.BytesIO):
    def read(self, *args, **kwargs):
        raise OSError("connection dropped")


class BrokenAdapter(ChunkedAdapter):
    def send(self, request, **kwargs):
        response = super().send(request, **kwargs)
        self.raw = BrokenBody(BODY)
        response.raw = self.raw
        return response


def test_a_broken_body_still_fails_the_request_instead_of_being_swallowed():
    session = session_with(BrokenAdapter())
    with pytest.raises(OSError):
        session.get("https://school.example/iserv/")


class BrokenRedirectBody(io.BytesIO):
    def read(self, *args, **kwargs):
        if "decode_content" in kwargs:
            return b""
        raise requests.exceptions.ChunkedEncodingError("broken redirect body")


class RedirectAdapter(ChunkedAdapter):
    def send(self, request, **kwargs):
        response = super().send(request, **kwargs)
        if request.url.endswith("/iserv/auth/login"):
            response.status_code = 302
            response.headers["Location"] = "https://school.example/iserv/"
            response.raw = BrokenRedirectBody(b"")
        return response


def test_a_redirect_with_a_broken_body_is_still_followed():
    session = session_with(RedirectAdapter())
    response = session.get("https://school.example/iserv/auth/login")
    assert response.status_code == 200
    assert response.content == BODY
