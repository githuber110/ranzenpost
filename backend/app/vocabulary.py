import re
import unicodedata

from .module_catalogue import CATALOGUE

TOKEN = re.compile(r"[^\W_]+")
UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
ASCII_LETTERS = {"ß": "ss", "ı": "i", "ł": "l", "ø": "o", "đ": "d", "æ": "ae", "œ": "oe", "þ": "th"}

ROUTE_WORDS = """
iserv idesk api app apps matrix client static assets js css img fonts vendor chunk main index show list edit new
save delete create update view detail details data meta time table timetable dsa pinboard pinboards absence absences
sicknotes sicknote userselection requesttoschools schoolsettings school settings current slots dieschulapp messenger
authenticate auth login logout token tokens profile public file files user users calendar mail videoconference rooms room
members member sync typing reports report close unread chat standalone before after cap parent parents parentletter
letter letters parentconference conference conferences attendee attendees portal home dashboard account admin help
imprint legal notification notifications privacy search plan plans exam exams exercise exercises news message
messages inbox outbox folder folders attachment attachments download upload preview print archive archived read
confirm confirmation filter filters week day days month year entry entries item items id ids type types status
state states version versions config configuration module modules group groups class classes course courses subject
subjects teacher teachers student students child children lesson lessons period periods substitution substitutions
change changes cancelled cancellation event events appointment appointments json html text plain xml http https www
""".split()

UI_WORDS = """
titel kind kinder absender weitere empfaenger empfänger veroeffentlicht veröffentlicht datum betreff stundenplan
kalender e mail videokonferenzen elternbriefe elternbrief pinnwände pinnwand pinnwaende abwesenheiten abwesenheit
elternsprechtage elternsprechtag nachrichten nachricht aktionen aktion typ art status name beschreibung bemerkung
bemerkungen kommentar kommentare stunde stunden zeit uhrzeit fach faecher fächer lehrer lehrkraft lehrkräfte raum
räume klasse klassen kurs kurse vertretung vertretungen entfall ausfall aenderung änderung aenderungen änderungen
kombiniert woche wochen diese nächste naechste letzte tag tage heute von bis ab uhr gelesen ungelesen neu alle keine
anhang anhänge anhaenge datei dateien grund zeitraum eingereicht gemeldet bestätigt bestaetigt offen erledigt ja nein
montag dienstag mittwoch donnerstag freitag samstag sonntag januar februar märz maerz april mai juni juli august
september oktober november dezember termin termine ort raumnummer eltern schüler schueler schülerin schuelerin
von an und oder mit ohne für fuer der die das den dem des ein eine einer
title sender recipient recipients published date subject time room teacher class course action actions description
note notes comment comments reason period from to until all none new read unread yes no open done
monday tuesday wednesday thursday friday saturday sunday january february march may june july october december
""".split()

MARKER_WORDS = """
child teacher school user secret host email phone name key word seg file uuid date hex n expr hash root query
""".split()


def fold_variants(token):
    lowered = token.casefold()
    variants = {lowered}
    expanded = "".join(UMLAUTS.get(char, char) for char in lowered)
    variants.add(expanded)
    stripped = unicodedata.normalize("NFKD", "".join(ASCII_LETTERS.get(char, char) for char in lowered))
    variants.add("".join(char for char in stripped if not unicodedata.combining(char)))
    return variants


def _catalogue_words():
    words = set()
    for slug, entry in CATALOGUE.items():
        words.update(TOKEN.findall(slug))
        for text in entry[:2]:
            words.update(TOKEN.findall(str(text)))
    return words


def _build():
    words = set()
    for word in ROUTE_WORDS + UI_WORDS + MARKER_WORDS + sorted(_catalogue_words()):
        words.update(fold_variants(word))
    return frozenset(words)


WORDS = _build()


def known_word(token):
    return any(variant in WORDS for variant in fold_variants(token))
