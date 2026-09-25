import re

from bs4 import BeautifulSoup

from .models import Child
from .pages import base_shape, path_of, refusal_wording

CHILD_SELECT_ID = "timetable-filter-child-select"
TIME_TABLE_PATH = "/iserv/time-table"
TIME_TABLE_MARKER = re.compile(r"^timetable-")
LOGIN_PATHS = ("/iserv/auth/", "/iserv/login", "/idesk/login")
ABSENT_PAGE_STATUSES = (403, 404)
SESSION_LOST_STATUSES = (401,)
CHILD_PAGE_MESSAGE_KEY = "api.children.unreadable"
CHILD_PAGE_FORBIDDEN_KEY = "api.children.forbidden"
FORBIDDEN_STATUSES = (401, 403)
LOGIN_FIELD = "_password"


def child_page_message_key(status):
    return CHILD_PAGE_FORBIDDEN_KEY if status in FORBIDDEN_STATUSES else CHILD_PAGE_MESSAGE_KEY


def parse_children(html):
    soup = BeautifulSoup(html, "html.parser")
    select = soup.find("select", id=CHILD_SELECT_ID)
    children = []
    if select is None:
        return children
    for option in select.find_all("option"):
        value = (option.get("value") or "").strip()
        name = option.get_text(strip=True)
        if value and name:
            children.append(Child(child_id=value, name=name))
    return children


def child_select_present(html):
    soup = BeautifulSoup(html or "", "html.parser")
    return soup.find("select", id=CHILD_SELECT_ID) is not None


def page_diagnosis(response):
    text = getattr(response, "text", "") or ""
    soup = BeautifulSoup(text, "html.parser")
    shape = base_shape(response)
    shape.update({
        "child_select": CHILD_SELECT_ID in text,
        "select_elements": len(soup.find_all("select")),
        "login_form": soup.find("input", attrs={"name": LOGIN_FIELD}) is not None,
    })
    wording = refusal_wording(response, soup)
    if wording:
        shape["refusal"] = wording
    return shape


def time_table_session_lost(response):
    status = int(getattr(response, "status_code", 0) or 0)
    if status in SESSION_LOST_STATUSES:
        return "status %d" % status
    final = path_of(getattr(response, "url", "") or "")
    if any(final.startswith(marker) for marker in LOGIN_PATHS):
        return "login page"
    soup = BeautifulSoup(getattr(response, "text", "") or "", "html.parser")
    if soup.find("input", attrs={"name": LOGIN_FIELD}) is not None:
        return "login page"
    return ""


def time_table_absence(response):
    status = int(getattr(response, "status_code", 0) or 0)
    if status in ABSENT_PAGE_STATUSES:
        return "status %d" % status
    if status != 200:
        return ""
    if path_of(getattr(response, "url", "") or "").rstrip("/") != TIME_TABLE_PATH:
        return "redirect"
    return ""


def time_table_recognised(html):
    return BeautifulSoup(html or "", "html.parser").find(id=TIME_TABLE_MARKER) is not None
