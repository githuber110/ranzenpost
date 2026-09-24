import math

from . import lockout

MAX_ATTEMPTS = 3
FIRST_WAIT_SECONDS = 30
MAX_WAIT_SECONDS = 300
FORGET_SECONDS = 600
PAUSES = "pauses"
RATE_LIMITED = "rate_limited"
OUTAGE = "outage"
WAIT_OUT_OUTCOMES = (RATE_LIMITED, OUTAGE)
LONG_PAUSE_REASONS = (lockout.LOCKED, lockout.CAPTCHA)
PAUSE_MESSAGES = {
    lockout.BAD_CREDENTIALS: "api.wizard.pausedCredentials",
    lockout.UNKNOWN_ACCOUNT: "api.wizard.pausedCredentials",
    lockout.LOCKED: "api.wizard.pausedLocked",
    lockout.CAPTCHA: "api.lockout.captcha",
    RATE_LIMITED: "api.wizard.pausedRateLimited",
    OUTAGE: "api.wizard.pausedRateLimited",
    "bad_code": "api.wizard.pausedCode",
    "code_rejected": "api.wizard.pausedCode",
}
DEFAULT_PAUSE_MESSAGE = "api.wizard.paused"


def entry_of(pauses, school):
    return dict((pauses or {}).get(school or "") or {})


def is_paused(entry, now):
    until = entry.get("until")
    return until is not None and now < until


def seconds_left(entry, now):
    return max(0, math.ceil(entry["until"] - now)) if is_paused(entry, now) else 0


def live(entry, now):
    if is_paused(entry, now):
        return True
    return now - entry.get("last", now) < FORGET_SECONDS


def live_pauses(pauses, now):
    return {school: entry for school, entry in (pauses or {}).items() if live(entry, now)}


def register_failure(entry, reason, now):
    entry = dict(entry)
    entry["attempts"] = entry.get("attempts", 0) + 1
    entry["reason"] = reason
    entry["last"] = now
    if reason in LONG_PAUSE_REASONS:
        entry["until"] = now + MAX_WAIT_SECONDS
    elif entry["attempts"] >= MAX_ATTEMPTS:
        wait = FIRST_WAIT_SECONDS * 2 ** (entry["attempts"] - MAX_ATTEMPTS)
        entry["until"] = now + min(wait, MAX_WAIT_SECONDS)
    return entry


def hold(entry, reason, seconds, now):
    entry = dict(entry)
    entry["reason"] = reason
    entry["last"] = now
    entry["until"] = max(entry.get("until") or 0, now + seconds)
    return entry


def wait_for(outcome, retry_after):
    if retry_after is not None:
        return max(int(retry_after), FIRST_WAIT_SECONDS)
    if outcome == RATE_LIMITED:
        return MAX_WAIT_SECONDS
    return None


def message_key(entry):
    return PAUSE_MESSAGES.get(entry.get("reason"), DEFAULT_PAUSE_MESSAGE)
