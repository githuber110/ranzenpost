from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .html import is_safe_url

EMPTY_PHRASE = "keine elternsprechtage"


def parse_conferences(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True).lower()
    if EMPTY_PHRASE in text:
        return {"empty": True, "items": []}
    body = _table_body(soup)
    if body is None:
        return {"error": "parse_failed", "items": []}
    rows = body.find_all("tr")
    if not rows:
        return {"empty": True, "items": []}
    items = []
    for row in rows:
        cells = [cell.get_text(strip=True) for cell in row.find_all(["td", "th"])]
        links = [
            urljoin(base_url, anchor["href"])
            for anchor in row.find_all("a", href=True)
            if is_safe_url(anchor["href"])
        ]
        items.append({"cells": cells, "links": links})
    return {"empty": False, "items": items}


def _table_body(soup):
    for table in soup.find_all("table"):
        body = table.find("tbody")
        if body is not None:
            return body
    return None
