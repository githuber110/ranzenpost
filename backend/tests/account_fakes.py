from html import escape
from urllib.parse import quote, unquote, urlsplit

from requests.structures import CaseInsensitiveDict

SCHOOL = "https://school-one.example"
TOKEN = "fixture-token"
OWN_ROOT = "/iserv/file/-/Files"
GROUP_ROOT = "/iserv/file/-/Groups"
LIST_ROOT = "/iserv/mailinglist"
BOOK_ROOT = "/iserv/addressbook"
PRIVATE_BOOK = "/iserv/addressbook/private"
PUBLIC_BOOK = "/iserv/addressbook/public"
FILE_HEADERS = ["", "", "Name", "Größe", "Typ", "Letzte Änderung", "Aktion", "", ""]
BOOK_HEADERS = ["", "Name", "Vorname", "E-Mail-Adresse", "Klasse", ""]
LIST_HEADERS = ["", "Titel", "Adressen", "", ""]
ACTION_OPTIONS = ["copy", "move", "rename", "zip", "unzip", "share", "mail", "download"]


class Answer:
    def __init__(self, status, url, text="", content=None, content_type="text/html; charset=utf-8", history=(), disposition=""):
        self.status_code = status
        self.url = url
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")
        self.headers = CaseInsensitiveDict({"content-type": content_type})
        if disposition:
            self.headers["content-disposition"] = disposition
        self.history = list(history)
        self.truncated = False

    def json(self):
        raise ValueError("no json")


def page(title, body):
    return (
        "<!doctype html><html><head><title>%s - IServ</title></head><body>"
        "<nav class='navbar navbar-default'><a href='/iserv/'>IServ</a><a href='/iserv/mail'>E-Mail</a>"
        "<a href='/iserv/file/-/Files'>Dateien</a><a href='/iserv/addressbook/private'>Adressbuch</a>"
        "<a href='/iserv/mailinglist'>Verteilerlisten</a><span class='user'>owner@school-one.example</span></nav>"
        "<form action='/iserv/auth/logout' method='post'><input type='hidden' name='id_token_hint' value='x'></form>"
        "<main><h1>%s</h1>%s</main><footer>support@school-one.example</footer></body></html>"
    ) % (escape(title), escape(title), body)


def default_own():
    return {
        "": [
            {"name": "Projekte", "folder": True, "date": "2026-10-01 10:00"},
            {"name": "Lesetagebuch.pdf", "folder": False, "size": "120 KB", "type": "PDF-Dokument", "date": "2026-10-12 08:30", "data": b"%PDF-1.4 reading log"},
            {"name": "Notizen.txt", "folder": False, "size": "1 KB", "type": "Textdatei", "date": "2026-09-20 17:05", "data": b"notes"},
        ],
        "Projekte": [
            {"name": "Plakat.png", "folder": False, "size": "340 KB", "type": "PNG-Bild", "date": "2026-10-02 11:15", "data": b"\x89PNG fixture"},
        ],
    }


def default_groups():
    return {
        "": [{"name": "Klasse 3b", "folder": True, "date": "2026-09-01 09:00"}],
        "Klasse 3b": [{"name": "Elternbrief.pdf", "folder": False, "size": "80 KB", "type": "PDF-Dokument", "date": "2026-10-05 12:00", "data": b"%PDF-1.4 letter"}],
    }


def default_people():
    return {
        PRIVATE_BOOK: [{"last": "Hausmeister", "first": "Herr", "address": "hausmeister@school-one.example", "class": ""}],
        PUBLIC_BOOK: [
            {"last": "Behrens", "first": "Anna", "address": "anna.behrens@school-one.example", "class": "3b"},
            {"last": "Behrendt", "first": "Tom", "address": "tom.behrendt@school-one.example", "class": "4a"},
            {"last": "Schulbuero", "first": "", "address": "office@school-one.example", "class": ""},
        ],
    }


def default_lists():
    return [{"id": "41", "title": "Elternrat 3b", "addresses": ["anna.behrens@school-one.example", "eltern.mia@example.org"]}]


