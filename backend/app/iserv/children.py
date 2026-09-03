from bs4 import BeautifulSoup

from .models import Child

CHILD_SELECT_ID = "timetable-filter-child-select"


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
