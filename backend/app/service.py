import logging
import threading
import time
from datetime import date, timedelta
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

from . import courses, holidays, integration, lockout, messages, modules, period_grid, requestlog, school_lists, signin_pause
from .signin_pause import PAUSES
from .store import (
    CHILDREN_LISTED,
    CHILDREN_REFUSED,
    CHILDREN_STATE_KEY,
    CHILDREN_UNREADABLE,
    LOGIN_HOLD,
    LOGIN_REVISION_KEY,
    connection_display_name,
    connection_short_name,
    edit_config,
    edit_secrets,
    edit_slot,
    host_of,
    split_child_key,
)
from .absence_service import AbsenceService
from .child_service import LETTERS_CHILD_PREFIX, SCHOOL_CACHE_SECONDS, ChildService, unknown_child
from .letter_service import LetterService
from .mail_service import MailFile, MailNotOffered, MailService
from .file_service import AccountModuleNotOffered, FileService
from .contacts_service import ContactsService
from .mail_settings import MailWebService
from .conference_service import TAB_CURRENT as CONFERENCE_TAB_CURRENT, ConferenceService
from . import news_sections
from .news_sections import NewsSections
from .task_service import TaskService, with_details
from . import account_lists
from .forum_service import READ_UNAVAILABLE_KEY, ForumService
from .refusals import Refusals
from .not_configured import ConnectionChangedError, NotConfiguredError
from .attachments import attachment_dict, clean_filename
from .failure import failure_cause
from .identifiers import as_int
from .sorting import folder_sort_key, published_sort_key, child_sort_key
from .iserv.client import IServClient
from .iserv.children import CHILD_PAGE_FORBIDDEN_KEY
from .iserv.badges import BADGES_PATH, MAIL_BADGE, MAIL_MODULE, BadgeShapeError, parse_badges
from .iserv.school_calendar import problem_text, read_calendar, source_kind
from .pathpattern import path_pattern
from .iserv.dsa import (
    REGULAR_PLAN_SECONDS,
    SUBSTITUTIONS_SETTING,
    TIMETABLE_SETTING,
    DieSchulAppClient,
    SharedReads,
    note_refusal,
)
from .iserv import dsa_substitutions
from .iserv.client import (
    LOGIN_TWOFACTOR_SETUP_KEY,
    PASSWORD_UNVERIFIED,
    REFUSAL_KEYS,
    server_failure,
)
from .iserv.errors import (
    REASON_BAD_CREDENTIALS,
    REASON_RATE_LIMITED,
    REASON_TWOFACTOR_SETUP,
    REASON_UNEXPECTED,
    REASON_UNKNOWN_ACCOUNT,
    DataError,
    LoginError,
    OutageError,
    PasswordError,
    PasswordUnclearError,
    ModulePageRefusedError,
    SchoolCalendarRefusedError,
    TwoFactorError,
    status_reason,
    transport_outage,
)
from .iserv.dsa_timetable import parse_current_timetable
from .iserv.timetable import changes_format, display_rows, shown_changes
from .iserv.twofactor import parse_delete_token, parse_token_rows, recognised_token_list, token_listed
from .mapping import (
    merge_discovered_codes,
    to_display,
)
from .messenger import MessengerService
from .sign_in import SignInService, next_totp_code, sign_in_failure_reason
from .timetable_source import TimetableSources, has_lessons
from .wizard import TOKEN_NAME

MAIL_RECOUNT_ACTIONS = frozenset({"mark_seen", "set_flag", "move", "archive", "trash", "spam"})
SCHOOL_EVENTS_DAYS = 60
START_PAGE_PATH = "/iserv/"
MODULES_RECHECK_SECONDS = 60
MODULES_RECHECKED_KEY = "api.modules.rechecked"
MODULES_TOO_SOON_KEY = "api.modules.tooSoon"
DSA_API_PATH = "/iserv/dieschulapp/api/1.0"
DSA_FILE_PATH = DSA_API_PATH + "/files/{filename}"
UNKNOWN_CONNECTION_KEY = "api.connection.unknown"
SCHOOL_REQUIRED_KEY = "api.school.required"
STATUS_OK = "ok"
STATUS_AUTH_FAILED = "auth_failed"
STATUS_NETWORK = "network"
STATUS_OUTAGE = "outage"
STATUS_NOT_CONFIGURED = "not_configured"
STATUS_PENDING = "pending"
HEALTH_STALE_AFTER_SECONDS = 5 * 60
HEALTH_CHECK_TIMEOUT_SECONDS = 5
REPAIR_REFUSAL_KEYS = dict(
    REFUSAL_KEYS,
    **{REASON_TWOFACTOR_SETUP: LOGIN_TWOFACTOR_SETUP_KEY, lockout.LOCKED: lockout.human_message_key(lockout.LOCKED)},
)
PASSWORD_UNCLEAR = "unclear"
PASSWORD_NOT_ARRIVED = "not_arrived"
REPAIR_COUNTED_REFUSALS = (REASON_BAD_CREDENTIALS, REASON_UNKNOWN_ACCOUNT, lockout.LOCKED)
UPSTREAM_ERRORS = (LoginError, TwoFactorError, DataError, requests.RequestException)
TIMETABLE_UNREADABLE_KEY = "api.timetable.unreadable"
COURSES_SAVED_KEY = "api.courses.saved"
COURSES_RESET_KEY = "api.courses.reset"


DISCONNECT_REMOVED_KEY = "api.disconnect.removed"
DISCONNECT_FAILED_KEY = "api.disconnect.failed"
DISCONNECT_FORCED_KEY = "api.disconnect.forced"
DISCONNECT_NO_TOKEN_KEY = "api.disconnect.noToken"
DISCONNECT_CHOOSE_KEY = "api.disconnect.choose"
DISCONNECT_UNREADABLE_KEY = "api.disconnect.unreadable"
DISCONNECT_UNCLEAR_KEY = "api.disconnect.unclear"


def _disconnect_result(attempted, removed, key, retryable=False, **extra):
    body = {"attempted": attempted, "removed": removed, "retryable": retryable}
    body.update(messages.payload(key))
    body.update(extra)
    return body


def _app_tokens(rows):
    return [
        {"id": row["uuid"], "name": row.get("name") or "", "created": str(row.get("created") or "")}
        for row in rows
        if row.get("name") == TOKEN_NAME and row.get("uuid")
    ]


def _token_rows_readable(html, rows):
    listed = BeautifulSoup(html or "", "html.parser").select("tbody tr")
    return len(listed) == len(rows)


def _sign_in_state(name):
    return property(
        lambda self: getattr(self._sign_in, name),
        lambda self, value: setattr(self._sign_in, name, value),
    )


def _auth_health(reason):
    return {"status": STATUS_AUTH_FAILED, "stale": False, "reason": reason}


