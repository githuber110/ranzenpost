CURRENT = "current"
OBSOLETE = "obsolete"
NEW = "new"
CATALOGUE = {
    "absence": ("Abwesenheiten", "Absences", CURRENT),
    "absence_obsolete": ("Abwesenheiten (veraltet)", "Absences (obsolete)", OBSOLETE),
    "addressbook": ("Adressbuch", "Address book", CURRENT),
    "exercise": ("Aufgaben", "Tasks", CURRENT),
    "bildungslogin-iserv": ("BILDUNGSLOGIN", "BILDUNGSLOGIN", CURRENT),
    "brockhaus": ("Brockhaus", "Brockhaus", CURRENT),
    "booking": ("Buchungen", "Bookings", CURRENT),
    "casio-education-iserv": ("CASIO Education", "CASIO Education", CURRENT),
    "curriculum": ("Curriculum", "Curriculum", CURRENT),
    "file": ("Dateien", "Files", CURRENT),
    "print": ("Drucken", "Printing", CURRENT),
    "mail": ("E-Mail", "Email", CURRENT),
    "restricted-shares": ("Eingeschränkte Netzlaufwerke", "Restricted network shares", CURRENT),
    "edupool": ("Edupool", "Edupool", CURRENT),
    "parentletter": ("Elternbriefe", "Parent letters", CURRENT),
    "parentconference": ("Elternsprechtage", "Parent-teacher conference days", CURRENT),
    "europalehrmittel-europathek": ("Europathek", "Europathek", CURRENT),
    "forum": ("Forum", "Forum", CURRENT),
    "dsa-daycare": ("Ganztag", "All-day care", CURRENT),
    "computer-request": ("Gerätebewerbung", "Device application", CURRENT),
    "computer": ("Gerätesteuerung", "Device control", CURRENT),
    "idm": ("Identitätsmanagement", "Identity management", CURRENT),
    "infodisplay": ("Infobildschirm", "Info display", CURRENT),
    "calendar": ("Kalender", "Calendar", CURRENT),
    "dsa-classregister": ("Klassenbuch", "Class register", CURRENT),
    "klassengeld": ("Klassengeld", "Class money", CURRENT),
    "exam-plan": ("Klausurplan", "Exam schedule", CURRENT),
    "knowledgebase": ("Knowledge-Base", "Knowledge base", CURRENT),
    "course-selection": ("Kurswahlen", "Course selection", CURRENT),
    "dsa-lists": ("Listen", "Lists", CURRENT),
    "messenger": ("Messenger", "Messenger", CURRENT),
    "methodenguide": ("MethodenGuide", "MethodenGuide", CURRENT),
    "mdm": ("Mobilgerätesteuerung", "Mobile device management", CURRENT),
    "moinschule": ("moin.schule-Konnektor", "moin.schule connector", CURRENT),
    "news": ("News", "News", CURRENT),
    "office": ("Office", "Office", CURRENT),
    "onlinemedia": ("Online-Medien", "Online media", CURRENT),
    "dsa-pinboard": ("Pinnwände", "Pinboards", CURRENT),
    "plan": ("Pläne", "Plans", CURRENT),
    "feedback": ("Rückmeldung", "Feedback", CURRENT),
    "poll-quick": ("Schnellumfragen", "Quick polls", CURRENT),
    "schuelerkarriere": ("Berufsorientierung von Schülerkarriere", "Career guidance by Schülerkarriere", CURRENT),
    "scobees": ("Scobees", "Scobees", CURRENT),
    "report": ("Störungsmeldung", "Fault report", CURRENT),
    "timetable": ("Stundenplan (veraltet)", "Timetable (obsolete)", OBSOLETE),
    "dsa-timetable": ("Stunden- und Vertretungsplan (neu)", "Timetable and substitutions (new)", NEW),
    "dsa-timetabling": ("Stundenplanung", "Timetable planning", CURRENT),
    "excalidraw": ("Tafeln", "Whiteboards", CURRENT),
    "etherpad": ("Texte", "Texts", CURRENT),
    "todo": ("To-do", "To-do", CURRENT),
    "poll": ("Umfragen", "Polls", CURRENT),
    "mailinglist": ("Verteilerlisten", "Mailing lists", CURRENT),
    "videoconference": ("Videokonferenzen", "Video conferences", CURRENT),
    "westermann": ("Westermann", "Westermann", CURRENT),
    "webuntis": ("WebUntis Messenger", "WebUntis Messenger", CURRENT),
    "cloudfiles": ("Wolke", "Cloud", CURRENT),
}
SEGMENT_SLUGS = {
    "time-table": "timetable",
    "dsa-absences": "absence",
}


def slug_of(segment):
    segment = str(segment or "").strip().lower()
    slug = SEGMENT_SLUGS.get(segment, segment)
    return slug if slug in CATALOGUE else ""


def official_name(slug):
    entry = CATALOGUE.get(slug)
    return entry[0] if entry else ""


def english_label(slug):
    entry = CATALOGUE.get(slug)
    return entry[1] if entry else ""


def edition_of(slug):
    entry = CATALOGUE.get(slug)
    return entry[2] if entry else ""
