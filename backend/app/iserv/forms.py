import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

META_REFRESH_RE = re.compile(r"url=([^;]+)", re.IGNORECASE)
JS_REDIRECT_RE = re.compile(
    r"""(?:window\.location(?:\.href)?|location\.href|location\.replace)\s*=?\s*\(?\s*['"]([^'"]+)['"]"""
)


@dataclass
class Form:
    action: str
    method: str
    fields: dict
    control_types: dict
    submits: dict = field(default_factory=dict)


def parse_forms(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    forms = []
    for element in soup.find_all("form"):
        target = element.get("hx-post") or element.get("hx-put") or element.get("action")
        action = urljoin(base_url, target or base_url)
        method = (element.get("method") or "post").lower()
        fields = {}
        control_types = {}
        submits = {}
        for control in element.find_all(["input", "textarea", "select"]):
            name = control.get("name")
            if not name:
                continue
            fields[name] = control.get("value") or ""
            if control.name == "input":
                control_types[name] = (control.get("type") or "text").lower()
            else:
                control_types[name] = control.name
        for control in element.find_all("button"):
            name = control.get("name")
            if not name or (control.get("type") or "submit").lower() != "submit":
                continue
            submits[name] = control.get("value") or ""
        for name, kind in control_types.items():
            if kind == "submit":
                submits[name] = fields.get(name, "")
        forms.append(Form(action, method, fields, control_types, submits))
    return forms


def find_login_form(forms):
    for form in forms:
        if any(kind == "password" for kind in form.control_types.values()):
            return form
    return None


def is_two_factor_form(form):
    if "otp" in form.fields:
        return True
    return any(name.startswith("two_factor_login_form[") for name in form.fields)


def find_two_factor_form(forms):
    for form in forms:
        if is_two_factor_form(form):
            return form
    return None


def find_client_redirect(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.find("meta", attrs={"http-equiv": re.compile("refresh", re.IGNORECASE)})
    if meta:
        match = META_REFRESH_RE.search(meta.get("content", ""))
        if match:
            return urljoin(base_url, match.group(1).strip())
    match = JS_REDIRECT_RE.search(html)
    if match:
        return urljoin(base_url, match.group(1))
    return None


AFFIRMATIVE_HINTS = ("submit", "confirm", "save", "send", "ok", "yes")
NEGATIVE_HINTS = ("cancel", "cancle", "abort", "back", "delete", "remove", "reset")


def affirmative_submit(submits):
    if not submits:
        return {}
    candidates = [name for name in submits if not any(h in name.lower() for h in NEGATIVE_HINTS)]
    if not candidates:
        return {}
    for name in candidates:
        if any(hint in name.lower() for hint in AFFIRMATIVE_HINTS):
            return {name: submits[name]}
    return {candidates[0]: submits[candidates[0]]}
