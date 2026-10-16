import logging

from . import account_lists, integration, messages, modules, school_lists
from .failure import error_kind
from .iserv.errors import DataError, ModulePageRefusedError, OutageError
from .iserv.forums import total_unread
from .store import edit

logger = logging.getLogger(__name__)

FORUMS_EVENT = "forums"
FORUMS_KEY = "notify.forums.new"
FORUM_STATE_KEY = "forum_unread"
PLAIN_LISTS = ((modules.INFODISPLAY, account_lists.SCREENS_FIELD),)


def _counted(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def forum_baseline(value):
    if not isinstance(value, dict):
        return {}
    baseline = {}
    for key, entry in value.items():
        if isinstance(entry, dict) and _counted(entry.get("unread")):
            baseline[str(key)] = {"unread": entry["unread"]}
    return baseline


def next_baseline(earlier, forums):
    listed = {str(forum["id"]) for forum in forums}
    kept = {key: value for key, value in earlier.items() if key in listed}
    for forum in forums:
        if _counted(forum.get("unread")):
            kept[str(forum["id"])] = {"unread": forum["unread"]}
    return kept


def fresh_forums(earlier, forums):
    fresh = []
    added = 0
    for forum in forums:
        unread = forum.get("unread")
        before = earlier.get(str(forum["id"]))
        if not _counted(unread) or before is None or unread <= before["unread"]:
            continue
        fresh.append(forum)
        added += unread - before["unread"]
    return fresh, added


def forum_notice(forum):
    return {
        "id": str(forum["id"]),
        "title": forum.get("title") or "",
        "sender": forum.get("category") or "",
        "date": forum.get("last_post_date") or "",
        "text": forum.get("last_post") or "",
    }


def _unread_known(forums):
    return all(_counted(forum.get("unread")) for forum in forums)


def drop_list(store, connection_id, field):
    snapshot = store.load_calendar_snapshot()
    if not (isinstance(snapshot.get(field), dict) and connection_id in snapshot[field]):
        return

    def change(snapshot):
        stored = snapshot.get(field)
        if isinstance(stored, dict):
            stored.pop(connection_id, None)

    edit(store, store.load_calendar_snapshot, store.save_calendar_snapshot, change)


def _drop_forums(poller, connection_id, poll_state):
    drop_list(poller.store, connection_id, account_lists.FORUMS_FIELD)
    integration.record_school_list(poller.store, connection_id, integration.SCHOOL_FORUMS, None)
    poll_state.pop(FORUM_STATE_KEY, None)


def _read(connection_id, field, reader):
    try:
        return reader(), None
    except OutageError:
        raise
    except ModulePageRefusedError:
        logger.info("poll school#%s %s refused for this account", connection_id, field)
        return None, {"module": field, "state": "refused"}
    except DataError as error:
        logger.info("poll school#%s %s unreadable, last list kept: %s", connection_id, field, error_kind(error))
        return None, {"module": field, "state": "unreadable"}
    except Exception as error:
        logger.warning("poll school#%s %s unreadable, last list kept: %s", connection_id, field, error_kind(error), exc_info=True)
        return None, {"module": field, "state": "unreadable", "kind": error_kind(error)}


def poll_forums(poller, connection, connection_id, offered, poll_state, language=None, school=""):
    field = account_lists.FORUMS_FIELD
    reader = getattr(connection, field, None)
    if poller.store is None or not callable(reader):
        return None
    if not offered:
        _drop_forums(poller, connection_id, poll_state)
        return None
    listed, failure = _read(connection_id, field, reader)
    if failure is not None:
        if failure.get("state") == "refused":
            _drop_forums(poller, connection_id, poll_state)
        return failure
    forums = [forum for forum in listed.get(field) or [] if isinstance(forum, dict)]
    now = int(poller.clock())
    school_lists.store_list(poller.store, connection_id, field, forums, now, account_lists.list_extra_of(listed))
    first = not isinstance(poll_state.get(FORUM_STATE_KEY), dict)
    earlier = forum_baseline(poll_state.get(FORUM_STATE_KEY))
    fresh, added = fresh_forums(earlier, forums)
    poll_state[FORUM_STATE_KEY] = next_baseline(earlier, forums)
    unread = total_unread(forums)
    if listed.get(account_lists.COMPLETE_FIELD, True) is not False and _unread_known(forums):
        integration.record_school_list(
            poller.store,
            connection_id,
            integration.SCHOOL_FORUMS,
            [forum_notice(forum) for forum in forums if _counted(forum.get("unread")) and forum["unread"] > 0],
            [forum_notice(forum) for forum in fresh],
            now,
            count=unread,
        )
    else:
        integration.record_school_list(poller.store, connection_id, integration.SCHOOL_FORUMS, None)
    if first:
        return {"module": field, "forums": len(forums), "unread": unread, "initialized": True}
    if added:
        poller._notify(
            FORUMS_EVENT,
            "",
            poller._tagged(language, school, messages.text_count(language, FORUMS_KEY, added)),
            f"school#{connection_id}: {added} new",
        )
    return {"module": field, "forums": len(forums), "unread": unread, "new": added}


def poll_plain_list(poller, connection, connection_id, offered, field):
    reader = getattr(connection, field, None)
    if poller.store is None or not callable(reader):
        return None
    if not offered:
        drop_list(poller.store, connection_id, field)
        return None
    listed, failure = _read(connection_id, field, reader)
    if failure is not None:
        if failure.get("state") == "refused":
            drop_list(poller.store, connection_id, field)
        return failure
    stored = school_lists.stored_list(poller.store, connection_id, field)
    entries = school_lists.carried(listed, field, stored.get(field) if stored else None)
    school_lists.store_list(poller.store, connection_id, field, entries, int(poller.clock()), account_lists.combined_extra(listed))
    return {"module": field, "items": len(entries)}


def poll_account_lists(poller, connection, connection_id, flags, poll_state, language=None, school=""):
    events = [poll_forums(poller, connection, connection_id, flags.get(modules.FORUMS, False), poll_state, language, school)]
    for module, field in PLAIN_LISTS:
        events.append(poll_plain_list(poller, connection, connection_id, flags.get(module, False), field))
    return [event for event in events if event is not None]
