"""Reviewed scope corrections for the XX. district KÉSZ (26/2015. (X. 21.)).

Automatic scoping (zone codes named in a paragraph, else its heading) is right for most paragraphs.
These entries fix the ones where it is wrong or too coarse; each was checked against the text.

zones: list of codes, a regex matched against whole codes, or "*" for every zone.
mode:  instead of zones, every zone whose table "beépítési mód" contains this word (plus zones
       where the mode is not fixed, "---", since it then follows the existing building: 26. § (1)).
kind:  zone | category | mode | general | public
"""
SKIP = {"2. §"}                      # definitions: a glossary, not rules for a site
SKIP_PREFIX = ("77. §", "78. §")     # entry into force, repealed decrees

BUILT = r"(Ln|Lke|Lk|Vt|Vi|Gksz)-.*|K-.*"          # Második rész: beépítésre szánt területek
PUBLIC = r"KÖu-.*|KÖk|Kt-.*|Zkp-.*"                # közterületek
GREEN = r"Zkp-.*|Kt-Zk-.*|Kt-Fk-.*"
K_ZONES = ["Lk-1/K1", "Lk-1/K2", "Lk-2/K", "Lke-1/K1", "Lke-1/K2", "Vi-2/L-K1", "Vi-2/L-K2"]  # 26. § + 36. § (5) a)


def _all(ids, **kw):
    return {i: kw for i in ids}


OVERRIDES = {
    # II. Fejezet – public space: pavilions, terraces, street trees.
    **_all(["3. § (1)", "3. § (2)", "3. § (3)", "3. § (4)", "3. § (5)", "4. § (1)", "4. § (3)", "4. § (4)",
            "4. § (5)", "4. § (6)", "4. § (7)", "4. § (8)"], zones=PUBLIC, kind="public"),
    "7. § (2)": {"zones": "*", "kind": "general", "conditional": True,
                 "note": "Csak a 2.b mellékleten feltöltöttnek jelölt területen."},
    "9. § (1)": {"zones": "*", "kind": "general", "conditional": False},
    "10. § (2)": {"zones": "*", "kind": "general", "conditional": True},

    # 15. § – the table's "beépítési magasság" means cornice or building height depending on the mode.
    "15. § (1)": {"mode": "zártsorú", "kind": "mode"},
    "15. § (2)": {"mode": "oldalhatáron", "kind": "mode"},
    "15. § (3)": {"mode": "ikres", "kind": "mode"},
    "15. § (4)": {"mode": "szabadonálló", "kind": "mode"},

    "18. §": {"zones": "*", "kind": "general"},
    **_all(["22. § (1)", "22. § (3)", "22/A. §"], zones=BUILT, kind="general"),
    **_all(["22. § (2)", "22. § (4)"], zones=BUILT, kind="general", conditional=True),
    "23. § (1)": {"zones": r"Ln-.*", "kind": "category", "flags": []},
    "24. § (5)": {"zones": ["Ln-3/Z"], "kind": "zone", "flags": ["setbacks", "units"]},

    # 26.–27. § – Lk-1/K, Lk-2/K, Lke-1/K, and Vi-2/L-K through 36. § (5) a).
    **_all(["26. § (1)", "26. § (2)", "26. § (3)", "26. § (4)", "26. § (5)", "26. § (6)", "26. § (7)", "27. § (2)"],
           zones=K_ZONES, kind="category"),
    "27. § (1)": {"zones": K_ZONES, "kind": "category", "conditional": False,
                  "note": "Az e) pont csak az Ősz u. – István u. – Erdő u. – János u. – Török Flóris u. által határolt területre vonatkozik."},
    "32. § (1)": {"zones": r"Lke-.*", "kind": "category", "flags": []},
    "33. § (1)": {"zones": ["Lke-1/K1", "Lke-1/K2"], "kind": "zone", "conditional": False,
                  "note": "A d) pont csak a Kéreg utca menti ingatlanokra vonatkozik."},
    "33. § (7)": {"zones": ["Lke-1/KSZ1", "Lke-1/KSZ2"], "kind": "zone", "conditional": False,
                  "note": "A b)–c) pont a Fiume utca menti telkekre, a d) pont a 182098/142 hrsz.-ú telekre vonatkozik."},
    "35. § (6)": {"zones": ["Vt-H/Lk2"], "kind": "zone", "conditional": False,
                  "note": "A c) pont a Kossuth Lajos utca menti épülettraktusokra vonatkozik."},
    "36. § (8)": {"zones": ["Vi-2/L-Z1"], "kind": "zone", "conditional": False,
                  "note": "Az a), c), d) pont a Határ út menti, az f) pont a Határ úttal párhuzamos utcák teleksorára vonatkozik."},

    # XV. Fejezet – the heading names no code.
    **_all(["39. § (1)", "39. § (2)", "39. § (3)"], zones=r"Gksz-.*", kind="category"),
    "43. § (1)": {"zones": r"Gksz-2/.*", "kind": "category"},
    "46. § (1)": {"zones": r"K-Rek/.*", "kind": "category"},

    # XVII. Fejezet – transport areas.
    "48. § (3)": {"zones": BUILT, "kind": "general", "conditional": True,
                  "note": "KÖu-2, KÖu-3, KÖu-4 övezettel határos, több közterülettel érintkező telekre."},
    "48. § (5)": {"zones": BUILT, "kind": "general", "flags": []},
    "48. § (7)": {"zones": "*", "kind": "general", "conditional": True},
    **_all(["49. § (1)", "49. § (2)", "49. § (3)"], zones=["KÖu-1"], kind="category"),
    **_all(["50. § (1)", "50. § (2)", "50. § (3)"], zones=["KÖu-2"], kind="category"),
    **_all(["52. § (1)", "52. § (2)", "52. § (3)"], zones=["KÖu-4"], kind="category"),
    **_all(["53. § (1)", "53. § (2)"], zones=["Kt-Kk"], kind="category"),
    **_all(["54. § (1)", "54. § (2)"], zones=["Kt-Kgy"], kind="category"),

    # XIX.–XXII. Fejezet – green, forest, agricultural and water areas.
    **_all(["63. § (1)", "63. § (2)", "63. § (3)", "63. § (4)"], zones=GREEN, kind="category"),
    "64. § (3)": {"zones": ["Zkp-Kp"], "kind": "zone",
                  "note": "A Vi-2/AE6 építési övezet határától mért 20 m-en belül."},
    **_all(["68. § (1)", "68. § (2)", "68. § (3)"], zones=["Ek-3"], kind="category"),
    **_all(["69. § (1)", "69. § (2)", "69. § (3)", "69. § (4)", "69. § (5)"], zones=["Ev-Ve"], kind="category"),
    **_all(["70. § (1)", "70. § (2)"], zones=["Má", "Mk"], kind="category"),
    "73. § (1)": {"zones": ["Vf", "Vá"], "kind": "category"},
    **_all(["74. § (1)", "74. § (2)"], zones=["Vf"], kind="category"),
    **_all(["75. § (1)", "75. § (2)", "75. § (3)", "75. § (4)"], zones=["Vá"], kind="category"),
}
