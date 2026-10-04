"""Effective limits for the XX. district KÉSZ: what the body text does to the 1. melléklet table.

Reviewed by hand against the consolidated text (2026-04-03). Each entry names the paragraph it comes
from; the extractor resolves that to a verified citation.

HEIGHT_MEANING: the table's "beépítési magasság" is applied per the building mode (15. §).
OVERRIDES: per zone, a parameter's value under a condition:
  None                                   always
  {"type": "along", "street": S}         plot row along street S (first row of plots)
  {"type": "parallel", "street": S}      plot rows on streets parallel to S (not along S itself)
  {"type": "block", "ring": [streets]}   inside the block bounded by these streets (in order)
  {"type": "manual", "text": ...}        depends on the plot/project: shown, not evaluated
params: table keys (maxCoveragePct, minGreenPct, minPlotM2, maxFar, maxFarParking, buildingMode),
"height" / "minHeight" with explicit "cornice" (párkánymagasság), "building" (épületmagasság), "peak"
(legmagasabb pont) values ("table" = the table value, "+x m" with "delta" = table value + x), or
extra rows: setbacks, units, buildings, all (= every table value).
"""

HEIGHT_MEANING = [
    {"mode": "zártsorú", "meaning": "párkánymagasság", "para": "15. § (1)",
     "text": "Zártsorú beépítésnél a táblázat beépítési magassága párkánymagasság."},
    {"mode": "oldalhatáron", "meaning": "párkánymagasság", "para": "15. § (2)",
     "text": "Oldalhatáron álló beépítésnél a beépítési magasság párkánymagasság; a tűzfal legfeljebb 7,5 m magas lehet."},
    {"mode": "ikres", "meaning": "a csatlakozó főépítmény szerinti, ennek hiányában párkánymagasság", "para": "15. § (3)",
     "text": "Ikres beépítésnél az épületmagasság a csatlakozó főépítmény szerinti; ha nincs, a beépítési magasság párkánymagasság."},
    {"mode": "szabadonálló", "meaning": "épületmagasság", "para": "15. § (4)",
     "text": "Szabadonálló beépítésnél a beépítési magasság épületmagasság; közeli lakószomszéd felé a homlokzat párkánymagassága nem haladhatja meg a beépítési magasságot."},
]

HATAR = "Határ út"
K_ZONES = ["Lk-1/K1", "Lk-1/K2", "Lk-2/K", "Lke-1/K1", "Lke-1/K2", "Vi-2/L-K1", "Vi-2/L-K2"]
KIALAKULT = ["Ln-T/SZ1", "Ln-T/G", "Lk-1/Z", "Lk-T/3", "Vi-3/G", "Vt-H/Lk-KSZ"]
BLOCK_1A = ["Ősz utca", "István utca", "Erdő utca", "János utca", "Török Flóris utca"]
BLOCK_1B = ["Török Flóris utca", "Székelyhíd utca", "Ady Endre utca", "Klapka utca"]


def per100(zones, para):
    return {"zones": zones, "param": "units", "value": "minden teljes 100 m² telekterület után 1 rendeltetési egység", "para": para}


