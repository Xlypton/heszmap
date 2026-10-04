"""Reviewed scopes for the XX. district TKR (17/2019. (V.21.), in force from 2025-03-28).

scope: "area" (character-area rules, `areas` lists which), "all-areas" (every településképi
szempontból meghatározó terület = the whole district), "protected" (TSZ/VU/egyedi védett),
"device" (signs, AC units, solar, chimneys… everywhere), "procedure" (consultation, permits).
Paragraphs not listed (tasks of the office, awards, fines, entry into force) are left out.
"""
NJT_ID = "2019-17-SP-5Y269"
DISTRICT_QUERY = "XX. kerület, Budapest"

AREAS = {
    "kistelkes": "Kistelkes kertvárosi terület",
    "nagytelkes": "Nagytelkes kertvárosi terület",
    "kisvaros": "Kisvárosi terület",
    "keretes": "Városias, keretes jellegű terület",
    "lakotelep": "Lakótelepi karakterű terület",
    "kozpont": "Városközponti terület",
    "duna": "Duna-part",
    "zold": "Nagy területű zöldfelületekkel bíró terület",
}

# Best guess of the character area from the KÉSZ zone. The authoritative boundary is the TKR
# 1. melléklet map; the app labels this as an estimate and links the map.
ZONE_AREA = [
    [r"Lke-1/SZ.*", "nagytelkes"],
    [r"Lke-.*|Vi-2/L-K.*", "kistelkes"],
    [r"Lk-T/.*|Ln-T/.*", "lakotelep"],
    [r"Lk-.*|Vi-2/L-SZ.*|Vi-2/L-Z.*", "kisvaros"],
    [r"Vt-.*", "kozpont"],
    [r"Ln-3/.*", "keretes"],
    [r"Kt-Sv|Kt-St|Vá", "duna"],
    [r"Zkp-.*|Ek-.*|Ev-.*|K-Rek/.*|K-T", "zold"],
]

GARDEN = ["kistelkes", "nagytelkes", "kisvaros"]
SCOPES = {
    "12": {"scope": "protected", "protection": "TSZ"},
    "13": {"scope": "protected", "protection": "VU"},
    "14": {"scope": "protected", "protection": "egyedi"},
    "15": {"scope": "protected", "protection": "egyedi"},
    "16": {"scope": "protected", "protection": "egyedi"},
    "21": {"scope": "all-areas"},
    "22": {"scope": "all-areas"},
    "23": {"scope": "area", "areas": GARDEN},
    "24": {"scope": "area", "areas": GARDEN},
    "25": {"scope": "area", "areas": GARDEN},
    "26": {"scope": "area", "areas": GARDEN},
    "27": {"scope": "area", "areas": GARDEN},
    "28": {"scope": "area", "areas": ["kistelkes"]},
    "29": {"scope": "area", "areas": ["nagytelkes"]},
    "30": {"scope": "area", "areas": ["kisvaros"]},
    "30/A": {"scope": "area", "areas": ["kisvaros"]},
    "31": {"scope": "area", "areas": ["kozpont", "keretes"]},
    "32": {"scope": "area", "areas": ["kozpont", "keretes"]},
    "33": {"scope": "area", "areas": ["keretes"]},
    "34": {"scope": "area", "areas": ["lakotelep"]},
    "35": {"scope": "area", "areas": ["lakotelep"]},
    "36": {"scope": "area", "areas": ["duna"]},
    "37": {"scope": "area", "areas": ["zold"]},
    "38": {"scope": "device"},
    "40": {"scope": "device"},
    "42": {"scope": "device"},
    "43": {"scope": "device"},
    "44": {"scope": "device"},
    "45": {"scope": "device"},
    "46": {"scope": "device"},
    "47": {"scope": "procedure"},
    "48": {"scope": "procedure"},
    "50": {"scope": "procedure"},
    "51": {"scope": "procedure"},
    "52": {"scope": "procedure"},
}

# 2. melléklet: protected street sections. "between" = the cross streets bounding the section.
STREET_SECTIONS = [
    {"ref": "VU-1", "name": "Szent Imre herceg utca – János utcától a Rákóczi utcáig", "street": "Szent Imre herceg utca", "between": ["János utca", "Rákóczi utca"]},
    {"ref": "VU-2", "name": "Rákóczi utca – Szent Imre herceg utcától Kende Kanuth utcáig", "street": "Rákóczi utca", "between": ["Szent Imre herceg utca", "Kende Kanuth utca"]},
    {"ref": "VU-3", "name": "Hosszú utca – Kende Kanuth utcától Szent Imre herceg utcáig", "street": "Hosszú utca", "between": ["Kende Kanuth utca", "Szent Imre herceg utca"]},
    {"ref": "VU-4", "name": "Vécsey utca – Nagysándor József utcától a Dessewffy utcáig", "street": "Vécsey utca", "between": ["Nagysándor József utca", "Dessewffy utca"]},
    {"ref": "VU-5", "name": "Nagy Győri István utca – Zilah utcától Madách utcáig", "street": "Nagy Győry István utca", "between": ["Zilah utca", "Madách utca"]},
    {"ref": "VU-6", "name": "Téglagyártó út, Téglagyártó tér", "street": "Téglagyár tér"},
    {"ref": "VU-7", "name": "Kossuth Lajos utca páratlan oldal – Ady Endre utcától Kossuth Lajos térig", "street": "Kossuth Lajos utca", "between": ["Ady Endre utca", "Kossuth Lajos tér"], "side": "páratlan"},
    {"ref": "VU-8", "name": "Ady Endre utca páratlan oldal Kossuth Lajos utcától Berkenye sétányig", "street": "Ady Endre utca", "between": ["Kossuth Lajos utca", "Berkenye sétány"], "side": "páratlan"},
    {"ref": "VU-9", "name": "Sebestyén utca – egész", "street": "Sebestyén utca"},
    {"ref": "VU-10", "name": "Jókai utca Határ úttól – Kossuth Lajos utcáig", "street": "Jókai Mór utca", "between": ["Határ út", "Kossuth Lajos utca"]},
    {"ref": "VU-12", "name": "Dobos utca – Kende Kanuth utcától Jókai Mór utcáig", "street": "Dobos utca", "between": ["Kende Kanuth utca", "Jókai Mór utca"]},
    {"ref": "VU-13", "name": "Kossuth Lajos utca Nagy Győri István utca – Török Flóris utca közötti szakasza", "street": "Kossuth Lajos utca", "between": ["Nagy Győry István utca", "Török Flóris utca"]},
]

# Sections given by house numbers rather than cross streets.
VU_ADDRESSES = [
    {"ref": "VU-11", "name": "Baross utca 99-103.", "addresses": ["Baross utca 99", "Baross utca 101", "Baross utca 103"]},
]

# Protected town structure: the block bounded by these streets, in order around it.
TSZ = {"ref": "TSZ", "name": "Topánka utca – Jókai Mór utca – Nagysándor József utca – Baross utca által határolt terület",
       "ring": ["Topánka utca", "Jókai Mór utca", "Nagysándor József utca", "Baross utca"]}
