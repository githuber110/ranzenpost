from app.service import ConnectionService
from app.store import ConnectionStore, Store

DEFAULT_SECRETS = {"username": "u", "password": "p", "totp_secret": "JBSWY3DPEHPK3PXP"}
SCHOOL_ONE = "https://school-one.example"
SCHOOL_TWO = "https://school-two.example"


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