OVERRIDES = [
    # --- Ln ------------------------------------------------------------------------------------
    {"zones": ["Ln-3/SZ1"], "param": "height", "cornice": "15,0 m", "peak": "19,0 m", "para": "24. § (2)"},
    {"zones": ["Ln-3/SZ1", "Ln-3/Z"], "param": "units", "value": "minden teljes 75 m² telekterület után 1 rendeltetési egység", "para": "24. § (2)"},
    {"zones": ["Ln-3/SZ3"], "param": "setbacks", "value": "előkert a János utca felé 3,0 m, a Széchenyi utca felé min. 10,0 m; oldalkert a János utcára merőleges telekhatárnál 8,5 m, a Széchenyi utcára merőlegesnél 0,5 m", "para": "24. § (4)"},
    {"zones": ["Ln-3/Z"], "param": "setbacks", "value": "új épület a szomszédos tűzfalas főépítményhez azonos előkerttel csatlakozzon", "para": "24. § (5)"},
    {"zones": ["Ln-T/SZ5"], "param": "height", "building": "table", "cornice": "19,5 m", "para": "25. § (12a)"},
    {"zones": ["Ln-T/SZ5"], "param": "maxFarParking", "value": "csak terepszint alatti beépítés esetén használható fel", "para": "25. § (12a)"},
    {"zones": ["Ln-T/SZ1", "Ln-T/SZ2", "Ln-T/SZ3"], "param": "units", "value": "a meglévő rendeltetési egységek száma nem növelhető", "para": "25. § (12)"},

    # --- "kialakult": existing values are the limits ----------------------------------------------
    {"zones": ["Ln-T/SZ1", "Ln-T/G"], "param": "all", "value": "kialakult: a meglévő legnagyobb értékek nem növelhetők, a legkisebbek nem csökkenthetők", "para": "25. § (13)"},
    {"zones": ["Lk-1/Z"], "param": "all", "value": "kialakult: a meglévő legnagyobb értékek nem növelhetők, a legkisebbek nem csökkenthetők", "para": "29. § (11)"},
    {"zones": ["Lk-T/3"], "param": "all", "value": "kialakult: a meglévő legnagyobb értékek nem növelhetők, a legkisebbek nem csökkenthetők", "para": "31. § (8)"},
    {"zones": ["Vi-3/G"], "param": "all", "value": "kialakult: a meglévő legnagyobb értékek nem növelhetők, a legkisebbek nem csökkenthetők", "para": "38. § (6a)"},
    {"zones": ["Vt-H/Lk-KSZ"], "param": "all", "value": "kialakult (az 1. melléklettől eltérően); a beépítettség utólagos hőszigeteléssel növelhető; a teljes telek építési hely", "para": "35. § (7)"},

    # --- Lk-1/K, Lk-2/K, Lke-1/K (+ Vi-2/L-K): 26.–27. § ------------------------------------------
    {"zones": K_ZONES, "param": "buildingMode", "value": "16,0 m vagy keskenyebb telken oldalhatáron álló, ikres vagy zártsorú; 16,0 m-nél szélesebb telken új épületnél takaratlan tűzfal nem építhető; zártsorú új épületszárny max. 16 m", "para": "26. § (1)"},
    {"zones": K_ZONES, "param": "setbacks", "value": "előkert 0,0 m; ha a szomszédok homlokvonala 5,0 m-en belül van, az egyik szomszéd homloksíkjához kell igazodni, egyébként 5,0 m", "para": "26. § (2)"},
    {"zones": K_ZONES, "param": "setbacks", "value": "hátsókert 0,0 m, de 16–21 m telekmélységnél a hátsó 3,0 m-es, 21 m felett a hátsó 6,0 m-es sávban újonnan csak gépjárműtároló, hulladéktartály-tároló, kerti építmény", "para": "26. § (4)"},
    {"zones": K_ZONES, "param": "height", "peak": "7,5 m", "para": "26. § (6)",
     "condition": {"type": "manual", "text": "a hátsó telekhatártól mért 3,0 m-es (16–21 m telekmélységnél) vagy 6,0 m-es (21 m felett) sávban, illetve 16 m-nél kisebb telekmélységnél a hátsó telekhatáron álló lakóépület bővítésénél"}},
    {"zones": K_ZONES, "param": "units", "value": "300 m² alatt 1; 300–600 m² között 2; 600 m² felett 200 m²-enként 1 önálló rendeltetési egység", "para": "27. § (1)"},
    {"zones": K_ZONES, "param": "units", "value": "minden teljes 70 m² telekterület után 1 önálló rendeltetési egység", "para": "27. § (1)",
     "condition": {"type": "along", "street": "Helsinki út"}},
    {"zones": K_ZONES, "param": "buildings", "value": "két épület csak 900 m²-nél nagyobb telken", "para": "27. § (2)"},
    {"zones": ["Lk-1/K1", "Lk-1/K2"], "param": "units", "value": "tetőtér-átépítésnél a tetőtérben legfeljebb két új rendeltetési egység, a telekmérettől függetlenül", "para": "27. § (1)",
     "condition": {"type": "block", "ring": BLOCK_1A}},
    {"zones": ["Lk-1/K1", "Lk-1/K2"], "param": "height", "cornice": "+2,0 m", "delta": 2.0, "note": "zártsorú beépítésnél, az utcafronti szárny udvari homlokzatán", "para": "29. § (1a)",
     "condition": {"type": "block", "ring": BLOCK_1A}},
    {"zones": ["Lk-1/K2"], "param": "height", "cornice": "+3,0 m", "building": "+3,0 m", "delta": 3.0, "para": "29. § (1b)",
     "condition": {"type": "block", "ring": BLOCK_1B}},
    {"zones": ["Lk-1/K2"], "param": "units", "value": "minden teljes 70 m² telekterület után 1 önálló rendeltetési egység", "para": "29. § (1b)",
     "condition": {"type": "block", "ring": BLOCK_1B}},

    # --- Lk ------------------------------------------------------------------------------------
    {"zones": ["Lk-1/SZ1", "Lk-1/SZ4"], "param": "units", "value": "a meglévő rendeltetési egységek száma nem növelhető", "para": "29. § (2a)"},
    per100(["Lk-1/SZ2"], "29. § (3)"),
    per100(["Lk-2/SZ"], "30. § (2)"),
    {"zones": ["Lk-T/1", "Lk-T/2", "Lk-T/3", "Lk-T/4"], "param": "units", "value": "a meglévő rendeltetési egységek száma nem növelhető", "para": "31. § (3a)"},

    # --- Lke-1 ---------------------------------------------------------------------------------
    {"zones": ["Lke-1/SZ1", "Lke-1/SZ3", "Lke-1/SZ5"], "param": "minPlotM2", "value": "telekszélesség min. 16,0 m, saroktelken min. 18,0 m", "para": "33. § (3)"},
    {"zones": ["Lke-1/SZ1", "Lke-1/SZ3"], "param": "buildings", "value": "minden megkezdett 800 m² után 1 épület, épületenként max. 250 m² bruttó alapterület; épületek között min. 7,5 m", "para": "33. § (3)"},
    {"zones": ["Lke-1/SZ1", "Lke-1/SZ3"], "param": "units", "value": "épületenként legfeljebb 4 rendeltetési egység", "para": "33. § (3)"},
    {"zones": ["Lke-1/SZ4"], "param": "units", "value": "épületenként legfeljebb 8 rendeltetési egység", "para": "33. § (3a)"},
    {"zones": ["Lke-1/SZ4"], "param": "minPlotM2", "value": "min. 300 m², ha a telekalakítás a kialakult kerítésvonal mentén történik", "para": "33. § (3a)",
     "condition": {"type": "manual", "text": "kialakult kerítésvonal menti telekalakításnál"}},
    {"zones": ["Lke-1/SZ5"], "param": "minGreenPct", "value": "a táblázat értéke 10 %-kal csökkenthető", "para": "33. § (3b)", "delta": -10,
     "condition": {"type": "manual", "text": "egy telken több épület elhelyezésénél"}},
    {"zones": ["Lke-1/SZ5"], "param": "buildings", "value": "minden megkezdett 700 m² után 1 épület, épületenként max. 250 m² bruttó alapterület; épületek között min. 7,5 m", "para": "33. § (3b)"},
    {"zones": ["Lke-1/SZ5"], "param": "units", "value": "épületenként legfeljebb 8 rendeltetési egység", "para": "33. § (3b)"},
    per100(["Lke-1/SZ2"], "33. § (4)"),
    {"zones": ["Lke-1/Z"], "param": "setbacks", "value": "előkert 5,0 m, hátsókert 5,0 m", "para": "33. § (5)"},
    {"zones": ["Lke-1/Z"], "param": "units", "value": "telkenként 1 lakás", "para": "33. § (5)"},

    # --- Vt-H ----------------------------------------------------------------------------------
    per100(["Vt-H/Lk1"], "35. § (5)"),
    {"zones": ["Vt-H/Ln-KSZ"], "param": "maxCoveragePct", "value": "100 % csak a földszinten és az első emeleten; fölötte max. 80 %", "para": "35. § (12)"},

    # --- Vi-2 ----------------------------------------------------------------------------------
    per100(["Vi-2/L-K1", "Vi-2/L-K2", "Vi-2/L-SZ1", "Vi-2/L-SZ2", "Vi-2/L-Z2", "Vi-2/L-Z3", "Vi-2/L-Z4"], "36. § (4a)"),
    per100(["Vi-2/SZ", "Vi-2/Z"], "37. § (1)"),
    {"zones": ["Vi-2/L-Z1"], "param": "units", "value": "minden teljes 70 m² telekterület után 1 lakás; földszinten lakás nem létesíthető", "para": "36. § (8)",
     "condition": {"type": "along", "street": HATAR}},
    {"zones": ["Vi-2/L-Z1"], "param": "minHeight", "building": "7,5 m", "para": "36. § (8)",
     "condition": {"type": "along", "street": HATAR}},
    {"zones": ["Vi-2/L-Z1"], "param": "minHeight", "building": "4,5 m", "para": "36. § (8)",
     "condition": {"type": "not-along", "street": HATAR}},
    {"zones": ["Vi-2/L-Z1"], "param": "height", "building": "9,0 m", "cornice": "6,5 m", "note": "a párkánymagasság a közterület felé néző homlokzatra vonatkozik", "para": "36. § (8)",
     "condition": {"type": "parallel", "street": HATAR}},
    {"zones": ["Vi-2/L-Z1"], "param": "setbacks", "value": "előkert 5,0 m", "para": "36. § (8)",
     "condition": {"type": "parallel", "street": HATAR}},
    # The table row itself makes the mode depend on the street ("zártsorú, a Határ úttal párhuzamos utcákban …").
    {"zones": ["Vi-2/L-Z1"], "param": "buildingMode", "value": "oldalhatáron álló vagy ikres", "para": "table",
     "condition": {"type": "parallel", "street": HATAR}},
    {"zones": ["Vi-2/L-Z1"], "param": "buildingMode", "value": "zártsorú", "para": "table",
     "condition": {"type": "not-parallel", "street": HATAR}},

    # --- Gksz ----------------------------------------------------------------------------------
    {"zones": ["Gksz-1/7"], "param": "setbacks", "value": "előkert 5,0 m, oldalkert 7,5 m, hátsókert 10 m", "para": "41. § (4a)"},
]
