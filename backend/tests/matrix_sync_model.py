import copy
import fnmatch
import hashlib
import json

SERVER = "school.example"
OWN_USER = f"@me:{SERVER}"
TEACHER = f"@teacher.lead:{SERVER}"
NOW = 1790000000000
DEFAULT_TIMELINE_LIMIT = 10
CUSTOM_STATE_TYPE = "org.example.room.meta"


def _user(kind, index):
    return f"@{kind}.{index}:{SERVER}"


class _Room:
    def __init__(self, room_id, clock):
        self.room_id = room_id
        self.clock = clock
        self.history = []
        self.unread = 0
        self.receipts = {}

    def _id(self):
        digest = hashlib.sha256(f"{self.room_id}/{len(self.history)}".encode()).hexdigest()
        return "$" + digest[:43]

    def add(self, event_type, sender, content, state_key=None):
        self.clock[0] += 61000
        event = {
            "type": event_type,
            "sender": sender,
            "content": content,
            "origin_server_ts": self.clock[0],
            "unsigned": {"age": NOW - self.clock[0], "membership": "join"},
            "event_id": self._id(),
        }
        if state_key is not None:
            event["state_key"] = state_key
            previous = self.current_state(len(self.history)).get((event_type, state_key))
            if previous is not None:
                event["unsigned"]["replaces_state"] = previous["event_id"]
                event["unsigned"]["prev_content"] = copy.deepcopy(previous["content"])
                event["unsigned"]["prev_sender"] = previous["sender"]
        self.history.append(event)
        return event

    def current_state(self, upto):
        state = {}
        for event in self.history[:upto]:
            if "state_key" in event:
                state[(event["type"], event["state_key"])] = event
        return state

    def member(self, user_id, display_name, membership="join"):
        return self.add(
            "m.room.member",
            user_id,
            {"membership": membership, "displayname": display_name, "avatar_url": None},
            state_key=user_id,
        )

    def message(self, sender, body):
        return self.add("m.room.message", sender, {"msgtype": "m.text", "body": body})


def _create_room(room_id, clock, name, teachers, parents, left, messages, announce=False):
    room = _Room(room_id, clock)
    creator = teachers[0][0]
    room.add("m.room.create", creator, {"creator": creator, "room_version": "10"}, state_key="")
    room.member(creator, teachers[0][1])
    power = {
        "users": {user_id: 100 if index == 0 else 50 for index, (user_id, _name) in enumerate(teachers)},
        "users_default": 0,
        "events": {
            "m.room.name": 50,
            "m.room.power_levels": 100,
            "m.room.history_visibility": 100,
            "m.room.canonical_alias": 50,
            "m.room.avatar": 50,
            "m.room.tombstone": 100,
            "m.room.server_acl": 100,
            "m.room.encryption": 100,
        },
        "events_default": 50 if announce else 0,
        "state_default": 50,
        "ban": 50,
        "kick": 50,
        "redact": 50,
        "invite": 50,
        "historical": 100,
        "notifications": {"room": 50},
    }
    room.add("m.room.power_levels", creator, power, state_key="")
    room.add("m.room.join_rules", creator, {"join_rule": "invite"}, state_key="")
    room.add("m.room.history_visibility", creator, {"history_visibility": "shared"}, state_key="")
    room.add("m.room.guest_access", creator, {"guest_access": "forbidden"}, state_key="")
    if name:
        room.add("m.room.name", creator, {"name": name}, state_key="")
        room.add("m.room.topic", creator, {"topic": f"Messages for {name}"}, state_key="")
    room.add(
        CUSTOM_STATE_TYPE,
        creator,
        {"managed": True, "group": room_id[1:9], "read_only": announce, "created_by": creator},
        state_key="",
    )
    for user_id, display_name in teachers[1:] + parents + left:
        room.add(
            "m.room.member",
            creator,
            {"membership": "invite", "displayname": display_name, "avatar_url": None},
            state_key=user_id,
        )
        room.member(user_id, display_name)
    for user_id, display_name in left:
        room.member(user_id, display_name, membership="leave")
    for index, (sender, body) in enumerate(messages):
        event = room.message(sender, body)
        if index % 4 == 1:
            for reactor, _name in parents[:3]:
                room.add(
                    "m.reaction",
                    reactor,
                    {"m.relates_to": {"rel_type": "m.annotation", "event_id": event["event_id"], "key": "+1"}},
                )
    for user_id, _name in parents:
        room.receipts[user_id] = room.history[-1]["event_id"]
    return room


