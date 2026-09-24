import re
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[2] / "playwright.config.js"
LONGEST_RUN_SECONDS = 3600


def test_the_e2e_server_keeps_idle_connections_open_longer_than_a_test_run():
    text = CONFIG.read_text(encoding="utf-8")
    found = re.search(r"IDLE_CONNECTION_SECONDS = (\d+);", text)
    assert found
    assert int(found.group(1)) >= LONGEST_RUN_SECONDS
    assert "--timeout-keep-alive ${IDLE_CONNECTION_SECONDS}" in text
