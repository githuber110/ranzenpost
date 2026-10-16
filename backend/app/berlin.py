from datetime import date, datetime, time, timedelta, timezone


def _last_sunday(year, month):
    day = 31
    while True:
        try:
            candidate = date(year, month, day)
        except ValueError:
            day -= 1
            continue
        if candidate.weekday() == 6:
            return candidate
        day -= 1


def offset(local):
    year = local.year
    starts = datetime.combine(_last_sunday(year, 3), time(2, 0))
    ends = datetime.combine(_last_sunday(year, 10), time(3, 0))
    return 2 if starts <= local < ends else 1


def utc_offset(utc_naive):
    year = utc_naive.year
    starts = datetime.combine(_last_sunday(year, 3), time(1, 0))
    ends = datetime.combine(_last_sunday(year, 10), time(1, 0))
    return 2 if starts <= utc_naive < ends else 1


def local_from_utc(utc_naive):
    return utc_naive + timedelta(hours=utc_offset(utc_naive))


def local_from_epoch(epoch):
    return local_from_utc(datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None))


def iso_from_epoch(epoch):
    utc_naive = datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None)
    hours = utc_offset(utc_naive)
    return (utc_naive + timedelta(hours=hours)).isoformat(timespec="seconds") + "+%02d:00" % hours


def date_from_utc(utc_naive):
    return local_from_utc(utc_naive).date()


def today(utc_naive=None):
    return date_from_utc(utc_naive or datetime.now(timezone.utc).replace(tzinfo=None))