class ConnectionService:
    _client = property(lambda self: self._sign_in._client)
    _last_code = _sign_in_state("_last_code")
    _session_lock = _sign_in_state("_session_lock")
    _expiry_window = _sign_in_state("_expiry_window")

    def __init__(self, store, client_factory=None):
        self.store = store
        self.id = str(getattr(store, "id", "") or "")
        self.client_factory = client_factory or (lambda url: IServClient(url))
        self._sign_in = SignInService(self)
        self._messenger_service = None
        self._mail_service = None
        self._mail_web = None
        self._mail_lock = threading.Lock()
        self._file_service = None
        self._contacts_service = None
        self._absence_service = None
        self._absence_lock = threading.Lock()
        self._timetable_page_denied = False
        self._child_list_state = ""
        self._settings_cache = (0.0, None)
        self._modules_recheck_at = 0.0
        self._refusals = Refusals(lambda: self.clock())
        self._calendar_source_notes = {}
        self._letter_service = LetterService(self)
        self._conference_service = ConferenceService(self)
        self._task_service = TaskService(self)
        self._news_sections = NewsSections(self)
        self._forum_service = ForumService(self)
        self._text_reader = account_lists.TextReader()
        self._child_service = ChildService(self)
        self._timetable_sources = TimetableSources(self)
        self.clock = time.time
        self._shared_reads = SharedReads(lambda: self.clock())
        self._regular_plans = SharedReads(lambda: self.clock(), seconds=REGULAR_PLAN_SECONDS)

    def is_configured(self):
        config = self.store.load_config()
        secrets = self.store.load_secrets()
        return bool(config.get("school_url")) and bool(secrets.get("username")) and bool(config.get("setup_complete"))

    def display_name(self):
        return connection_display_name(self.store.load_config())

    def child_key(self, child_id):
        return f"{self.id}:{child_id}"

    def stored_children(self):
        return self._child_service.stored_children()

    def authorized_child(self, child_id):
        return self._child_service.authorized_child(child_id)

    def _login(self, timeout=None):
        return self._sign_in._login(timeout)

    def session_not_opened_held(self):
        return self._sign_in.session_not_opened_held()

    def code_refused_since_sign_in(self):
        return self._sign_in.code_refused_since_sign_in()

    def code_refusal_needs_setup(self):
        return self._sign_in.code_refusal_needs_setup()

    def code_repair_announced(self):
        return self._sign_in.code_repair_announced()

    def note_code_repair_announced(self):
        return self._sign_in.note_code_repair_announced()

    def _outage_hold(self, now):
        reader = getattr(self.store, "load_integration_state", None)
        slot = reader() if callable(reader) else {}
        left = integration.outage_wait_left(slot, now)
        if not left:
            return None
        return OutageError(slot.get(integration.OUTAGE_REASON) or REASON_UNEXPECTED, retry_after=left)

    def _release_login_hold(self, fingerprint):
        return self._sign_in._release_login_hold(fingerprint)

    def _detect_modules(self, client):
        if not callable(getattr(client, "fetch", None)):
            return
        try:
            self._store_registry(self._probe_modules(client))
        except Exception:
            logger.debug("module detection failed", exc_info=True)

    def _probe_modules(self, client):
        try:
            page = client.fetch(START_PAGE_PATH)
        except OutageError:
            raise
        except requests.RequestException as error:
            raise transport_outage(error) from error
        status = int(getattr(page, "status_code", 0) or 0)
        if status >= 500:
            raise OutageError(status_reason(status))
        html = getattr(page, "text", "") if status == 200 else ""
        login_html = str(getattr(client, "login_page", "") or "")
        return modules.detect(
            html,
            self._probing_fetch(client),
            self.store.load_modules(),
            clock=self.clock,
            login_html=login_html,
            school_app_timetable=not self.school_app_timetable_withheld(),
            ledger=self._refusals,
        )

    def _probing_fetch(self, client):
        live = getattr(client, "fetch_live", None)
        keep = getattr(client, "fetch_and_keep", None)
        if not callable(live) or not callable(keep):
            return client.fetch

        def fetch(path, params=None):
            if path.startswith(modules.DSA_API):
                response = live(path, params)
                note_refusal(self._refusals, path, response, params)
                return response
            return keep(path, params)

        return fetch

    def school_app_timetable_withheld(self):
        try:
            settings = self._school_settings()
        except Exception:
            logger.debug("timetable availability lookup failed", exc_info=True)
            return False
        return settings.get(TIMETABLE_SETTING, True) is False

    def _store_registry(self, registry):
        def change(slot):
            previous = dict(slot)
            if modules.changed(previous if previous else None, registry):
                logger.info("school#%s %s", self.id, modules.summary(registry))
            slot.clear()
            slot.update(modules.with_history(previous, registry))

        edit_slot(self.store, "modules", change)

    def modules(self):
        stored = self.store.load_modules()
        registry = modules.normalize(stored if stored else None)
        if self._timetable_page_denied and not self._school_app_timetable_usable(registry):
            registry["modules"][modules.TIMETABLE] = False
        return registry

    def _school_app_timetable_usable(self, registry):
        return modules.school_app_timetable_served(registry) and self._child_service.course_ids_known()

    def stored_modules(self):
        stored = self.store.load_modules()
        return modules.normalize(stored if stored else None)

    def module_available(self, name):
        return self.modules()["modules"].get(name, True)

    def refresh_modules(self):
        if self._client is None or not self._client.is_authenticated():
            self._login()
            return self.modules()
        if callable(getattr(self._client, "fetch", None)):
            self._store_registry(self._probe_modules(self._client))
        return self.modules()

    def recheck_modules(self, clock=time.time):
        now = clock()
        if now - self._modules_recheck_at < MODULES_RECHECK_SECONDS:
            return messages.result(False, MODULES_TOO_SOON_KEY, error="rate_limited", modules=self.modules())
        self._modules_recheck_at = now
        self._refusals.clear()
        registry = self.refresh_modules()
        return messages.result(True, MODULES_RECHECKED_KEY, modules=registry)

    def _session(self):
        return self._sign_in._session()

    def iserv_session(self):
        return self._session()

    def _trust_school_app(self):
        return self._sign_in._trust_school_app()

    def _forget_session(self, client):
        return self._sign_in._forget_session(client)

    def signed_in_session(self):
        client = self._client
        return client if client is not None and client.is_authenticated() else None

    def me_if_signed_in(self):
        return self.me() if self.signed_in_session() is not None else None

    def _messenger(self):
        if self._messenger_service is None:
            self._messenger_service = MessengerService(self)
        return self._messenger_service

    def messenger_rooms(self):
        return self._messenger().rooms()

    def messenger_room_messages(self, room_id, before=None):
        return self._messenger().room_messages(room_id, before)

    def messenger_send(self, room_id, text, txn_id=""):
        return self._messenger().send_message(room_id, text, txn_id)

    def messenger_media(self, server_name, media_id):
        return self._messenger().media(server_name, media_id)

    def messenger_mark_read(self, room_id, event_id):
        return self._messenger().mark_room_read(room_id, event_id)

    def messenger_teacher_search(self, query):
        return self._messenger().search_teachers(query)

    def messenger_teacher_room_children(self):
        return self._messenger().teacher_room_children()

    def messenger_create_teacher_room(self, teacher, child_ids, add_other_parents):
        return self._messenger().create_teacher_room(teacher, child_ids, add_other_parents)

    def messenger_unread_pulse(self):
        return self._messenger().unread_pulse()

    def _noted_outage(self):
        reader = getattr(self.store, "load_integration_state", None)
        slot = reader() if callable(reader) else {}
        return bool(isinstance(slot, dict) and slot.get(integration.OUTAGE_SINCE))

    def _session_status(self):
        if not self._noted_outage():
            return "ok"
        try:
            page = self._client.fetch(START_PAGE_PATH)
        except requests.RequestException:
            return STATUS_OUTAGE
        return STATUS_OUTAGE if int(getattr(page, "status_code", 0) or 0) >= 500 else "ok"

    def check_connection(self):
        if not self.is_configured():
            return "not_configured"
        if self._client is not None and self._client.is_authenticated():
            return self._session_status()
        with self._session_lock:
            try:
                self._login()
            except (LoginError, TwoFactorError):
                self._sign_in.drop_session()
                return "auth_failed"
            except OutageError:
                self._sign_in.drop_session()
                return STATUS_OUTAGE
            except requests.RequestException:
                self._sign_in.drop_session()
                return "network"
            except NotConfiguredError:
                return "not_configured"
        return "ok"

    def _stored_status(self, slot):
        if slot.get(integration.OUTAGE_SINCE):
            return STATUS_OUTAGE
        if slot.get("last_poll_ok"):
            return STATUS_OK
        error = str(slot.get("last_error") or "")
        if error in (STATUS_AUTH_FAILED, STATUS_NETWORK, STATUS_OUTAGE):
            return error
        return STATUS_NETWORK

    def health_status(self, clock=time.time):
        if not self.is_configured():
            return {"status": STATUS_NOT_CONFIGURED, "stale": False}
        slot = self.store.load_integration_state()
        last_poll = slot.get("last_poll")
        last_poll = int(last_poll) if isinstance(last_poll, (int, float)) and not isinstance(last_poll, bool) else 0
        if last_poll and clock() - last_poll < HEALTH_STALE_AFTER_SECONDS:
            status = self._stored_status(slot)
            if status == STATUS_AUTH_FAILED:
                return _auth_health(slot.get(integration.AUTH_REASON) or REASON_BAD_CREDENTIALS)
            return {"status": status, "stale": False}
        if self._outage_hold(clock()) is not None:
            return {"status": STATUS_OUTAGE, "stale": False}
        if self._client is not None and self._client.is_authenticated():
            return {"status": self._session_status(), "stale": False}
        with self._session_lock:
            try:
                self._login(timeout=HEALTH_CHECK_TIMEOUT_SECONDS)
            except (LoginError, TwoFactorError) as error:
                self._sign_in.drop_session()
                return _auth_health(sign_in_failure_reason(error))
            except OutageError:
                self._sign_in.drop_session()
                return {"status": STATUS_OUTAGE, "stale": False}
            except NotConfiguredError:
                return {"status": STATUS_NOT_CONFIGURED, "stale": False}
            except requests.Timeout:
                self._sign_in.drop_session()
                return {"status": self._stored_status(slot), "stale": True}
            except requests.RequestException:
                self._sign_in.drop_session()
                return {"status": STATUS_NETWORK, "stale": False}
        return {"status": STATUS_OK, "stale": False}

    def change_password(self, current, new):
        client = self._session()
        try:
            client.change_password(current, new)
        except PasswordUnclearError:
            return self._password_after_lost_answer(client, new)
        except PasswordError as error:
            if str(error) == PASSWORD_UNVERIFIED:
                self._store_password(new)
                return "unverified"
            raise
        self._store_password(new)
        return True

    def _password_after_lost_answer(self, client, new):
        url = self.store.load_config().get("school_url", "")
        pause = self._repair_pause(url)
        if signin_pause.is_paused(pause, self.clock()):
            logger.warning("the password change answer was lost; the sign-in pause holds the check back")
            return PASSWORD_UNCLEAR
        accepted = client.accepts_password(new)
        refusal = getattr(client, "refusal", "") or (REASON_BAD_CREDENTIALS if accepted is False else "")
        if refusal in REPAIR_COUNTED_REFUSALS:
            self._save_repair_pause(url, signin_pause.register_failure(pause, refusal, self.clock()))
        if accepted is True:
            logger.info("the password change answer was lost, the new password signs in")
            self._store_password(new)
            return True
        if accepted is False:
            logger.warning("the password change answer was lost, the new password does not sign in")
            return PASSWORD_NOT_ARRIVED
        logger.warning("the password change answer was lost and the check got no answer")
        return PASSWORD_UNCLEAR

    def repair_password(self, password):
        config = self.store.load_config()
        secrets = self.store.load_secrets()
        url = config.get("school_url", "")
        username = secrets.get("username", "")
        if not url or not username:
            raise NotConfiguredError("school url or credentials missing")
        held = self._outage_hold(self.clock())
        if held is not None and held.reason == REASON_RATE_LIMITED:
            return messages.result(False, signin_pause.PAUSE_MESSAGES[signin_pause.RATE_LIMITED], retry_in=held.retry_after)
        pause = self._repair_pause(url)
        if signin_pause.is_paused(pause, self.clock()):
            return self._repair_paused(pause)
        client = requestlog.tag_school(self.client_factory(url), self.id)
        client.username = username
        accepted = client.accepts_password(password)
        refusal = getattr(client, "refusal", "") or (REASON_BAD_CREDENTIALS if accepted is False else "")
        if refusal in REPAIR_COUNTED_REFUSALS:
            pause = signin_pause.register_failure(pause, refusal, self.clock())
            self._save_repair_pause(url, pause)
            if signin_pause.is_paused(pause, self.clock()):
                return self._repair_paused(pause)
        if refusal in REPAIR_REFUSAL_KEYS and refusal != REASON_BAD_CREDENTIALS:
            return messages.result(False, REPAIR_REFUSAL_KEYS[refusal])
        if accepted is False:
            return messages.result(False, "api.repair.rejected")
        if accepted is None:
            answered = getattr(client, "answered", False) is True
            return messages.result(False, "api.repair.unexpected" if answered else "api.repair.unreachable")
        self._save_repair_pause(url, None)
        self._store_password(password)
        return messages.result(True, "api.repair.ok")

    def _repair_pause(self, url):
        reader = getattr(self.store, "load_wizard", None)
        state = reader() if callable(reader) else {}
        pauses = signin_pause.live_pauses(state.get(PAUSES) if isinstance(state, dict) else {}, self.clock())
        return signin_pause.entry_of(pauses, url)

    def _save_repair_pause(self, url, entry):
        reader = getattr(self.store, "load_wizard", None)
        writer = getattr(self.store, "save_wizard", None)
        if not callable(reader) or not callable(writer):
            return
        state = reader()
        pauses = dict(state.get(PAUSES) or {})
        if entry:
            pauses[url] = entry
        elif url in pauses:
            pauses.pop(url)
        else:
            return
        if pauses:
            state[PAUSES] = pauses
        else:
            state.pop(PAUSES, None)
        writer(state)

    def _repair_paused(self, pause):
        left = signin_pause.seconds_left(pause, self.clock())
        return messages.result(False, signin_pause.message_key(pause), retry_in=left)

    def _store_password(self, password):
        def store(secrets):
            secrets["password"] = password
            secrets.pop(LOGIN_HOLD, None)

        with self._session_lock:
            edit_secrets(self.store, store)
            self._sign_in.drop_session()

    def disconnect(self, force=False, token_id=None):
        secrets = self.store.load_secrets()
        if not secrets.get("totp_secret"):
            iserv_result = _disconnect_result(False, True, DISCONNECT_NO_TOKEN_KEY)
        else:
            iserv_result = self._remove_iserv_token(secrets, token_id)
        if not iserv_result["removed"] and force is not True:
            logger.warning("the school stays connected: its two-factor token is still in IServ")
            iserv_result["disconnected"] = False
            return iserv_result
        if not iserv_result["removed"]:
            logger.warning("the school was disconnected although its two-factor token is still in IServ")
            iserv_result.update(messages.payload(DISCONNECT_FORCED_KEY))
        self._clear_local_data()
        iserv_result["disconnected"] = True
        return iserv_result

    def _remove_iserv_token(self, secrets, token_id=None):
        uuid = secrets.get("twofactor_uuid")
        try:
            client = self._session()
            list_page = client.get_twofactor_list_page()
            csrf_token = parse_delete_token(list_page.text)
            if not csrf_token:
                logger.warning("removing the two-factor token failed: the token list was not readable")
                return _disconnect_result(True, False, DISCONNECT_FAILED_KEY, True)
            if not uuid:
                rows = parse_token_rows(list_page.text)
                if not _token_rows_readable(list_page.text, rows):
                    logger.warning("removing the two-factor token refused: the token list rows were not readable")
                    return _disconnect_result(True, False, DISCONNECT_UNREADABLE_KEY, True)
                tokens = _app_tokens(rows)
                if not tokens:
                    logger.info("no two-factor token of the app is listed in IServ")
                    return _disconnect_result(True, True, DISCONNECT_NO_TOKEN_KEY)
                if token_id not in [token["id"] for token in tokens]:
                    logger.warning("removing the two-factor token waits for a choice: %d tokens carry the name of the app", len(tokens))
                    return _disconnect_result(False, False, DISCONNECT_CHOOSE_KEY, tokens=tokens)
                uuid = token_id
            else:
                rows = recognised_token_list(list_page.text)
                if rows is None:
                    logger.warning("removing the two-factor token refused: the token list was not recognised")
                    return _disconnect_result(True, False, DISCONNECT_UNREADABLE_KEY, True)
                if not token_listed(list_page.text, rows, uuid):
                    logger.info("the two-factor token of the app is no longer listed in IServ")
                    return _disconnect_result(True, True, DISCONNECT_REMOVED_KEY)
            code = next_totp_code(secrets["totp_secret"], self._last_code)
            removed = client.delete_totp_token(uuid, code, csrf_token)
        except DataError as error:
            if error.message_key == DISCONNECT_UNCLEAR_KEY:
                logger.warning("removing the two-factor token is unclear: the token list was not recognised afterwards")
                return _disconnect_result(True, False, DISCONNECT_UNCLEAR_KEY, True)
            logger.warning("removing the two-factor token could not be confirmed: %s", failure_cause(error))
            return _disconnect_result(True, False, DISCONNECT_FAILED_KEY, True)
        except (NotConfiguredError, LoginError, TwoFactorError, requests.RequestException) as error:
            logger.warning("removing the two-factor token could not be confirmed: %s", failure_cause(error))
            return _disconnect_result(True, False, DISCONNECT_FAILED_KEY, True)
        if not removed:
            logger.warning("removing the two-factor token failed: IServ still lists it")
        return _disconnect_result(True, removed, DISCONNECT_REMOVED_KEY if removed else DISCONNECT_FAILED_KEY, not removed)

    def _clear_local_data(self):
        with self._session_lock:
            self._child_service.retire()
            self._letter_service.forget_listed()
            self._conference_service.forget()
            self.store.reset_config()
            self.store.delete_secrets()
            self._sign_in.drop_session()
            self._messenger_service = None
            self._mail_service = None
            self._mail_web = None
            self._file_service = None
            self._contacts_service = None
            self._absence_service = None
            self._child_service = ChildService(self)
            self._timetable_sources.reset()
            self._regular_plans.clear()

    def children(self):
        try:
            listed = self._child_service.children()
        except DataError as error:
            self._note_child_list_state(child_list_state(error))
            raise
        self._note_child_list_state(CHILDREN_LISTED)
        return listed

    def _note_child_list_state(self, state):
        self._child_list_state = state
        if self.store.load_config().get(CHILDREN_STATE_KEY) != state:
            edit_config(self.store, lambda config: config.update({CHILDREN_STATE_KEY: state}))

    def child_list_state(self):
        return self._child_list_state or str(self.store.load_config().get(CHILDREN_STATE_KEY) or "")

    def _cached_child(self, child_id):
        return self._child_service._cached_child(child_id)

    def listed_child_count(self):
        return self._child_service.listed_count(refresh=True)

    def _migrate_stored_children(self, children):
        return self._child_service._migrate_stored_children(children)

    def _school_settings(self):
        stamp, cached = self._settings_cache
        if cached is not None and time.time() - stamp <= SCHOOL_CACHE_SECONDS:
            return cached
        settings = self._dsa().school_settings()
        self._settings_cache = (time.time(), settings)
        return settings

    def _substitutions_released(self):
        try:
            value = self._school_settings().get(SUBSTITUTIONS_SETTING)
        except Exception:
            logger.debug("school settings lookup failed", exc_info=True)
            return None
        return value if isinstance(value, bool) else None

    def _school_timetable(self, target, course_ids):
        school_app = self._dsa()
        released = self._substitutions_released() is True
        payload = school_app.current_timetable(target, course_ids, substitutions=released)
        if payload is None:
            raise DataError(
                "timetable was not readable",
                message_key=TIMETABLE_UNREADABLE_KEY,
                detail={"source": "school-app", "date": target.isoformat(), "status": school_app.last_status},
            )
        week = parse_current_timetable(payload, target)
        regular, failure = self._regular_timetable(school_app, target, course_ids, payload) if released else (dsa_substitutions.NOT_ASKED, "")
        week.substitutions = dsa_substitutions.mark(week, payload, regular, target, failure)
        return week

    @staticmethod
    def _regular_timetable(school_app, target, course_ids, current):
        try:
            regular = school_app.regular_timetable(target, course_ids, current)
        except OutageError as error:
            if error.reason == REASON_RATE_LIMITED:
                raise
            return None, type(error).__name__
        except Exception as error:
            return None, type(error).__name__
        if regular is None:
            return None, "answer %s" % (getattr(school_app, "last_status", 0) or "-")
        return regular, ""

    def _dsa(self):
        client = self._session()
        return DieSchulAppClient(
            client.base_url,
            client.session,
            on_expired=lambda: self._forget_session(client),
            on_answered=self._trust_school_app,
            shared=self._shared_reads,
            regular_plans=self._regular_plans,
            refusals=self._refusals,
        )

    def school_profile(self):
        return self._dsa().school()

    def pinboard(self):
        boards = self._dsa().pinboards_or_raise()

        def initialise(seen_state):
            if seen_state.get("pinboard_initialised"):
                return
            known = set(seen_state.get("pinboard", []))
            for board in boards:
                for column in board.columns:
                    for tile in column.tiles:
                        known.add(tile.id)
            seen_state["pinboard"] = sorted(known)
            seen_state["pinboard_initialised"] = True

        seen = set(edit_slot(self.store, "seen", initialise).get("pinboard", []))
        folders = []
        feed = []
        for board in boards:
            unread_count = 0
            columns = []
            last_post_id = None
            for column in board.columns:
                tiles = []
                for tile in column.tiles:
                    is_unread = tile.id not in seen
                    if is_unread:
                        unread_count += 1
                    if tile.id is not None and (last_post_id is None or tile.id > last_post_id):
                        last_post_id = tile.id
                    entry = {
                        "id": tile.id,
                        "title": tile.title,
                        "text": tile.text,
                        "color": tile.color,
                        "owner": tile.owner,
                        "folder_id": board.id,
                        "folder_title": board.title,
                        "column_title": column.title,
                        "unread": is_unread,
                        "attachments": [attachment_dict(a, self.id) for a in tile.attachments],
                    }
                    tiles.append(entry)
                    feed.append(entry)
                columns.append({"id": column.id, "title": column.title, "tiles": tiles})
            folders.append(
                {
                    "id": board.id,
                    "title": board.title,
                    "unread": unread_count,
                    "last_post_id": last_post_id,
                    "columns": columns,
                    "attachments": [attachment_dict(a, self.id) for a in board.attachments],
                    "author": board.author,
                    "students_can_create_tiles": board.students_can_create_tiles,
                }
            )
        folders.sort(key=lambda entry: folder_sort_key(entry.get("last_post_id"), entry.get("title")))
        feed.sort(key=lambda entry: entry["id"] or 0, reverse=True)
        return {"folders": folders, "feed": feed}

    def pinboard_attachment(self, filename):
        filename = clean_filename(filename)
        return school_lists.read_school_file(self._session(), DSA_FILE_PATH.format(filename=quote(filename, safe="")), self._school_url())

    def absence_attachment(self, filename):
        return self._absences().absence_attachment(filename)

    def mark_pinboard_seen(self, tile_ids=None, mark_all=False, unseen=False):
        listed = []
        if mark_all:
            for board in self._dsa().pinboards():
                for column in board.columns:
                    listed.extend(tile.id for tile in column.tiles)

        def change(seen):
            current = set(seen.get("pinboard", []))
            if mark_all:
                current.update(listed)
            elif unseen:
                current.difference_update(tile_ids or [])
            else:
                current.update(tile_ids or [])
            seen["pinboard"] = sorted(current)

        return {"seen": len(edit_slot(self.store, "seen", change)["pinboard"])}

    def _letters(self):
        return self._letter_service

    def letters(self, tab="current"):
        return self._letters().letters(tab)

    def mark_letters_read(self, keys=None, mark_all=False):
        return self._letters().mark_letters_read(keys, mark_all)

    def letter_detail(self, letter_id, recipient_id):
        return self._letters().letter_detail(letter_id, recipient_id)

    def confirm_letter(self, letter_id, recipient_id, text=None, choices=None):
        return self._letters().confirm_letter(letter_id, recipient_id, text, choices)

    def answer_form(self, letter_id, recipient_id):
        return self._letters().answer_form(letter_id, recipient_id)

    def edit_answer(self, letter_id, recipient_id, text=None, choices=None):
        return self._letters().edit_answer(letter_id, recipient_id, text, choices)

    def reply_to_letter(self, letter_id, recipient_id, text, request_id, confirmed=False):
        return self._letters().reply_to_letter(letter_id, recipient_id, text, request_id, confirmed)

    def archive_letter(self, letter_id, recipient_id):
        return self._letters().archive_letter(letter_id, recipient_id)

    def restore_letter(self, letter_id, recipient_id):
        return self._letters().restore_letter(letter_id, recipient_id)

    def letter_attachment(self, attachment_id):
        return self._letters().letter_attachment(attachment_id)

    def me(self):
        data = self._dsa()._get("users/me") or {}
        if not isinstance(data, dict):
            return {}
        school = data.get("school")
        school = school if isinstance(school, dict) else {}
        address = ", ".join(
            part
            for part in (school.get("street"), school.get("zip"), school.get("town"), school.get("country"))
            if part
        )
        return {
            "forename": str(data.get("forename") or "").strip(),
            "displayname": str(data.get("displayname") or "").strip(),
            "id": data.get("id"),
            "surname": str(data.get("surname") or "").strip(),
            "username": str(data.get("username") or "").strip(),
            "email": str(data.get("email") or "").strip(),
            "external_id": data.get("externalId"),
            "is_active": data.get("isActive"),
            "is_activated": data.get("isActivated"),
            "needs_re_registration": data.get("needsReRegistration"),
            "in_preparation": data.get("inPreparation"),
            "is_web_user": data.get("isWebUser"),
            "is_guardian": data.get("isGuardian"),
            "is_main_teacher": data.get("isMainTeacher"),
            "roles": data.get("roles") or [],
            "is_notified_by_email": data.get("isNotifiedByEmail"),
            "is_receiver_of_serial_print": data.get("isReceiverOfSerialPrint"),
            "is_newsletter_receiver": data.get("isNewsletterReceiver"),
            "has_active_devices": data.get("hasActiveDevices"),
            "has_2nd_factor_active": data.get("has2ndFactorActive"),
            "has_restricted_access_pin": data.get("hasRestrictedAccessPin"),
            "created_at": data.get("createdAt"),
            "updated_at": data.get("updatedAt"),
            "school_name": str(school.get("name") or "").strip(),
            "school_address": address,
        }

    def read_school_calendar(self, first, last):
        read = read_calendar(self._session(), first, last, server_failure)
        self._note_calendar_sources(read.problems)
        return read

    def school_events(self, first, last):
        return self.read_school_calendar(first, last).events

    def _note_calendar_sources(self, problems):
        notes = {}
        for problem in problems:
            text = "%s %s not read: %s" % (source_kind(problem.kind), path_pattern(problem.path) or "-", problem_text(problem.reason))
            notes[problem.source] = text
            if self._calendar_source_notes.get(problem.source) != text:
                logger.info("school#%s calendar source %s", self.id, text)
        self._calendar_source_notes = notes

    def _school_url(self):
        return self.store.load_config().get("school_url", "")

    def tasks(self):
        return school_lists.read_tasks(self._session())

    def news(self):
        return school_lists.read_news(self._session())

    def forums(self):
        return account_lists.read_forums(self._session())

    def texts(self):
        return self._text_reader.read(self._session())

    def infodisplay(self):
        return account_lists.read_screens(self._session())

    def forum_mark_read(self, confirmed=False):
        return self._forum_service.mark_all_read(confirmed)

    def task_detail(self, task_id):
        return self._task_service.detail(task_id)

    def task_file(self, task_id, kind, index):
        return self._task_service.file(task_id, kind, index)

    def task_act(self, task_id, action, form_id, target=None, text=None, files=None, confirmed=False):
        return self._task_service.act(task_id, action, form_id, target, text, files, confirmed)

    def news_detail(self, path, title=""):
        return school_lists.read_news_detail(self._session(), self._school_url(), path, title)

    def news_section(self, section):
        return self._news_sections.items(section)

    def news_section_detail(self, section, item_id):
        return self._news_sections.detail(section, item_id)

    def news_file(self, item_id, kind, index, section=""):
        if section:
            path = self._news_sections.file_path(section, item_id, kind, index)
        else:
            stored = school_lists.stored_list(self.store, self.id, school_lists.NEWS_FIELD)
            path = school_lists.news_file_path((stored or {}).get(school_lists.NEWS_FIELD), item_id, kind, index)
        if not path:
            raise DataError("unknown news file")
        return school_lists.read_school_file(self._session(), path, self._school_url())

    def badges(self):
        response = self._session().fetch_or_raise(BADGES_PATH)
        try:
            return parse_badges(response.json())
        except (ValueError, BadgeShapeError) as error:
            raise DataError("navigation badges unreadable", detail={"path": BADGES_PATH}) from error

    def mail_available(self):
        return modules.lists_module(self.stored_modules(), MAIL_MODULE)

    def mail(self):
        if not self.mail_available():
            raise MailNotOffered()
        with self._mail_lock:
            if self._mail_service is None:
                self._mail_service = MailService(self)
            return self._mail_service

    def mail_web(self):
        if not self.mail_available():
            raise MailNotOffered()
        with self._mail_lock:
            if self._mail_web is None:
                self._mail_web = MailWebService(self)
            return self._mail_web

    def account_modules(self):
        registry = self.stored_modules()
        return {slug: modules.lists_module(registry, slug) for slug in modules.LISTED_MODULES}

    def files(self):
        if not self.account_modules()[modules.FILES]:
            raise AccountModuleNotOffered()
        with self._mail_lock:
            if self._file_service is None:
                self._file_service = FileService(self)
            return self._file_service

    def contacts(self, slug):
        if not self.account_modules().get(slug):
            raise AccountModuleNotOffered()
        with self._mail_lock:
            if self._contacts_service is None:
                self._contacts_service = ContactsService(self)
            return self._contacts_service

    def mail_badge(self):
        try:
            return self.badges().get(MAIL_BADGE, 0)
        except UPSTREAM_ERRORS as error:
            logger.info("school#%s mail count not read again after a read mark: %s", self.id, failure_cause(error))
            return None

    def conferences(self, tab=CONFERENCE_TAB_CURRENT):
        return self._conference_service.conferences(tab)

    def conference_page(self, page):
        return self._conference_service.page(page)

    def submit_conference_form(self, page, form, check, submit, values, request_id="", confirmed=False):
        return self._conference_service.submit(page, form, check, submit, values, request_id, confirmed)

    def timetable_available(self):
        return self.module_available(modules.TIMETABLE)

    def _absences(self):
        with self._absence_lock:
            if self._absence_service is None:
                self._absence_service = AbsenceService(self)
            return self._absence_service

    def absences_overview(self):
        return self._absences().absences_overview()

    def older_absence_form(self):
        return self._absences().older_absence_form()

    def older_absence_detail(self, entry_id):
        return self._absences().older_absence_detail(entry_id)

    def older_absence_attachment(self, entry_id, key):
        return self._absences().older_absence_attachment(entry_id, key)

    def attach_older_absence(self, entry_id, upload):
        return self._absences().attach_older_absence(entry_id, upload)

    def delete_older_attachment(self, entry_id, key):
        return self._absences().delete_older_attachment(entry_id, key)

    def older_absence_export(self):
        return self._absences().older_absence_export()

    def report_absence(self, payload, attachments=None):
        return self._absences().report_absence(payload, attachments)

    def delete_absence(self, payload):
        return self._absences().delete_absence(payload)

    def sick_note_pdf(self, sick_note_id):
        return self._absences().sick_note_pdf(sick_note_id)

    def _school_period_times(self):
        try:
            return self._dsa().period_times() or {}
        except Exception:
            logger.debug("dsa period times lookup failed", exc_info=True)
            return {}

    def _school_period_slots(self):
        try:
            reader = getattr(self._dsa(), "period_slots", None)
        except Exception:
            reader = None
        if not callable(reader):
            return self._school_period_times()
        try:
            return reader() or {}
        except Exception:
            logger.debug("dsa period slots lookup failed", exc_info=True)
            return {}

    def _merge_period_times(self, config, discovered):
        return period_grid.merge_iserv(config, discovered)

    def timetable(self, child_id, reference=None, week_offset=0):
        payload, config = self._timetable_payload(child_id, reference, week_offset)
        shown = courses.apply(payload, courses.filter_of(config, child_id))
        if payload.get("week_offset") == 0:
            lessons = shown.get("lessons") or []
            vacations = payload.get("vacations") or []
            edit_config(self.store, lambda current: current.update(period_grid.merge_profile(current, str(child_id), lessons, vacations)))
        return shown

    def timetable_courses(self, child_id, reference=None):
        payload, config = self._timetable_payload(child_id, reference, 0)
        lessons = list(payload["lessons"])
        try:
            upcoming, config = self._timetable_payload(child_id, reference, 1)
        except Exception:
            logger.debug("next week was not readable for the course list", exc_info=True)
        else:
            lessons.extend(upcoming["lessons"])
        return courses.catalogue(lessons, courses.filter_of(config, child_id), config)

    def save_course_filter(self, child_id, chosen, known, confirmed_empty=False):
        value = None if chosen is None else {"chosen": chosen, "known": known}
        if value is not None and confirmed_empty:
            value[courses.CONFIRMED_EMPTY_KEY] = True
        config = edit_config(self.store, lambda current: current.update(courses.with_filter(current, child_id, value)))
        stored = courses.filter_of(config, child_id)
        key = COURSES_SAVED_KEY if stored is not None else COURSES_RESET_KEY
        return messages.result(True, key, chosen=len(stored["chosen"]) if stored else 0)

    def _timetable_payload(self, child_id, reference=None, week_offset=0):
        if str(child_id).startswith(LETTERS_CHILD_PREFIX):
            raise unknown_child()
        offset = holidays.clamp_week_offset(week_offset)
        target = (reference or date.today()) + timedelta(days=7 * offset)
        child = self._cached_child(str(child_id))
        reading = self._timetable_sources.read(child_id, child, target)
        week = reading.week
        school_slots = reading.slots if reading.slots is not None else self._school_period_slots()
        school_times = {key: slot["start"] for key, slot in period_grid.normalize_slots(school_slots).items()}

        def learn(current):
            merged = merge_discovered_codes(current, week.combined + week.plain)
            current.update(self._merge_period_times(merged, school_slots))

        config = edit_config(self.store, learn)
        lessons = [
            dict(to_display(lesson, config, change), course_key=courses.regular_course_key(lesson, change))
            for lesson, change in display_rows(week)
        ]
        payload = {
            "last_updated": week.last_updated,
            "start_date": week.start_date,
            "end_date": week.end_date,
            "lessons": lessons,
            "changes": shown_changes(week),
            "changes_format": changes_format(week),
            "period_times": config.get("period_times", {}),
            "school_period_times": school_times,
            "change_count": sum(1 for entry in lessons if entry["change_kind"]),
            "week_offset": offset,
            "substitutions_released": self._substitutions_released(),
            "vacations": list(getattr(week, "vacations", None) or []),
            "source": reading.source,
            "no_lessons": not has_lessons(week),
        }
        return payload, config


