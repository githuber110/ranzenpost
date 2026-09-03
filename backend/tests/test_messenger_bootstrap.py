from pathlib import Path

import pytest

from app.iserv.messenger import BootstrapNotFoundError, parse_bootstrap

FIXTURES = Path(__file__).parent / "fixtures"


def read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_bootstrap_extracts_the_matrix_auth_set_from_the_messenger_page():
    auth = parse_bootstrap(read("messenger_page.html"))
    assert auth["access_token"] == "fixture-access-token-0123456789abcdef0123456789abcdef01234567"
    assert auth["device_id"] == "ISEfixturedeviceid00000000000000000000000"
    assert auth["home_server"] == "22222222-2222-2222-2222-222222222222"
    assert auth["user_id"].startswith("@33333333")
    assert auth["iserv_token"].startswith("fixture-iserv-token")
    assert auth["iserv_cryptkey"].startswith("fixture-cryptkey")


def test_parse_bootstrap_is_robust_against_a_leading_assignment_prefix():
    html = (
        "<html><body><script>window.__ISERV__ = "
        + '{"other":1,"messenger_authentication":{'
        + '"access_token":"tok","device_id":"dev","home_server":"srv",'
        + '"user_id":"@u:srv","iserv_token":"it","iserv_cryptkey":"ck"}};'
        + "</script></body></html>"
    )
    auth = parse_bootstrap(html)
    assert auth == {
        "access_token": "tok",
        "device_id": "dev",
        "home_server": "srv",
        "user_id": "@u:srv",
        "iserv_token": "it",
        "iserv_cryptkey": "ck",
    }


def test_parse_bootstrap_ignores_unrelated_scripts_around_it():
    html = (
        "<html><body>"
        '<script src="/assets/a.js"></script>'
        "<script>var noise = {\"totally\":\"unrelated\"};</script>"
        '<script type="application/json">'
        '{"messenger_authentication":{"access_token":"tok","device_id":"dev",'
        '"home_server":"srv","user_id":"@u:srv","iserv_token":"it","iserv_cryptkey":"ck"}}'
        "</script>"
        "<script>console.log(1);</script>"
        "</body></html>"
    )
    auth = parse_bootstrap(html)
    assert auth["access_token"] == "tok"


def test_parse_bootstrap_raises_when_the_marker_is_missing():
    with pytest.raises(BootstrapNotFoundError):
        parse_bootstrap("<html><body><script>{}</script></body></html>")


def test_parse_bootstrap_raises_on_empty_html():
    with pytest.raises(BootstrapNotFoundError):
        parse_bootstrap("")


def test_parse_bootstrap_ignores_a_bootstrap_object_missing_required_fields():
    html = (
        "<html><body><script>"
        '{"messenger_authentication":{"access_token":"","device_id":"dev",'
        '"home_server":"","user_id":"","iserv_token":"","iserv_cryptkey":""}}'
        "</script></body></html>"
    )
    with pytest.raises(BootstrapNotFoundError):
        parse_bootstrap(html)