def _parents(start, count):
    return [(_user("parent", index), f"Parent {index}") for index in range(start, start + count)]


def _teachers(start, count):
    return [(_user("teacher", index), f"Teacher {index}") for index in range(start, start + count)]


def _chatter(senders, count, words=18):
    lines = []
    for index in range(count):
        sender = senders[index % len(senders)][0]
        text = " ".join(f"word{(index * 7 + step) % 97}" for step in range(words + index % 11))
        lines.append((sender, f"Note {index}: {text}."))
    return lines


def build_account(class_groups=2, class_size=40, wide_rooms=1, wide_size=150, direct_rooms=6, seed_messages=30):
    clock = [NOW - 90 * 24 * 3600 * 1000]
    me = [(OWN_USER, "Me")]
    rooms = []
    lead = [(TEACHER, "Teacher Lead")]
    for index in range(class_groups):
        teachers = lead + _teachers(index * 3, 2)
        parents = me + _parents(index * class_size, class_size)
        left = _parents(1000 + index * 10, 6)
        chatter = _chatter(teachers + parents[1:6], seed_messages)
        room = _create_room(f"!class{index}:{SERVER}", clock, f"Class {index + 3}b", teachers, parents, left, chatter)
        for user_id, display_name in _parents(2000 + index * 20, 12):
            room.member(user_id, display_name)
        room.unread = 3 + index
        rooms.append(room)
    for index in range(wide_rooms):
        teachers = lead + _teachers(100 + index * 5, 4)
        parents = me + _parents(5000 + index * wide_size, wide_size)
        chatter = _chatter(teachers, seed_messages // 3, words=60)
        room = _create_room(
            f"!wide{index}:{SERVER}", clock, f"Year news {index + 1}", teachers, parents, [], chatter, announce=True
        )
        room.unread = 1
        rooms.append(room)
    for index in range(direct_rooms):
        teacher = _teachers(200 + index, 1)
        chatter = _chatter(teacher + me, 8 + index)
        room = _create_room(f"!direct{index}:{SERVER}", clock, "", teacher, me, [], chatter)
        room.unread = index % 2
        rooms.append(room)
    busy = rooms[0]
    for reactor, _name in _parents(0, 25):
        busy.add("m.reaction", reactor, {"m.relates_to": {"rel_type": "m.annotation", "event_id": busy.history[-1]["event_id"], "key": "ok"}})
    return {"rooms": rooms, "invites": [f"!invite0:{SERVER}"]}


def _type_matches(event_type, section):
    if section is None:
        return True
    types = section.get("types")
    not_types = section.get("not_types") or []
    if any(fnmatch.fnmatchcase(event_type, pattern) for pattern in not_types):
        return False
    if types is None:
        return True
    return any(fnmatch.fnmatchcase(event_type, pattern) for pattern in types)


def _limited(events, section):
    if section is None or section.get("limit") is None:
        return events
    limit = int(section["limit"])
    return events[-limit:] if limit > 0 else []


def only_fields(event, fields):
    if not fields:
        return event
    kept = {}
    for path in fields:
        parts = path.split(".")
        source = event
        for part in parts[:-1]:
            source = source.get(part) if isinstance(source, dict) else None
        if not isinstance(source, dict) or parts[-1] not in source:
            continue
        target = kept
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = copy.deepcopy(source[parts[-1]])
    return kept


def _push_rules():
    rule_ids = [f".m.rule.example_{index}" for index in range(28)]
    return {
        "global": {
            kind: [
                {
                    "rule_id": rule_id,
                    "default": True,
                    "enabled": True,
                    "conditions": [{"kind": "event_match", "key": "type", "pattern": "m.room.message"}],
                    "actions": ["notify", {"set_tweak": "sound", "value": "default"}, {"set_tweak": "highlight", "value": False}],
                }
                for rule_id in rule_ids[offset::4]
            ]
            for offset, kind in enumerate(("override", "content", "room", "underride"))
        }
    }


def _joined_room(room, sync_filter):
    room_filter = sync_filter.get("room") or {}
    timeline_filter = room_filter.get("timeline")
    fields = sync_filter.get("event_fields")
    positions = [
        position
        for position, event in enumerate(room.history)
        if _type_matches(event["type"], timeline_filter)
    ]
    limit = DEFAULT_TIMELINE_LIMIT
    if timeline_filter is not None and timeline_filter.get("limit") is not None:
        limit = int(timeline_filter["limit"])
    window = positions[-limit:] if limit > 0 else []
    start = window[0] if window else len(room.history)
    state = [
        event
        for event in room.current_state(start).values()
        if _type_matches(event["type"], room_filter.get("state"))
    ]
    timeline = [room.history[position] for position in window]
    ephemeral = [
        {"type": "m.typing", "content": {"user_ids": []}},
        {
            "type": "m.receipt",
            "content": {
                event_id: {"m.read": {user_id: {"ts": NOW - 5000}}}
                for user_id, event_id in room.receipts.items()
            },
        },
    ]
    account_data = [
        {"type": "m.fully_read", "content": {"event_id": room.history[-1]["event_id"]}},
        {"type": "m.tag", "content": {"tags": {}}},
    ]
    return {
        "state": {"events": [only_fields(event, fields) for event in state]},
        "timeline": {
            "events": [only_fields(event, fields) for event in timeline],
            "limited": len(positions) > len(window),
            "prev_batch": f"t{len(room.history)}-{room.room_id[1:9]}",
        },
        "ephemeral": {
            "events": _limited([e for e in ephemeral if _type_matches(e["type"], room_filter.get("ephemeral"))], room_filter.get("ephemeral"))
        },
        "account_data": {
            "events": _limited(
                [e for e in account_data if _type_matches(e["type"], room_filter.get("account_data"))],
                room_filter.get("account_data"),
            )
        },
        "unread_notifications": {"notification_count": room.unread, "highlight_count": 0},
    }


def _has_content(entry):
    return any(entry[section]["events"] for section in ("state", "timeline", "ephemeral", "account_data"))


def _joined_rooms(account, sync_filter):
    entries = {room.room_id: _joined_room(room, sync_filter) for room in account["rooms"]}
    return {room_id: entry for room_id, entry in entries.items() if _has_content(entry)}


def serve_sync(account, sync_filter):
    sync_filter = sync_filter or {}
    global_account_data = [
        {"type": "m.push_rules", "content": _push_rules()},
        {"type": "m.direct", "content": {user_id: [f"!direct{index}:{SERVER}"] for index, (user_id, _n) in enumerate(_teachers(200, 6))}},
    ]
    presence = [
        {"type": "m.presence", "sender": user_id, "content": {"presence": "offline", "last_active_ago": 3600000}}
        for user_id, _name in _teachers(0, 12)
    ]
    invite = {
        room_id: {
            "invite_state": {
                "events": [
                    {"type": "m.room.name", "state_key": "", "sender": TEACHER, "content": {"name": "New room"}},
                    {"type": "m.room.member", "state_key": OWN_USER, "sender": TEACHER, "content": {"membership": "invite"}},
                ]
            }
        }
        for room_id in account["invites"]
    }
    return {
        "next_batch": "s1234_5678_90_1_2_3_4_5_6",
        "account_data": {
            "events": _limited(
                [e for e in global_account_data if _type_matches(e["type"], sync_filter.get("account_data"))],
                sync_filter.get("account_data"),
            )
        },
        "presence": {
            "events": _limited(
                [e for e in presence if _type_matches(e["type"], sync_filter.get("presence"))],
                sync_filter.get("presence"),
            )
        },
        "to_device": {"events": []},
        "device_lists": {"changed": [], "left": []},
        "device_one_time_keys_count": {"signed_curve25519": 0},
        "rooms": {
            "join": _joined_rooms(account, sync_filter),
            "invite": invite,
            "leave": {},
        },
    }


def body_size(body):
    return len(json.dumps(body, separators=(",", ":")).encode("utf-8"))