def child_list_state(error):
    if getattr(error, "message_key", "") == CHILD_PAGE_FORBIDDEN_KEY:
        return CHILDREN_REFUSED
    return CHILDREN_UNREADABLE


class SchoolRequiredError(DataError):
    def __init__(self):
        super().__init__("a school must be named when several are set up", message_key=SCHOOL_REQUIRED_KEY)


def _unknown_connection():
    return DataError("unknown connection", message_key=UNKNOWN_CONNECTION_KEY)


def _split_prefixed(value):
    text = str(value or "")
    connection_id, separator, rest = text.partition(":")
    if not separator:
        return "", text
    return connection_id, rest


def _tag_media_urls(payload, connection_id):
    for message in (payload or {}).get("messages") or []:
        url = message.get("media_url") if isinstance(message, dict) else ""
        if url:
            message["media_url"] = f"{url}?connection={connection_id}"
    return payload


def _without_open_url(entry):
    return {key: value for key, value in entry.items() if key != "open_url"}


def _event_in_window(event, first, last):
    start = str(event.get("start") or "")[:10]
    end = str(event.get("end") or "")[:10] or start
    if not start:
        return False
    ends_after = end > first.isoformat() if event.get("all_day") and end != start else end >= first.isoformat()
    return ends_after and start <= last.isoformat()


