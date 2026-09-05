from bs4 import BeautifulSoup

from .models import Child
from .pages import base_shape

CHILD_SELECT_ID = "timetable-filter-child-select"
CHILD_PAGE_MESSAGE_KEY = "api.children.unreadable"
LOGIN_FIELD = "_password"


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
    return shape
