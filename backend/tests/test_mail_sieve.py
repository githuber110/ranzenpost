import pytest

from app.iserv import sieve
from app.mail_service import MailService
from tests.mail_fakes import FakeImap, FakeSieveTransport
from tests.test_mail_imap import service_with_mail


def with_sieve(tmp_path, transport):
    service, store, school, _, clock = service_with_mail(tmp_path, FakeImap)
    connection = service.connection(school)
    opened = []

    def sieve_opener(host, username, password):
        opened.append(host)
        return sieve.open_sieve(host, username, password, transport=transport.fresh())

    connection._mail_service = MailService(connection, opener=lambda host: FakeImap(), clock=lambda: clock["now"], sieve_opener=sieve_opener)
    return service, school, opened


def test_the_client_signs_in_only_after_tls_and_lists_scripts():
    transport = FakeSieveTransport()
    client = sieve.open_sieve("school.example", "u", "p", transport=transport)
    assert transport.secure is True and transport.signed_in is True
    assert client.capabilities["SIEVE"] == "fileinto reject envelope vacation"
    assert client.scripts() == [{"name": "iserv", "active": True}]
    assert "fileinto" in client.script("iserv")


def test_a_server_without_tls_never_gets_the_password():
    transport = FakeSieveTransport(tls=False)
    with pytest.raises(sieve.SieveUnreachable):
        sieve.open_sieve("school.example", "u", "p", transport=transport)
    assert not any(b"AUTHENTICATE" in line for line in transport.sent)


def test_a_wrong_password_is_a_sign_in_refusal():
    with pytest.raises(sieve.SieveSignInRefused):
        sieve.open_sieve("school.example", "u", "wrong", transport=FakeSieveTransport())


def test_the_client_has_no_write_command():
    assert not any(hasattr(sieve.SieveClient, name) for name in ("put", "check", "activate", "delete"))


def test_required_extensions_are_read_from_the_script():
    assert sieve.required_extensions('require ["fileinto", "vacation"];\nrequire "reject";\nkeep;') == ["fileinto", "vacation", "reject"]
    assert sieve.required_extensions("keep;") == []


def test_the_structure_names_scripts_and_their_extensions_only(tmp_path):
    transport = FakeSieveTransport()
    service, school, opened = with_sieve(tmp_path, transport)
    found = service.connection(school).mail().sieve_structure()
    assert found["scripts"] == [{"name": "iserv", "active": True, "extensions": ["fileinto"]}]
    assert "vacation" in found["capabilities"]["SIEVE"]
    assert opened == ["school.example"]
    assert not any(command in b"".join(transport.sent) for command in (b"PUTSCRIPT", b"SETACTIVE", b"CHECKSCRIPT"))


def test_an_unreachable_rules_server_is_named(tmp_path):
    service, school, _ = with_sieve(tmp_path, FakeSieveTransport())

    def refuse(host, username, password):
        raise OSError("refused")

    service.connection(school).mail().sieve_opener = refuse
    with pytest.raises(sieve.SieveUnreachable):
        service.connection(school).mail().sieve_structure()
