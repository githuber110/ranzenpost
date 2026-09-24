import logging

from app.calendar_listener import INVALID_REQUEST_MESSAGE, InvalidRequestSummarizer


def _record(message=INVALID_REQUEST_MESSAGE):
    return logging.LogRecord(
        name="uvicorn.error",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_invalid_request_lines_are_swallowed_one_by_one():
    summarizer = InvalidRequestSummarizer(clock=lambda: 0.0)

    assert summarizer.filter(_record()) is False
    assert summarizer.filter(_record()) is False


def test_other_messages_pass_through_untouched():
    summarizer = InvalidRequestSummarizer(clock=lambda: 0.0)

    assert summarizer.filter(_record("something else")) is True


def test_a_summary_line_is_emitted_once_a_minute_not_once_per_hit():
    clock = {"now": 0.0}
    summaries = []
    summarizer = InvalidRequestSummarizer(
        clock=lambda: clock["now"], on_summary=summaries.append
    )

    for _ in range(5):
        summarizer.filter(_record())
    assert summaries == []

    clock["now"] = 61.0
    summarizer.filter(_record())

    assert summaries == [6]


def test_flush_emits_a_pending_partial_window_on_shutdown():
    summaries = []
    summarizer = InvalidRequestSummarizer(clock=lambda: 0.0, on_summary=summaries.append)

    summarizer.filter(_record())
    summarizer.filter(_record())
    summarizer.flush()

    assert summaries == [2]


def test_flush_with_nothing_pending_stays_silent():
    summaries = []
    summarizer = InvalidRequestSummarizer(clock=lambda: 0.0, on_summary=summaries.append)

    summarizer.flush()

    assert summaries == []


def test_the_summarizer_leaves_invalid_requests_of_other_servers_alone():
    import logging

    from app.calendar_listener import INVALID_REQUEST_MESSAGE, InvalidRequestSummarizer

    summarizer = InvalidRequestSummarizer(on_summary=lambda count: None, thread_name="calendar-listener")
    record = logging.LogRecord("uvicorn.error", logging.WARNING, __file__, 1, INVALID_REQUEST_MESSAGE, None, None)
    record.threadName = "MainThread"
    assert summarizer.filter(record) is True
    record.threadName = "calendar-listener"
    assert summarizer.filter(record) is False
