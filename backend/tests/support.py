from app.service import ConnectionService
from app.store import ConnectionStore, Store

DEFAULT_SECRETS = {"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"}
SCHOOL_ONE = "https://school-one.example"
SCHOOL_TWO = "https://school-two.example"


class Response:
    def __init__(self, status_code, url, text="", content_type="text/html; charset=utf-8", json_data=None, location=""):
        self.status_code = status_code
        self.url = url
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"Content-Type": content_type}
        if location:
            self.headers["Location"] = location
        self.json_data = json_data

    def json(self):
        if self.json_data is None:
            raise ValueError("no json")
        return self.json_data


def add_school(store, url=SCHOOL_ONE, secrets=None, complete=True, **fields):
    entry = store.add_connection(url, setup_complete=complete, **fields)
    store.save_secrets(entry["id"], dict(DEFAULT_SECRETS if secrets is None else secrets))
    return entry["id"]


def scoped(store, connection_id):
    return ConnectionStore(store, connection_id)


def connection_service(store, connection_id, client_factory=None):
    return ConnectionService(scoped(store, connection_id), client_factory=client_factory)


def single_school(data_dir, url=SCHOOL_ONE, secrets=None, client_factory=None, complete=True, **fields):
    store = Store(data_dir)
    connection_id = add_school(store, url, secrets, complete, **fields)
    service = connection_service(store, connection_id, client_factory)
    return service, service.store, connection_id
