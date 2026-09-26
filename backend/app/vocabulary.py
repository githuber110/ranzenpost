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
members member sync typing reports report close unread chat standalone before after cap parent parents parentletter redirect
min bundle runtime polyfills polyfill legacy esm umd overview history today
projects project transactions transaction statements statement invoices invoice
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
archiv übersicht uebersicht liste listen weiter zurück zurueck vorherige startseite verlauf details alle
projekte projekt umsätze umsaetze buchungen kontoauszug rechnungen rechnung
title sender recipient recipients published date subject time room teacher class course action actions description
note notes comment comments reason period from to until all none new read unread yes no open done
monday tuesday wednesday thursday friday saturday sunday january february march may june july october december
""".split()

MARKER_WORDS = """
child teacher school user secret host email phone name key word seg file uuid date hex n expr hash root query
""".split()

HTML_WORDS = """
form forms input inputs button buttons btn submit reset crud multi select option options checkbox radio hidden textarea
label labels field fields fieldset legend control controls group nav navbar navigation main header footer sidebar menu
content contents container wrapper wrap inner outer row rows col cols column columns table tbl thead tbody tfoot th td tr
list lists item items card cards body panel panels modal dialog tab tabs pane panes grid badge badges icon icons fa fas far
text muted primary secondary success danger warning info light dark sm md lg xl xs block inline flex none pull left
right center middle top bottom start end clearfix active disabled show fade collapse collapsed dropdown toggle link links
pagination page pages alert alerts well box widget widgets section sections title subtitle heading headline filter search
admin csrf layout default custom no mb mt ms me mx my px py pb pt small large full width height auto
hover striped bordered condensed responsive sortable sort sorting asc desc selected checked required readonly
placeholder iserv
""".split()

API_WORDS = """
id ids uid name names title text body content created updated deleted modified at by date dates time times start end
begin from to until type types kind status state url urls link links href path file files size mime mimetype extension
filename width height color colour owner author user users student students child children course courses subject
subjects teacher teachers room rooms lesson lessons period periods week weeks day days entries entry items item data meta
count counts total page pages limit offset sort order filter is has can enabled active available visible read unread
seen new confirmed confirmation required main external internal display displayname forename surname first last full
short long label labels value values key keys code codes number numbers index position parent parents group groups class
classes school schools settings setting guardians guardian and for of in on with timetable substitutions substitution
initiating repeat request requests sick notes note plain changes change combined changed message messages event events
access refresh device home server homeserver sender recipients recipient attachments attachment tiles tile columns
column pinboard pinboards description reason comment comments tags tag category categories image images thumbnail preview
avatar email phone mobile address language locale timezone role roles permission permissions flag flags token csrf secret
session expires expiry format version api success error errors result results response params query payload map object
array php routing basepath authentication messenger matrix typing sync filter dow payment return x y empty pay amount balance iban fee price sum currency
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


IDENTIFIER_EXCLUDED = frozenset(
    """
    montag dienstag mittwoch donnerstag freitag samstag sonntag monday tuesday wednesday thursday friday saturday sunday
    januar februar märz maerz april mai juni juli august september oktober november dezember january february march may
    june july october december min art can kind page price root key day long short light field lehrer lehrkraft ort grund
    """.split()
)


def _build_identifiers():
    words = set()
    for word in ROUTE_WORDS + UI_WORDS + MARKER_WORDS + HTML_WORDS + API_WORDS:
        if word not in IDENTIFIER_EXCLUDED:
            words.update(fold_variants(word))
    return frozenset(words)


IDENTIFIER_WORDS = _build_identifiers()


def known_word(token):
    return any(variant in WORDS for variant in fold_variants(token))


def known_identifier(token):
    return any(variant in IDENTIFIER_WORDS for variant in fold_variants(token))