class FakeAccountSchool:
    def __init__(self, base=SCHOOL, own=None, groups=None, people=None, lists=None):
        self.base = base
        self.own = own if own is not None else default_own()
        self.groups = groups if groups is not None else default_groups()
        self.people = people if people is not None else default_people()
        self.lists = lists if lists is not None else default_lists()
        self.posts = []
        self.fetched = []
        self.upload_refused = False
        self.upload_ignored = False
        self.delete_asks = True
        self.list_table = True
        self.book_root_missing = False
        self.confirm_extra = []
        self.confirm_redirected = False
        self.delete_also = []
        self.broken_folders = []
        self.rename_uploads = False
        self.import_ignored = False
        self.title_with_extension = False
        self.next_list = 50

    def url(self, path):
        return self.base + path

    def is_authenticated(self):
        return True

    def login(self, username, password, code_provider):
        return self

    def _tree(self, path):
        if path == OWN_ROOT or path.startswith(OWN_ROOT + "/"):
            return self.own, OWN_ROOT
        if path == GROUP_ROOT or path.startswith(GROUP_ROOT + "/"):
            return self.groups, GROUP_ROOT
        return None, ""

    @staticmethod
    def _folder_key(path, root):
        rest = path[len(root):].strip("/")
        return unquote(rest)

    def _entry_path(self, root, folder, name):
        parts = [part for part in (folder, name) if part]
        return root + "/" + "/".join(quote(part) for part in "/".join(parts).split("/"))

    def file_rows(self, root, folder, entries):
        if not entries:
            return "<tr><td colspan='9'>Keine Dateien</td></tr>"
        rows = []
        for entry in entries:
            path = self._entry_path(root, folder, entry["name"])
            icon = "fa fa-folder" if entry["folder"] else "fa fa-file"
            stamp = entry["date"]
            day, clock = stamp.split(" ")
            year, month, date = day.split("-")
            shown = "%s.%s.%s %s" % (date, month, year, clock)
            rows.append(
                "<tr><td><input type='checkbox' name='form[files][]' value='%s'></td>"
                "<td><span class='%s'></span></td>"
                "<td><a href='%s'>%s</a></td><td>%s</td><td>%s</td>"
                "<td data-sort='%s'>%s</td>"
                "<td><a class='dropdown-toggle' href='#'>...</a></td><td></td><td></td></tr>"
                % (escape(entry["name"]), icon, escape(path), escape(entry["name"]), escape(entry.get("size", "")),
                   "Ordner" if entry["folder"] else escape(entry.get("type", "")), stamp, shown)
            )
        return "".join(rows)

    def file_page(self, root, folder, rows=None, query=""):
        tree = self.own if root == OWN_ROOT else self.groups
        listed = tree.get(folder, [])
        crumbs = ["<li><a href='%s'>%s</a></li>" % (root, "Eigene" if root == OWN_ROOT else "Gruppen")]
        trail = ""
        for part in [part for part in folder.split("/") if part]:
            trail = (trail + "/" + part).strip("/")
            crumbs.append("<li><a href='%s'>%s</a></li>" % (escape(self._entry_path(root, "", trail)), escape(part)))
        location = "/" + ("Files" if root == OWN_ROOT else "Groups") + ("/" + folder if folder else "")
        upload = "" if root == GROUP_ROOT and not folder else (
            "<form id='file-upload' class='form-inline' action='/iserv/file/upload' method='post' enctype='multipart/form-data'>"
            "<label for='upload_file'>File *</label><input type='file' id='upload_file' name='upload[file][]' required multiple>"
            "<input type='hidden' name='upload[path]' value='%s'><button type='submit' name='upload[submit]'>Hochladen</button>"
            "<input type='hidden' name='upload[_token]' value='%s'></form>" % (escape(location), TOKEN)
        )
        search = (
            "<form id='file-search' class='form-inline' action='/iserv/file/search' method='post'>"
            "<input type='search' name='search[search]' required value='%s'><button type='submit' name='submit'>-</button>"
            "<input type='hidden' name='search[path]' value='%s'><button type='submit' name='search[actions][reset]'>Reset</button>"
            "<input type='hidden' name='search[_token]' value='%s'></form>" % (escape(query), escape(location), TOKEN)
        )
        options = "".join("<option value='%s'>%s</option>" % (value, value) for value in ACTION_OPTIONS)
        heads = "".join("<th>%s</th>" % escape(label) for label in FILE_HEADERS)
        body = (
            "<ol class='breadcrumb'>%s</ol>%s%s"
            "<form class='form-inline' action='%s' method='post'>"
            "<table id='files' class='table table-hover'><thead><tr>%s</tr></thead><tbody>%s</tbody></table>"
            "<button type='submit' name='form[delete]'>Löschen</button><button type='submit' name='form[confirm]'>OK</button>"
            "<select name='form[action]'>%s</select><select name='form[preview][size]'><option>1</option></select>"
            "<input type='hidden' name='form[path]' value='%s'><input type='hidden' name='form[current_search]' value=''>"
            "<input type='hidden' name='form[_token]' value='%s'></form>"
            "<a href='/iserv/file/-/Groups'>Gruppen</a><a href='/iserv/file/cloud'>Wolke</a><a href='/iserv/file/add/folder'>Neuer Ordner</a>"
        ) % ("".join(crumbs), upload, search, escape(self._entry_path(root, folder, "")), heads, self.file_rows(root, folder, listed) if rows is None else rows, options, escape(location), TOKEN)
        return page("Dateien", body)

    def book_page(self, path, query):
        people = self.people.get(path, [])
        wanted = query.casefold()
        shown = [person for person in people if not wanted or wanted in (person["first"] + " " + person["last"] + " " + person["address"]).casefold()]
        heads = "".join("<th>%s</th>" % escape(label) for label in BOOK_HEADERS)
        rows = "".join(
            "<tr><td><input type='checkbox' name='crud[multi][]' value='%d'></td><td><a href='%s/show/%d'>%s</a></td><td>%s</td>"
            "<td><a href='mailto:%s'>%s</a></td><td>%s</td><td></td></tr>"
            % (index, path, index, escape(person["last"]), escape(person["first"]), escape(person["address"]), escape(person["address"]), escape(person["class"]))
            for index, person in enumerate(shown, 1)
        )
        body = (
            "<ul class='nav nav-tabs'><li><a href='%s'>Privat</a></li><li><a href='%s'>Öffentlich</a></li>"
            "<li><a href='%s'>Verteiler</a></li></ul>"
            "<form class='form-inline' method='get'><input type='text' name='filter[search]' value='%s'></form>"
            "<table id='crud-table' class='table table-striped'><thead><tr>%s</tr></thead><tbody>%s</tbody></table>"
        ) % (PRIVATE_BOOK, PUBLIC_BOOK, BOOK_ROOT + "/mailinglist", escape(query), heads, rows)
        return page("Adressbuch", body)

    def list_page(self):
        heads = "".join("<th>%s</th>" % escape(label) for label in LIST_HEADERS)
        rows = "".join(
            "<tr><td><input type='checkbox' name='iserv_crud_multi_select[multi][]' value='%s'></td>"
            "<td><a href='%s/show/%s'>%s</a></td><td>%d</td><td><a href='%s/edit/%s'>Bearbeiten</a></td><td></td></tr>"
            % (entry["id"], LIST_ROOT, entry["id"], escape(entry["title"]), len(entry["addresses"]), LIST_ROOT, entry["id"])
            for entry in self.lists
        ) or "<tr><td colspan='5'>Keine Einträge</td></tr>"
        table = "<table id='crud-table' class='table table-striped'><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (heads, rows) if self.list_table else ""
        body = (
            "<form class='form-horizontal' action='%s/import' method='post' enctype='multipart/form-data'>"
            "<label for='list_title'>Titel</label><input type='text' id='list_title' name='form[list][title]'>"
            "<label for='list_upload'>Datei</label><input type='file' id='list_upload' name='form[list][upload]' required>"
            "<button type='submit' name='form[submit]'>Importieren</button><input type='hidden' name='form[_token]' value='%s'></form>"
            "<form action='%s/batch/confirm' method='post'>%s"
            "<button type='submit' name='iserv_crud_multi_select[actions][delete]'>Löschen</button>"
            "<input type='hidden' name='iserv_crud_multi_select[_token]' value='%s'></form><a href='%s/add'>Hinzufügen</a>"
        ) % (LIST_ROOT, TOKEN, LIST_ROOT, table, TOKEN, LIST_ROOT)
        return page("Verteilerlisten", body)

    def confirm_page(self, ids):
        chosen = [entry for entry in self.lists if entry["id"] in ids]
        hidden = "".join("<input type='hidden' name='iserv_crud_multi_select_confirm[multi][]' value='%s'>" % entry["id"] for entry in chosen)
        names = "".join("<li>%s</li>" % escape(entry["title"]) for entry in chosen)
        body = (
            "<p>Wollen Sie die folgenden Einträge wirklich löschen?</p><ul>%s</ul>"
            "<form action='%s/batch' method='post'>%s<input type='hidden' name='iserv_crud_multi_select_confirm[_token]' value='%s'>"
            "<button type='submit' name='iserv_crud_multi_select_confirm[cancel]'>Abbrechen</button>"
            "<button type='submit' name='iserv_crud_multi_select_confirm[confirm]'>Löschen</button></form>"
        ) % (names, LIST_ROOT, hidden, TOKEN)
        return page("Löschen bestätigen", body)

    def list_detail_page(self, ident):
        entry = next((item for item in self.lists if item["id"] == ident), None)
        if entry is None:
            return None
        rows = "".join("<tr><td><a href='mailto:%s'>%s</a></td></tr>" % (escape(address), escape(address)) for address in entry["addresses"])
        return page(entry["title"], "<table class='table'><tbody>%s</tbody></table>" % rows)

    def fetch(self, path, params=None):
        self.fetched.append((path, dict(params or {})))
        parts = urlsplit(path)
        path = parts.path.rstrip("/") or parts.path
        tree, root = self._tree(path)
        if tree is not None:
            folder = self._folder_key(path, root)
            if folder in self.broken_folders:
                return Answer(200, self.url(path), page("Dateien", "<p>Bitte warten</p>"))
            if folder in tree:
                return Answer(200, self.url(path), self.file_page(root, folder))
            return Answer(404, self.url(path), page("Nicht gefunden", ""))
        if path in ("/iserv", ""):
            return Answer(200, self.url("/iserv/"), page("IServ", ""))
        if path == BOOK_ROOT and not self.book_root_missing:
            return Answer(200, self.url(PRIVATE_BOOK), self.book_page(PRIVATE_BOOK, ""), history=[302])
        if path in (PRIVATE_BOOK, PUBLIC_BOOK):
            return Answer(200, self.url(path), self.book_page(path, str((params or {}).get("filter[search]") or "")))
        if path == LIST_ROOT:
            return Answer(200, self.url(path), self.list_page())
        if path.startswith(LIST_ROOT + "/show/"):
            found = self.list_detail_page(path.rsplit("/", 1)[-1])
            if found is not None:
                return Answer(200, self.url(path), found)
        return Answer(404, self.url(path), page("Nicht gefunden", ""))

    def fetch_or_raise(self, path, params=None):
        return self.fetch(path, params)

    def fetch_file(self, path, limit, timeout=60):
        tree, root = self._tree(path)
        if tree is not None:
            key = self._folder_key(path, root)
            folder, _, name = key.rpartition("/")
            entry = next((item for item in tree.get(folder, []) if item["name"] == name and not item["folder"]), None)
            if entry is not None:
                kind = "application/pdf" if name.endswith(".pdf") else "image/png" if name.endswith(".png") else "text/plain"
                return Answer(200, self.url(path), content=entry["data"], content_type=kind, disposition='attachment; filename="%s"' % name)
        return Answer(404, self.url(path), page("Nicht gefunden", ""))

    def post_form(self, url, data, files=None, headers=None, timeout=60):
        path = urlsplit(url).path
        pairs = list(data.items()) if isinstance(data, dict) else list(data or [])
        self.posts.append({"path": path, "data": pairs, "files": [(name, part[0], len(part[1])) for name, part in files or []]})
        values = {}
        for name, value in pairs:
            values.setdefault(name, []).append(value)
        if path == "/iserv/file/upload":
            return self._upload(values, files or [])
        if path == "/iserv/file/search":
            return self._search(values)
        if path == LIST_ROOT + "/import":
            return self._import(values, files or [])
        if path == LIST_ROOT + "/batch/confirm":
            ids = values.get("iserv_crud_multi_select[multi][]", [])
            if values.get("iserv_crud_multi_select[_token]") != [TOKEN] or "iserv_crud_multi_select[actions][delete]" not in values:
                return Answer(400, url, page("Fehler", "<div class='alert alert-danger'>Ungültig</div>"))
            if self.delete_asks:
                return Answer(200, url, self.confirm_page(ids + self.confirm_extra), history=[302] if self.confirm_redirected else [])
            self.lists = [entry for entry in self.lists if entry["id"] not in ids]
            return Answer(200, self.url(LIST_ROOT), self.list_page(), history=[302])
        if path == LIST_ROOT + "/batch":
            if "iserv_crud_multi_select_confirm[confirm]" in values and values.get("iserv_crud_multi_select_confirm[_token]") == [TOKEN]:
                ids = values.get("iserv_crud_multi_select_confirm[multi][]", []) + self.delete_also
                self.lists = [entry for entry in self.lists if entry["id"] not in ids]
            return Answer(200, self.url(LIST_ROOT), self.list_page(), history=[302])
        return Answer(404, url, page("Nicht gefunden", ""))

    def _upload(self, values, files):
        if self.upload_refused:
            return Answer(400, self.url("/iserv/file/upload"), page("Fehler", "<div class='alert alert-danger'>Die Datei ist zu groß.</div>"))
        if values.get("upload[_token]") != [TOKEN]:
            return Answer(400, self.url("/iserv/file/upload"), page("Fehler", "<div class='alert alert-danger'>Token</div>"))
        location = (values.get("upload[path]") or ["/Files"])[0]
        group = location.startswith("/Groups")
        tree, root = (self.groups, GROUP_ROOT) if group else (self.own, OWN_ROOT)
        folder = location[len("/Groups" if group else "/Files"):].strip("/")
        if not self.upload_ignored:
            for name, part in files:
                if name == "upload[file][]":
                    stored = part[0].replace(".", " (1).", 1) if self.rename_uploads else part[0]
                    tree.setdefault(folder, []).append({"name": stored, "folder": False, "size": "1 KB", "type": "Datei", "date": "2026-10-16 09:00", "data": part[1]})
        path = root + ("/" + quote(folder) if folder else "")
        return Answer(200, self.url(path), self.file_page(root, folder), history=[302])

    def _search(self, values):
        wanted = (values.get("search[search]") or [""])[0].casefold()
        rows = "".join(
            self.file_rows(OWN_ROOT, folder, [entry])
            for folder, entries in self.own.items()
            for entry in entries
            if wanted and wanted in entry["name"].casefold()
        )
        return Answer(200, self.url("/iserv/file/search"), self.file_page(OWN_ROOT, "", rows=rows or self.file_rows(OWN_ROOT, "", []), query=wanted))

    def _import(self, values, files):
        if values.get("form[_token]") != [TOKEN]:
            return Answer(400, self.url(LIST_ROOT + "/import"), page("Fehler", "<div class='alert alert-danger'>Token</div>"))
        upload = next((part for name, part in files if name == "form[list][upload]"), None)
        if upload is None:
            return Answer(400, self.url(LIST_ROOT + "/import"), page("Fehler", "<div class='alert alert-danger'>Datei fehlt</div>"))
        title = (values.get("form[list][title]") or [""])[0] or (upload[0] if self.title_with_extension else upload[0].rsplit(".", 1)[0])
        lines = [line.strip() for line in upload[1].decode("utf-8", "replace").splitlines() if line.strip()]
        self.next_list += 1
        if self.import_ignored:
            return Answer(200, self.url(LIST_ROOT), self.list_page(), history=[302])
        self.lists.append({"id": str(self.next_list), "title": title, "addresses": lines})
        return Answer(200, self.url(LIST_ROOT), self.list_page(), history=[302])