def _school_letters(connection, tab):
    if not connection.module_available(modules.LETTERS):
        return {"letters": []}
    return connection.letters(tab)


class IServService:
    def __init__(self, store, client_factory=None):
        self.store = store
        self.client_factory = client_factory or (lambda url: IServClient(url))
        self._connections = {}
        self._lock = threading.Lock()

    def connection(self, connection_id, entry=None):
        connection_id = str(connection_id or "")
        entry = entry if entry is not None else (self.store.connection(connection_id) or {})
        revision = entry.get(LOGIN_REVISION_KEY, 0)
        with self._lock:
            existing = self._connections.get(connection_id)
            if existing is None or getattr(existing, "login_revision", 0) != revision:
                existing = ConnectionService(self.store.connection_store(connection_id), self.client_factory)
                existing.login_revision = revision
                self._connections[connection_id] = existing
            return existing

    def connections(self, include_pending=False):
        entries = self.store.connections()
        known = {entry["id"] for entry in entries}
        with self._lock:
            for stale in [name for name in self._connections if name not in known]:
                self._connections.pop(stale, None)
        return [
            self.connection(entry["id"], entry)
            for entry in entries
            if include_pending or entry.get("setup_complete")
        ]

    def known_connection(self, connection_id):
        connection_id = str(connection_id or "")
        if not connection_id or self.store.connection(connection_id) is None:
            raise _unknown_connection()
        return self.connection(connection_id)

    def pick_school(self, connection_id=None):
        if connection_id:
            return self.known_connection(connection_id)
        listed = self.connections()
        if not listed:
            raise NotConfiguredError("no school connected")
        if len(listed) > 1:
            raise SchoolRequiredError()
        return listed[0]

    def resolve(self, child_key):
        connection_id, child_id = split_child_key(child_key)
        if not connection_id or self.store.connection(connection_id) is None:
            raise unknown_child()
        connection = self.connection(connection_id)
        return connection, connection.authorized_child(child_id)

    def is_configured(self):
        return any(connection.is_configured() for connection in self.connections())

    def annotate(self, connection, item):
        item = dict(item)
        item["connection_id"] = connection.id
        item["school"] = connection.display_name()
        return item

    def summaries(self, with_status=False):
        rows = []
        for entry in self.store.connections():
            connection = self.connection(entry["id"])
            row = {
                "id": entry["id"],
                "name": connection_display_name(entry),
                "school_name": entry.get("school_name", ""),
                "label": entry.get("label", ""),
                "short_name": connection_short_name(entry),
                "school_url": entry.get("school_url", ""),
                "host": host_of(entry.get("school_url")),
                "setup_complete": bool(entry.get("setup_complete")),
                "username": connection.store.load_secrets().get("username", ""),
                "children": [self._child(connection, child) for child in connection.stored_children()],
                CHILDREN_STATE_KEY: connection.child_list_state(),
            }
            if with_status:
                row["status"] = connection.check_connection() if row["setup_complete"] else STATUS_PENDING
            rows.append(row)
        return rows

    def check_connection(self):
        return self._aggregate_statuses([connection.check_connection() for connection in self.connections()])

    def health_overview(self, clock=time.time):
        rows = self.summaries(with_status=False)
        statuses = []
        for row in rows:
            if not row["setup_complete"]:
                row["status"], row["stale"] = STATUS_PENDING, False
                continue
            connection = self.connection(row["id"])
            result = connection.health_status(clock=clock)
            row["status"], row["stale"] = result["status"], result["stale"]
            if result.get("reason"):
                row["reason"] = result["reason"]
            statuses.append(row["status"])
        return self._aggregate_statuses(statuses), rows

    @staticmethod
    def _aggregate_statuses(statuses):
        if not statuses:
            return STATUS_NOT_CONFIGURED
        if STATUS_OK in statuses:
            return STATUS_OK
        if all(status == STATUS_AUTH_FAILED for status in statuses):
            return STATUS_AUTH_FAILED
        if all(status == STATUS_NOT_CONFIGURED for status in statuses):
            return STATUS_NOT_CONFIGURED
        if all(status == STATUS_OUTAGE for status in statuses):
            return STATUS_OUTAGE
        return STATUS_NETWORK

    def children(self, connection_id=None):
        if connection_id:
            connection, raw = self._children_of(self.known_connection(connection_id))
            return [self._child(connection, child) for child in raw]
        listed = []
        failures = []
        connections = self.connections()
        for connection in connections:
            try:
                connection, raw = self._children_of(connection)
            except (NotConfiguredError,) + UPSTREAM_ERRORS as error:
                failures.append(error)
                if child_list_state(error) == CHILDREN_REFUSED:
                    logger.info("child list of school#%s refused for this account", connection.id)
                else:
                    logger.warning("child list of school#%s unavailable: %s", connection.id, failure_cause(error))
                raw = [dict(child, unavailable=True) for child in connection.stored_children()]
            listed.extend(self._child(connection, child) for child in raw)
        if failures and not listed:
            raise failures[0]
        if failures and len(failures) == len(connections) and not all(isinstance(failure, OutageError) for failure in failures):
            raise failures[0]
        listed.sort(key=child_sort_key)
        return listed

    def _children_of(self, connection):
        try:
            return connection, connection.children()
        except ConnectionChangedError:
            entry = self.store.connection(connection.id)
            if entry is None:
                raise
            fresh = self.connection(connection.id, entry)
            return fresh, fresh.children()

    def _child(self, connection, child):
        item = self.annotate(connection, child)
        item["key"] = connection.child_key(str(child.get("child_id") or ""))
        return item

    def timetable(self, child_key, reference=None, week_offset=0):
        connection, child_id = self.resolve(child_key)
        return connection.timetable(child_id, reference, week_offset)

    def timetable_courses(self, child_key, reference=None):
        connection, child_id = self.resolve(child_key)
        return connection.timetable_courses(child_id, reference)

    def save_course_filter(self, child_key, chosen, known, confirmed_empty=False):
        connection, child_id = self.resolve(child_key)
        if child_id not in {child["child_id"] for child in connection.stored_children()}:
            raise unknown_child()
        return connection.save_course_filter(child_id, chosen, known, confirmed_empty)

    def timetable_available(self):
        return self.module_available(modules.TIMETABLE)

    def modules(self):
        registries = [connection.modules() for connection in self.connections()]
        if not registries:
            return modules.default_registry()
        merged = modules.default_registry()
        merged["modules"] = {
            name: any(registry["modules"].get(name, True) for registry in registries) for name in modules.MODULES
        }
        for field in ("unsupported", "covered", "unknown"):
            seen = set()
            for registry in registries:
                for entry in registry[field]:
                    if entry["segment"] not in seen:
                        seen.add(entry["segment"])
                        merged[field].append(entry)
        merged["checked_at"] = max(registry["checked_at"] for registry in registries)
        merged["iserv_version"] = next(
            (registry["iserv_version"] for registry in registries if registry["iserv_version"]), ""
        )
        return merged

    def modules_of(self, connection_id):
        return self.known_connection(connection_id).modules()

    def module_available(self, name):
        return self.modules()["modules"].get(name, True)

    def recheck_modules(self, connection_id=None):
        return self.pick_school(connection_id).recheck_modules()

    def me(self, connection_id=None):
        return self.pick_school(connection_id).me()

    def school_profile(self, connection_id=None):
        return self.pick_school(connection_id).school_profile()

    def iserv_session(self, connection_id=None):
        return self.pick_school(connection_id).iserv_session()

    def change_password(self, connection_id, current, new):
        return self.pick_school(connection_id).change_password(current, new)

    def repair_password(self, connection_id, password):
        return self.pick_school(connection_id).repair_password(password)

    def disconnect(self, connection_id=None, force=False, token_id=None):
        connection = self.pick_school(connection_id)
        result = connection.disconnect(force, token_id)
        if result.get("disconnected"):
            with self._lock:
                self._connections.pop(connection.id, None)
        return result

    def _merge(self, collect):
        results = []
        failures = []
        connections = self.connections()
        for connection in connections:
            try:
                results.append((connection, collect(connection)))
            except (NotConfiguredError,) + UPSTREAM_ERRORS as error:
                failures.append((connection, error))
                logger.warning("school#%s did not answer: %s", connection.id, failure_cause(error))
        if not connections:
            raise NotConfiguredError("no school connected")
        if failures and not results:
            raise failures[0][1]
        return results, [connection.id for connection, _ in failures]

    def mail_counts(self):
        schools = []
        for connection in self.connections():
            if not connection.mail_available():
                continue
            schools.append(self.annotate(connection, {"unread": integration.school_mail(self.store, connection.id)}))
        return {"schools": schools}

    def mail_call(self, connection_id, action, *args, **kwargs):
        connection = self.pick_school(connection_id)
        result = getattr(connection.mail(), action)(*args, **kwargs)
        if action in MAIL_RECOUNT_ACTIONS:
            unread = connection.mail_badge()
            if unread is not None:
                integration.record_school_mail(self.store, connection.id, unread)
            result["unread_mail"] = integration.school_mail(self.store, connection.id)
        return self.annotate(connection, result)

    def mail_attachment(self, connection_id, folder, uid, part):
        return MailFile(self.pick_school(connection_id).mail().attachment(folder, uid, part))

    def mail_web_call(self, connection_id, action, *args, **kwargs):
        connection = self.pick_school(connection_id)
        return self.annotate(connection, getattr(connection.mail_web(), action)(*args, **kwargs))

    def account_modules(self):
        schools = []
        for connection in self.connections():
            offered = connection.account_modules()
            if any(offered.values()):
                schools.append(self.annotate(connection, offered))
        return {"schools": schools}

    def file_listing(self, connection_id, path=""):
        connection = self.pick_school(connection_id)
        return self.annotate(connection, connection.files().listing(path))

    def file_search(self, connection_id, path, query):
        connection = self.pick_school(connection_id)
        return self.annotate(connection, connection.files().search(path, query))

    def school_file(self, connection_id, path):
        return self.pick_school(connection_id).files().download(path)

    def file_upload(self, connection_id, path, files, confirmed=False):
        connection = self.pick_school(connection_id)
        return self.annotate(connection, connection.files().upload(path, files, confirmed))

    def address_search(self, connection_id, query):
        connection = self.pick_school(connection_id)
        return self.annotate(connection, connection.contacts(modules.ADDRESSBOOK).search(query))

    def mailing_lists(self, connection_id):
        connection = self.pick_school(connection_id)
        return self.annotate(connection, connection.contacts(modules.MAILING_LISTS).lists())

    def mailing_list_detail(self, connection_id, list_id):
        connection = self.pick_school(connection_id)
        return self.annotate(connection, connection.contacts(modules.MAILING_LISTS).list_detail(list_id))

    def mailing_list_import(self, connection_id, values, files, confirmed=False):
        connection = self.pick_school(connection_id)
        return self.annotate(connection, connection.contacts(modules.MAILING_LISTS).import_list(values, files, confirmed))

    def mailing_list_delete(self, connection_id, list_id, confirmed=False):
        connection = self.pick_school(connection_id)
        return self.annotate(connection, connection.contacts(modules.MAILING_LISTS).delete_list(list_id, confirmed))

    def school_events(self, days=SCHOOL_EVENTS_DAYS):
        today = holidays.berlin_today()
        last = today + timedelta(days=days)
        connections = self.connections()
        if not connections:
            raise NotConfiguredError("no school connected")
        stored = self.store.load_calendar_snapshot().get("schools")
        stored = stored if isinstance(stored, dict) else {}
        entries = []
        unavailable = []
        for connection in connections:
            if not connection.module_available(modules.CALENDAR):
                continue
            entry = stored.get(connection.id)
            if isinstance(entry, dict) and isinstance(entry.get("events"), list):
                kept = entry["events"]
            else:
                try:
                    kept = connection.school_events(today, last)
                except SchoolCalendarRefusedError:
                    continue
                except (DataError, LoginError, OutageError) as error:
                    logger.info("school#%s calendar not read before its first poll: %s", connection.id, failure_cause(error))
                    unavailable.append(connection.id)
                    continue
            for event in kept:
                if isinstance(event, dict) and _event_in_window(event, today, last):
                    entries.append(self.annotate(connection, dict(event)))
        entries.sort(key=lambda event: (event.get("start") or "", event.get("title") or ""))
        return {"events": entries, "unavailable": unavailable}

    def tasks(self):
        found = self._school_lists(modules.TASKS, school_lists.TASKS_FIELD, lambda connection: connection.tasks())
        found[school_lists.TASKS_FIELD] = with_details(found[school_lists.TASKS_FIELD], self.store)
        found[school_lists.TASKS_FIELD].sort(key=school_lists.task_order)
        return found

    def news(self):
        found = self._school_lists(modules.NEWS, school_lists.NEWS_FIELD, lambda connection: connection.news())
        found[school_lists.NEWS_FIELD] = school_lists.news_order(found[school_lists.NEWS_FIELD])
        return found

    def forums(self):
        return self._school_lists(modules.FORUMS, account_lists.FORUMS_FIELD, lambda connection: connection.forums(), True)

    def texts(self):
        return self._school_lists(modules.TEXTS, account_lists.TEXTS_FIELD, lambda connection: connection.texts(), True)

    def infodisplay(self):
        return self._school_lists(modules.INFODISPLAY, account_lists.SCREENS_FIELD, lambda connection: connection.infodisplay(), True)

    def forum_mark_read(self, connection_id, confirmed=False):
        connection = self.known_connection(connection_id)
        if not connection.module_available(modules.FORUMS):
            return messages.result(False, READ_UNAVAILABLE_KEY, outcome="unavailable")
        return connection.forum_mark_read(confirmed)

    def _school_lists(self, module, field, read, name_unreadable=False):
        connections = self.connections()
        if not connections:
            raise NotConfiguredError("no school connected")
        entries = []
        schools = []
        unavailable = []
        unreadable = []
        for connection in connections:
            if not connection.module_available(module):
                continue
            listed = school_lists.stored_list(self.store, connection.id, field)
            if listed is None:
                try:
                    read_now = read(connection)
                except ModulePageRefusedError:
                    continue
                except (DataError, LoginError, OutageError) as error:
                    logger.info("school#%s %s not read before its first poll: %s", connection.id, field, failure_cause(error))
                    unavailable.append(connection.id)
                    if isinstance(error, DataError):
                        unreadable.append(connection.id)
                    continue
                listed = school_lists.store_list(
                    self.store,
                    connection.id,
                    field,
                    school_lists.carried(read_now, field, None),
                    getattr(connection, "clock", time.time)(),
                    account_lists.combined_extra(read_now),
                )
            school = {"last_success": int(listed.get("last_success") or 0)}
            school.update(account_lists.school_extras(listed))
            sections = listed.get(school_lists.SECTIONS_FIELD)
            if isinstance(sections, dict):
                school[school_lists.SECTIONS_FIELD] = sorted(name for name in sections if name in school_lists.NEWS_SECTIONS)
            schools.append(self.annotate(connection, school))
            entries.extend(self.annotate(connection, _without_open_url(item)) for item in listed[field] if isinstance(item, dict))
        found = {field: entries, "schools": schools, "unavailable": unavailable}
        if name_unreadable:
            found["unreadable"] = unreadable
        return found

    def letters(self, tab="current"):
        results, unavailable = self._merge(lambda connection: _school_letters(connection, tab))
        entries = []
        for connection, data in results:
            for entry in data.get("letters") or []:
                tagged = self.annotate(connection, entry)
                tagged["key"] = ":".join(
                    [connection.id, str(entry.get("letter_id")), str(entry.get("recipient_id"))]
                )
                entries.append(tagged)
        entries.sort(key=lambda item: published_sort_key(item.get("published")), reverse=True)
        return {"letters": entries, "unavailable": unavailable}

    def mark_letters_read(self, keys=None, mark_all=False):
        totals = {"read": 0, "blocked": 0, "failed": 0}
        grouped = {}
        for key in keys or []:
            connection_id, rest = _split_prefixed(key)
            grouped.setdefault(connection_id, []).append(rest)
        targets = self.connections() if mark_all else [self.known_connection(name) for name in grouped]
        for connection in targets:
            try:
                outcome = connection.mark_letters_read(grouped.get(connection.id), mark_all)
            except (NotConfiguredError,) + UPSTREAM_ERRORS as error:
                logger.warning("school#%s letters were not marked read: %s", connection.id, failure_cause(error))
                outcome = {"failed": len(grouped.get(connection.id) or []) or 1}
            for name in totals:
                totals[name] += int(outcome.get(name) or 0)
        return totals

    def letter_detail(self, connection_id, letter_id, recipient_id):
        return self.known_connection(connection_id).letter_detail(letter_id, recipient_id)

    def confirm_letter(self, connection_id, letter_id, recipient_id, text=None, choices=None):
        return self.known_connection(connection_id).confirm_letter(letter_id, recipient_id, text, choices)

    def answer_form(self, connection_id, letter_id, recipient_id):
        return self.known_connection(connection_id).answer_form(letter_id, recipient_id)

    def edit_answer(self, connection_id, letter_id, recipient_id, text=None, choices=None):
        return self.known_connection(connection_id).edit_answer(letter_id, recipient_id, text, choices)

    def reply_to_letter(self, connection_id, letter_id, recipient_id, text, request_id, confirmed=False):
        return self.known_connection(connection_id).reply_to_letter(letter_id, recipient_id, text, request_id, confirmed)

    def archive_letter(self, connection_id, letter_id, recipient_id):
        return self.known_connection(connection_id).archive_letter(letter_id, recipient_id)

    def restore_letter(self, connection_id, letter_id, recipient_id):
        return self.known_connection(connection_id).restore_letter(letter_id, recipient_id)

    def letter_attachment(self, connection_id, attachment_id):
        return self.known_connection(connection_id).letter_attachment(attachment_id)

    def pinboard(self):
        results, unavailable = self._merge(lambda connection: connection.pinboard())
        folders = []
        feed = []
        for connection, data in results:
            for folder in data.get("folders") or []:
                tagged = self.annotate(connection, folder)
                tagged["key"] = f"{connection.id}:{folder.get('id')}"
                folders.append(tagged)
            for entry in data.get("feed") or []:
                tagged = self.annotate(connection, entry)
                tagged["key"] = f"{connection.id}:{entry.get('id')}"
                tagged["folder_key"] = f"{connection.id}:{entry.get('folder_id')}"
                feed.append(tagged)
        return {"folders": folders, "feed": feed, "unavailable": unavailable}

    def mark_pinboard_seen(self, keys=None, mark_all=False, unseen=False):
        grouped = {}
        for key in keys or []:
            connection_id, rest = _split_prefixed(key)
            tile_id = as_int(rest)
            if tile_id is not None:
                grouped.setdefault(connection_id, []).append(tile_id)
        targets = self.connections() if mark_all else [self.known_connection(name) for name in grouped]
        seen = 0
        for connection in targets:
            outcome = connection.mark_pinboard_seen(grouped.get(connection.id), mark_all, unseen)
            seen += int(outcome.get("seen") or 0)
        return {"seen": seen}

    def pinboard_attachment(self, connection_id, filename):
        return self.known_connection(connection_id).pinboard_attachment(filename)

    def news_file(self, connection_id, item_id, kind, index, section=""):
        return self.known_connection(connection_id).news_file(item_id, kind, index, section)

    def news_section(self, section):
        connections = self.connections()
        if not connections:
            raise NotConfiguredError("no school connected")
        entries = []
        unavailable = []
        for connection in connections:
            if not connection.module_available(modules.NEWS):
                continue
            try:
                items = connection.news_section(section)
            except DataError as error:
                if getattr(error, "message_key", "") == news_sections.SECTION_UNKNOWN_KEY:
                    continue
                logger.info("school#%s news section unreadable: %s", connection.id, failure_cause(error))
                unavailable.append(connection.id)
                continue
            except (LoginError, OutageError) as error:
                logger.info("school#%s news section unreadable: %s", connection.id, failure_cause(error))
                unavailable.append(connection.id)
                continue
            entries.extend(self.annotate(connection, item) for item in items)
        return {school_lists.NEWS_FIELD: school_lists.news_order(entries), "section": section, "unavailable": unavailable}

    def news_section_detail(self, connection_id, section, item_id):
        return self.known_connection(connection_id).news_section_detail(section, item_id)

    def task_detail(self, connection_id, task_id):
        return self.known_connection(connection_id).task_detail(task_id)

    def task_file(self, connection_id, task_id, kind, index):
        return self.known_connection(connection_id).task_file(task_id, kind, index)

    def task_act(self, connection_id, task_id, action, form_id, target=None, text=None, files=None, confirmed=False):
        return self.known_connection(connection_id).task_act(task_id, action, form_id, target, text, files, confirmed)

    def absence_attachment(self, connection_id, filename):
        return self.known_connection(connection_id).absence_attachment(filename)

    def conferences(self, tab=CONFERENCE_TAB_CURRENT):
        results, unavailable = self._merge(lambda connection: connection.conferences(tab))
        items = []
        errors = []
        empty = True
        for connection, data in results:
            if data.get("error"):
                errors.append(connection.id)
            if not data.get("empty", not data.get("items")):
                empty = False
            for item in data.get("items") or []:
                items.append(self.annotate(connection, item))
        payload = {"items": items, "empty": empty and not items, "unavailable": unavailable}
        if errors and len(errors) == len(results):
            payload["error"] = "unavailable"
        return payload

    def conference_page(self, connection_id, page):
        connection = self.known_connection(connection_id)
        return dict(connection.conference_page(page), connection_id=connection.id)

    def submit_conference_form(self, connection_id, page, form, check, submit, values, request_id="", confirmed=False):
        connection = self.known_connection(connection_id)
        result = connection.submit_conference_form(page, form, check, submit, values, request_id, confirmed)
        if isinstance(result.get("page"), dict):
            result["page"] = dict(result["page"], connection_id=connection.id)
        return result

    def absences_overview(self, connection_id=None):
        connection = self.pick_school(connection_id)
        overview = connection.absences_overview()
        overview["connection_id"] = connection.id
        overview["school"] = connection.display_name()
        return overview

    def older_absence_form(self, connection_id=None):
        return self.pick_school(connection_id).older_absence_form()

    def older_absence_detail(self, connection_id, entry_id):
        return self.pick_school(connection_id).older_absence_detail(entry_id)

    def older_absence_attachment(self, connection_id, entry_id, key):
        return self.pick_school(connection_id).older_absence_attachment(entry_id, key)

    def attach_older_absence(self, connection_id, entry_id, upload):
        return self.pick_school(connection_id).attach_older_absence(entry_id, upload)

    def delete_older_attachment(self, connection_id, entry_id, key):
        return self.pick_school(connection_id).delete_older_attachment(entry_id, key)

    def older_absence_export(self, connection_id=None):
        return self.pick_school(connection_id).older_absence_export()

    def report_absence(self, connection_id, payload, attachments=None):
        return self.pick_school(connection_id).report_absence(payload, attachments)

    def delete_absence(self, connection_id, payload):
        return self.pick_school(connection_id).delete_absence(payload)

    def sick_note_pdf(self, connection_id, sick_note_id):
        return self.pick_school(connection_id).sick_note_pdf(sick_note_id)

    def messenger_rooms(self):
        results, unavailable = self._merge(lambda connection: connection.messenger_rooms())
        rooms = []
        self_user_ids = {}
        teacher_schools = []
        for connection, data in results:
            self_user_ids[connection.id] = data.get("self_user_id", "")
            if data.get("can_write_to_teacher"):
                teacher_schools.append(connection.id)
            for room in data.get("rooms") or []:
                tagged = self.annotate(connection, room)
                tagged["self_user_id"] = data.get("self_user_id", "")
                rooms.append(tagged)
        rooms.sort(key=lambda room: room.get("last_message_at") or 0, reverse=True)
        return {
            "rooms": rooms,
            "self_user_ids": self_user_ids,
            "can_write_to_teacher": bool(teacher_schools),
            "teacher_schools": teacher_schools,
            "unavailable": unavailable,
        }

    def messenger_room_messages(self, connection_id, room_id, before=None):
        connection = self.pick_school(connection_id)
        return _tag_media_urls(connection.messenger_room_messages(room_id, before), connection.id)

    def messenger_send(self, connection_id, room_id, text, txn_id=""):
        return self.pick_school(connection_id).messenger_send(room_id, text, txn_id)

    def messenger_media(self, connection_id, server_name, media_id):
        return self.pick_school(connection_id).messenger_media(server_name, media_id)

    def messenger_mark_read(self, connection_id, room_id, event_id):
        return self.pick_school(connection_id).messenger_mark_read(room_id, event_id)

    def messenger_teacher_search(self, connection_id, query):
        return self.pick_school(connection_id).messenger_teacher_search(query)

    def messenger_teacher_room_children(self, connection_id):
        return self.pick_school(connection_id).messenger_teacher_room_children()

    def messenger_create_teacher_room(self, connection_id, teacher, child_ids, add_other_parents):
        return self.pick_school(connection_id).messenger_create_teacher_room(teacher, child_ids, add_other_parents)

    def messenger_unread_pulse(self):
        total = None
        for connection in self.connections():
            count = connection.messenger_unread_pulse()
            if count is None:
                continue
            total = (total or 0) + int(count)
        return total
