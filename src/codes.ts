/**
 * Plain-Hungarian meanings of the codes the regulations' zone tables print ("Z", "SZ", "K", "Kr.", "s75",
 * "É=12,5"), so the card can show "zártsorú" next to the code instead of the bare code (Peti, 2026-11-02).
 *
 * The meanings come from each regulation's own table legend or definitions, because the same letter can mean
 * different things in different plans: "S" is "szabadon álló" in Győr but "sorházas" in XXIII., and in XIV.
 * an "S" next to the green-area value means a sports-ground exception, not a corner plot. Areas whose legend
 * is not in the text layer of the PDF use the usual national meanings (Z, SZ, O, I/IK, K/KA), which every
 * legend we could read agrees on. A code we have no meaning for is shown as printed, never guessed.
 */

type Dict = Record<string, string>;

/** Hungarian-aware upper case for lookups ("Sz" -> "SZ", "Ikr" -> "IKR", "Kr." -> "KR"). */
const key = (s: string) => s.toLocaleUpperCase('hu-HU').replace(/\.$/, '');

// ---------------------------------------------------------------------------------------------------------
// Building mode (beépítési mód)

/** Meanings every legend we read agrees on. */
const MODE_BASE: Dict = {
  Z: 'zártsorú',
  SZ: 'szabadonálló',
  O: 'oldalhatáron álló',
  I: 'ikres',
  IK: 'ikres',
  IKR: 'ikres',
  K: 'kialakult',
  KA: 'kialakult',
  T: 'telepszerű',
  Ú: 'úszótelkes', // IV-5 legend "úszótelkes (Ú)"; XVI "SZ (Ú)", XI5 Ln-T "Ú"
  HZ: 'hézagosan zártsorú',
  ZU: 'zártudvaros zártsorú',
  ZK: 'zártsorú keretes',
  KE: 'keretes',
  C: 'csoportházas',
};

/** Per regulation (the key of its zone-types file), from that regulation's legend. */
const MODE_AREA: Record<string, Dict> = {
  // GYÉSZ beépítési módok: szabadon álló (S), oldalhatáron álló (O), zártsorú (Z), keretes (KE), zártudvaros (U),
  // ikres (I), csoportházas (C), telepszerű (T), kialakult (K), fésűs (F), hajlított (H), lakóparkos (LP), városi villás (V).
  gyor: { S: 'szabadon álló', U: 'zártudvaros', F: 'fésűs', H: 'hajlított', LP: 'lakóparkos', V: 'városi villás' },
  // 2. melléklet: "SZT - szabadonálló telepszerű, SZÁ - szabadonálló általános, O - oldalhatáron álló, Z - zártsorú,
  // ZK - zártsorú keretes, I- ikres". "SZA" is SZÁ without its accent in two rows.
  pecs: { SZT: 'szabadonálló telepszerű', SZÁ: 'szabadonálló általános', SZA: 'szabadonálló általános' },
  // 1. melléklet: "Z - általános zártsorú, ZU - zárt udvaros, ZK-A/B/C - zártsorú keretes „A”/„B”/„C” típus,
  // SZ - szabadonálló, IK - ikres, Z/SZ - zártsorú, szabadonálló jellegű épületelhelyezéssel, T - telepszerű, KA - kialakult állapot".
  xiii: {
    Z: 'általános zártsorú', ZU: 'zártudvaros zártsorú',
    'ZK-A': 'zártsorú keretes („A” típus)', 'ZK-B': 'zártsorú keretes („B” típus)', 'ZK-C': 'zártsorú keretes („C” típus)',
    'Z/SZ': 'zártsorú, szabadonálló jellegű épületelhelyezéssel', ZSZ: 'zártsorú, szabadonálló jellegű épületelhelyezéssel',
    KA: 'kialakult állapot',
  },
  // 2. melléklet: "HZ = Hézagosan zártsorú, HZO = Hézagosan zártsorú oldalhatáros, TU = telepszerű úszótelkes, U = úszótelkes".
  xv: { TU: 'telepszerű úszótelkes', HZO: 'hézagosan zártsorú, oldalhatáros', HZT: 'hézagosan zártsorú', U: 'úszótelkes' },
  // 6. § (1): zártsorú Z, szabadonálló SZ, oldalhatáron álló O, ikresen csatlakozó I, sorházas S.
  xxiii: { S: 'sorházas', I: 'ikresen csatlakozó' },
  // 2. melléklet: "SZ szabadon álló, O oldalhatáron álló, Ikr ikres, K kialakult állapot szerint". "SZO" is not in the
  // legend: read as the two modes it joins, and marked as our reading.
  xxi: { SZ: 'szabadon álló', K: 'kialakult állapot szerint', SZO: 'szabadon álló vagy oldalhatáron álló' },
  // 1. melléklet: "Kr." / "KR" rows: the area is regulated by a government decree (footnote 6, 69-72. §).
  i: { KR: 'a kormányrendelet szerint' },
};

/** Codes whose meaning is our reading, not the legend's: shown with a note. */
const MODE_READING: Record<string, string[]> = { xxi: ['SZO'] };

/** Whole cells the table's text layer splits or merges. */
const MODE_WHOLE: Record<string, Record<string, string>> = {
  // "SZ" printed across two lines next to the row ("S" above, "Z" below).
  xi9: { 'S Z': 'SZ' },
  // "SZ" above "Z" read as one word: two modes (the second with the "s" corner-plot values).
  viii: { SZZ: 'SZ Z' },
};

export interface ModeWords {
  /** The mode in words ("zártsorú"; "szabadonálló / zártsorú" when the table gives two). */
  words: string;
  /** The code as printed, to compare with the PDF. */
  code: string;
  /** The meaning is our reading of an undefined code. */
  reading?: boolean;
}

const LOWER = 'a-záéíóöőúüű';
const UPPER = 'A-ZÁÉÍÓÖŐÚÜŰ';

function modeCode(area: string, token: string): string | undefined {
  const k = key(token);
  return MODE_AREA[area]?.[k] ?? MODE_BASE[k];
}

/** The building mode in plain words, or undefined when the cell is empty, already words, or holds a code we
 *  cannot read (then the card shows it as printed). */
export function modeWords(area: string, raw: string): ModeWords | undefined {
  const text = raw.trim();
  if (!text || /^[-–‐—]+$/.test(text)) return undefined;
  // "S (szabadon álló)" (Győr) and "szabadonálló (SZ)" (IV.): words and code are both printed.
  let m = text.match(new RegExp(`^([${UPPER}][${UPPER}${LOWER}]{0,3})\\s*\\(([${LOWER}][${LOWER} ,]{3,})\\)$`));
  if (m) return { words: m[2], code: m[1] };
  m = text.match(new RegExp(`^([${UPPER}${LOWER}][${LOWER} ]{3,}?)\\s*\\(([${UPPER}]{1,3})\\)$`));
  if (m) return { words: m[1].replace(/^./, (c) => c.toLocaleLowerCase('hu-HU')), code: m[2] };
  // Already in words ("zártsorú", "kialakult úszótelkes", "zártsorú, a Határ úttal párhuzamos utcákban ...").
  if (new RegExp(`[${LOWER}]{4,}`).test(text)) return undefined;

  const norm = key(text).replace(/\s*\/\s*/g, '/');
  const whole = MODE_WHOLE[area]?.[text] ?? MODE_WHOLE[area]?.[norm];
  const src = whole ?? text;
  const direct = modeCode(area, key(src).replace(/\s*\/\s*/g, '/').replace(/\**$/, ''));
  if (direct) return { words: direct, code: whole ? src : text, reading: MODE_READING[area]?.includes(key(src)) || undefined };

  // Codes joined by "/", ",", a space (two lines of one cell), or one in brackets: "SZ (Ú)", "SZ, IK", "Z**, SZ".
  const re = new RegExp(`([${UPPER}${LOWER}]+(?:-[ABC])?\\.?)(\\**)|(\\(\\d+\\))|\\s*([/,])\\s*|(\\()|(\\))|(\\s+)`, 'gy');
  let out = '';
  let reading = false;
  let lastWasCode = false;
  let pos = 0;
  for (let t = re.exec(src); t && t.index === pos; t = re.exec(src)) {
    pos = re.lastIndex;
    if (t[1]) {
      const w = modeCode(area, t[1]);
      if (!w) return undefined;
      if (MODE_READING[area]?.includes(key(t[1]))) reading = true;
      out += w;
      lastWasCode = true;
    } else if (t[3]) {
      // "(1)": a footnote mark; stays visible in the printed code.
    } else if (t[4]) {
      out += t[4] === ',' ? ', ' : ' / ';
      lastWasCode = false;
    } else if (t[5]) {
      out += ' (';
      lastWasCode = false;
    } else if (t[6]) {
      out += ')';
    } else if (t[7]) {
      // Two codes on two lines of one cell ("SZ Z"): both are allowed, each with its own values.
      // Not before a bracket: "SZ (K)" is one code with a qualifier.
      if (lastWasCode && src.charAt(pos) !== '(') out += ' / ';
      lastWasCode = false;
    }
  }
  if (pos !== src.length || !out) return undefined;
  return { words: out.replace(/\s+/g, ' ').replace(/\( /g, '(').trim(), code: whole ?? text, reading: reading || undefined };
}

// ---------------------------------------------------------------------------------------------------------
// Codes in the other cells ("K", "K (60)", "Kr.", "45 s75", "É=12,5", "3,5L", "100 F")

interface Gloss {
  /** Matches the code inside the cell text. */
  re: RegExp;
  /** How the card names it, e.g. "K". */
  code: string;
  text: string;
  /** Shown as the value when the cell holds this code alone (default: `text` up to a colon). */
  short?: string;
}

const B = `(?<![${UPPER}${LOWER}])`; // no letter before
const A = `(?![${UPPER}${LOWER}])`; // no letter after
const g = (code: string, pattern: string, text: string, short?: string): Gloss => ({ code, re: new RegExp(pattern, 'u'), text, short });

// Not "§K" (XIII.: "kiegészítő előírás szerint").
const KIALAKULT = g('K', `(?<![${UPPER}${LOWER}§])K${A}`, 'kialakult: a meglévő állapot szerint');
const KA = g('KA', `${B}KA${A}`, 'kialakult állapot');
const OTEK_MARK = g('”', '”', 'OTÉK-tól való eltéréssel');

/** Per regulation, from its legend; KIALAKULT and KA apply everywhere. */
const GLOSS_AREA: Record<string, Gloss[]> = {
  // 25. § (1) "K" = kialakult állapot; (3) a value in brackets after "K" applies to a new building after the existing
  // one is demolished; 28. § "TK"; footnote 6 "Korm. rendelet szerint".
  i: [
    g('K (…)', `${B}K\\s*\\(`, 'a zárójeles érték a meglévő épület teljes bontása után épülő új épületre vonatkozik (25. § (3))'),
    g('TK', `${B}TK${A}`, 'a meglévő magasság a településképi rendelet illeszkedési szabályai szerint változtatható (28. §)',
      'a meglévő magasság (településképi illeszkedés)'),
    g('Kr.', `${B}(?:Kr\\.|KR)${A}`, 'a kormányrendelet szerint'),
  ],
  // 59. § (2)-(4), 60. §: "A" alapintézmény, intézmény esetén; "L" lakásrendeltetés esetén; "PP" parkolóhely-pótlás
  // a terven jelölt telken; "S" saroktelek esetén; "§" ha az övezet előírásában szereplő feltétel teljesül; "KH" közhasználat.
  ii: [
    g('S', `${B}S${A}`, 'saroktelek esetén'),
    g('KH', `${B}KH${A}`, 'kedvezmény közhasználatú terület kialakítása esetén'),
    g('A', `${B}A${A}`, 'alapintézmény, intézmény esetén'),
    g('L', `${B}L${A}`, 'lakásrendeltetés esetén'),
    g('PP', `${B}PP${A}`, 'parkolóhely-pótlásra a terven jelölt telken'),
    g('§', '§', 'ha az övezet előírásában szereplő feltétel teljesül', 'az övezet előírásában szereplő feltétellel'),
  ],
  // 1. melléklet jelmagyarázat (29. § (8)).
  xiii: [
    g('S', `${B}S${A}`, 'kizárólag saroktelek esetén'),
    g('F', `${B}F(?:\\+\\d)?${A}`, 'kizárólag földszint (F+1: földszint + 1 emelet, F+2: földszint + 2 emelet)'),
    g('L', `\\d\\s*L${A}|${B}L${A}`, 'lakóépület esetén alkalmazható érték'),
    g('KH', `${B}KH${A}`, 'szintterületi kedvezmény közhasználatú terület kialakítása esetén (33. §)'),
    g('E', `${B}E${A}`, 'szintterületi többletkedvezmény energiaminősítéssel rendelkező épület esetén (33. §)'),
    g('G', `${B}G${A}`, 'csak terepszint alatti garázs és pinceszinti tárolók esetén'),
    g('TO', `${B}TO${A}`, 'a telek megosztása esetén kialakítható legkisebb telekterület'),
    g('k', `[\\d”]k${A}`, 'fásítás esetén a zöldfelület kedvezményes értéke (30. § (4))'),
    g('FA', `%\\s*FA${A}`, 'fásításra meghatározott telekrész aránya (30. § (4))'),
    g('§K', '§K', 'kiegészítő előírásban foglalt esetben, vagy feltétel szerint'),
    g('§', '§(?!K)', 'az övezeti előírásban foglalt feltétel esetén', 'az övezeti előírás feltétele szerint'),
    g('ZÁÉ', `${B}Z[ÁA]É${A}`, 'zöldfelületi átlagérték a lakótelepi egység övezetére'),
    OTEK_MARK,
  ],
  // 27. § (5): "S" az oktatási, nevelési rendeltetéshez kapcsolódó új sportpálya, játszótér esetén.
  xiv: [g('S', `${B}S${A}`, 'oktatási, nevelési célú új sportpálya, játszótér esetén a zöldfelület legkisebb mértéke 10% lehet (27. § (5))')],
  // 2. melléklet: "/S = saroktelek esetén", "§ = § szerint", "SZT = szabályozási terv szerint", "KA = kialakult méret".
  xv: [
    g('S', `/\\s*S${A}`, 'saroktelek esetén'),
    g('§', '§', 'a rendelet vonatkozó paragrafusa szerint', 'a rendelet paragrafusa szerint'),
    g('SZT', `${B}SZT${A}`, 'a szabályozási terv szerint'),
  ],
  // 2. melléklet: "Á - általános esetben, S - saroktelek esetén, F - földszinten, kizárólag intézmény, közintézmény,
  // vagy járműtároló céljára, MG - mélygarázs létesítése esetén"; VI2: "ÖK – Kizárólag településrendezési szerződés alapján".
  vi: [
    g('Á', `${B}Á${A}`, 'általános esetben'), g('S', `${B}S${A}`, 'saroktelek esetén'),
    g('F', `${B}F${A}`, 'földszinten, kizárólag intézmény, közintézmény vagy járműtároló céljára'),
    g('MG', `${B}MG${A}`, 'mélygarázs létesítése esetén'), g('ÖK', `${B}ÖK${A}`, 'kizárólag településrendezési szerződés alapján'),
  ],
  // "s" before a value: the corner-plot (saroktelek) value, e.g. "65 s70" in a Z-only row.
  viii: [g('s', `${B}s\\d`, 'saroktelek esetén')],
  xxi: [g('s', `${B}s\\d`, 'saroktelek esetén')],
  // Column header "(É= épület, P= párkány)".
  xxii: [g('É', `${B}É${A}`, 'épületmagasság'), g('P', `${B}P${A}`, 'párkánymagasság')],
  // 9. § (4): "K" kialakult, "F" a 78. § szerint (a művelési ágtól függ), "G" a városrész részletes szabályai szerint.
  gyor: [
    g('F', `${B}F${A}`, 'a 78. § szerint: az érték a művelési ágtól függ'),
    g('G', `${B}G${A}`, 'a városrészre vonatkozó részletes szabályok szerint'),
  ],
  // Footnote under the tables: "p párkánymagasság" (printed as a raised p: "15,0[p]").
  x: [g('p', '\\[p\\]', 'párkánymagasság')],
  // Legends under the tables (raised letters, printed here as "[S]", "[TSZ]").
  'xii-kvh': [
    g('S', `${B}S${A}`, 'saroktelek esetén alkalmazható'),
    g('T', `\\[T\\]`, 'tetőtér-beépítés esetén alkalmazható bónuszérték (8. §)'),
    g('TSZ', `${B}TSZ${A}`, 'településrendezési szerződés megkötése esetén'),
    g('INT', `${B}INT${A}`, 'településrendezési szerződéssel, ha a földszinten kizárólag intézmény van'),
    g('I', `\\[I\\]`, 'iroda és közhasználatú építmény elhelyezése esetén'),
    g('O', `\\[O\\]`, 'OTÉK-tól való eltérési engedély alapján'),
    g('K', `\\[K\\]`, 'kereskedelmi, szolgáltató funkció esetén'),
  ],
};
GLOSS_AREA.vi2 = GLOSS_AREA.vi;

/** "É=12,5" / "P=8,0" / "P: 9,0" (IV. districts), "ém: 16,0" / "pm: 9,0" (XI.). */
const HEIGHT_PREFIX: Gloss[] = [
  g('É', `^É\\s*[=:]`, 'épületmagasság'), g('P', `^P\\s*[=:]`, 'párkánymagasság'),
  g('ém', '^ém\\.?:', 'épületmagasság'), g('pm', '^pm\\.?:', 'párkánymagasság'),
];

export interface ValueWords {
  /** The cell is a code alone ("K", "K*", "Kr."): its meaning, to show in place of the code. */
  main?: string;
  /** Each code found in the cell, with its meaning. */
  notes: { code: string; text: string }[];
}

/** What the codes in a table cell mean, for the card's line under the value. */
export function valueWords(area: string, raw: string): ValueWords {
  const text = raw.trim();
  const out: ValueWords = { notes: [] };
  if (!text || /^[-–‐—]+$/.test(text)) return out;
  const area0 = GLOSS_AREA[area] ?? [];
  const list = [...area0, ...HEIGHT_PREFIX];
  // An area's own "K"/"KA" meaning (e.g. I.: "K (…)") is added on top of the general one.
  if (!area0.some((x) => x.code === 'K')) list.push(KIALAKULT);
  if (!area0.some((x) => x.code === 'KA')) list.push(KA);
  for (const x of list) {
    if (x.re.test(text) && !out.notes.some((n) => n.code === x.code)) out.notes.push({ code: x.code, text: x.text });
  }
  // A code alone, with at most footnote marks: show its meaning as the value.
  const bare = text.replace(/[*”"]+$/, '').trim();
  const alone = out.notes.find((n) => n.code === bare || (n.code === 'Kr.' && /^(?:Kr\.?|KR)$/.test(bare)));
  if (alone) {
    const gl = list.find((x) => x.code === alone.code);
    out.main = gl?.short ?? alone.text.replace(/:.*$/, '');
    out.notes = out.notes.filter((n) => n !== alone);
  }
  return out;
}

// ---------------------------------------------------------------------------------------------------------
// Zone categories, for zones whose table gives no name ("Ln (Ln-0052)", "Lk-1/IV-3/1")

/** National land-use categories (OTÉK / TÉKA), valid in every plan. */
const CATEGORY_BASE: Dict = {
  Ln: 'Nagyvárosias lakóterület', Lk: 'Kisvárosias lakóterület', Lke: 'Kertvárosias lakóterület', Lf: 'Falusias lakóterület',
  'Ln-T': 'Nagyvárosias, telepszerű lakóterület', 'Lk-T': 'Kisvárosias, telepszerű lakóterület',
  Vt: 'Településközpont terület', Vi: 'Intézményi terület', Gksz: 'Kereskedelmi, szolgáltató gazdasági terület',
  Gip: 'Ipari gazdasági terület', K: 'Különleges terület', Zkp: 'Közpark', Zkk: 'Közkert', Zfk: 'Fásított köztér',
  Ev: 'Védelmi erdő', Ek: 'Közjóléti erdő', Eg: 'Gazdasági erdő', Má: 'Általános mezőgazdasági terület',
  Mk: 'Kertes mezőgazdasági terület', Vf: 'Folyóvizek medre és partja', Vg: 'Vízgazdálkodási terület',
  KÖu: 'Közúti közlekedési terület', KÖk: 'Kötöttpályás közlekedési terület', Tk: 'Természetközeli terület',
};

/** The Budapest-wide categories (Fővárosi Rendezési Szabályzat), as the district plans name them. */
const CATEGORY_BUDAPEST: Dict = {
  'Lk-1': 'Kisvárosias, jellemzően zártsorú beépítésű lakóterület', 'Lk-2': 'Kisvárosias, jellemzően szabadonálló jellegű lakóterület',
  'Lke-1': 'Kertvárosias, intenzív beépítésű lakóterület', 'Lke-2': 'Kertvárosias, laza beépítésű lakóterület',
  'Lke-3': 'Kertvárosias, sziluettérzékeny, hegyvidéki lakóterület',
  'Ln-1': 'Nagyvárosias, jellemzően zártsorú, zártudvaros beépítésű lakóterület',
  'Ln-2': 'Nagyvárosias, jellemzően zártsorú, keretes beépítésű lakóterület', 'Ln-3': 'Nagyvárosias, jellemzően szabadonálló jellegű lakóterület',
  'Vi-1': 'Intézményi, jellemzően zártsorú beépítésű terület', 'Vi-2': 'Intézményi, jellemzően szabadonálló jellegű terület',
  'Vi-3': 'Intézményi, helyi lakosság alapellátását biztosító terület',
  'Vt-V': 'Városközpont terület', 'Vt-H': 'Kiemelt jelentőségű helyi központ terület', 'Vt-M': 'Mellékközpont terület',
  'Gksz-1': 'Gazdasági, jellemzően kereskedelmi, szolgáltató terület', 'Gksz-2': 'Gazdasági, jellemzően raktározást, termelést szolgáló terület',
  'Gip-E': 'Energiatermelés terület', 'K-Rek': 'Nagykiterjedésű rekreációs és szabadidős terület', 'K-Sp': 'Nagykiterjedésű sportolási célú terület',
  'K-Hon': 'Honvédelmi, katonai és nemzetbiztonsági terület', 'K-Közl': 'Közlekedéshez kapcsolódó épületek területe',
  'K-T': 'Temető', 'K-Eü': 'Különleges egészségügyi terület', 'K-Okt': 'Oktatási központ területe', 'K-Hull': 'Hulladékkezelő terület',
  'K-Ker': 'Bevásárlóközpont területe', 'Kt-Ez': 'Egyéb zöldfelület', 'Kt-Gy': 'Gyalogos utak területe',
  'Kt-Kgy': 'Önálló gyalogos utak területe', 'Kt-Kk': 'Kerületi jelentőségű közutak területe', 'Kt-S': 'Természetközeli sétány területe',
  'Kt-U': 'Lakó- és kiszolgáló utak területe', 'Kt-Vá': 'Közösségi közlekedési végállomás területe', Zvp: 'Városi park',
  'Kb-Ez': 'Kondicionáló célú, jelentős zöldfelületű terület', 'Kt-Fk': 'Fásított köztér', 'Kt-Zkp': 'Közpark', 'Kt-Zkk': 'Közkert',
};

/** Pécs HÉSZ headings ("Különleges közhasználatú építmény terület (K-i)", "Kb-t jelű ... temetőterület övezet"). */
const CATEGORY_AREA: Record<string, Dict> = {
  pecs: {
    'Gip-e': 'Egyéb ipari gazdasági terület', 'Gip-z': 'Zavaró hatású ipari gazdasági terület',
    'K-i': 'Különleges közhasználatú építmény terület', 'K-kö': 'Különleges közlekedési terület',
    'K-h': 'Különleges hulladék-elhelyezési terület', 'K-ke': 'Különleges kereskedelmi célú terület',
    'K-k': 'Különleges városüzemeltetési kertészeti terület', 'K-lo': 'Különleges lovarda terület', 'KÖ-km': 'Telekigényes közmű terület',
    Mke: 'Kertes mezőgazdasági terület', Mko: 'Korlátozott használatú mezőgazdasági terület',
    'Kb-t': 'Temetőterület', 'Kb-esz': 'Különleges szolgáltató terület (beépítésre nem szánt)', 'Kb-eá': 'Állattartó terület',
    'Kb-ei': 'Idegenforgalmi terület (beépítésre nem szánt)', 'Kb-ea': 'Arborétum', 'Kb-np': 'Napelempark',
    'Kb-szt': 'Szalmatároló terület', 'Kb-b': 'Bányaterület', 'Kb-r': 'Rekreációs terület (beépítésre nem szánt)',
  },
};

const NOT_BUDAPEST = new Set(['gyor', 'pecs', 'csobanka']);

/** The land-use category a zone code belongs to, in words, by its longest known prefix. */
export function categoryName(area: string, code: string): string | undefined {
  const dicts = [CATEGORY_AREA[area] ?? {}, NOT_BUDAPEST.has(area) ? {} : CATEGORY_BUDAPEST, CATEGORY_BASE];
  // A sub-area prefix ("BF/Vt-V/K", "IT/K-Eü" in IX.) comes before the category.
  const tries = [code, code.replace(/^[A-ZÁÉÍÓÖŐÚÜŰ]{2,3}\//, '')];
  for (const c of tries) {
    const cu = key(c);
    let best: string | undefined;
    let bestLen = 0;
    for (const d of dicts) {
      for (const [k, v] of Object.entries(d)) {
        const ku = key(k);
        if (ku.length > bestLen && cu.startsWith(ku) && !/[\p{L}\d]/u.test(cu.charAt(ku.length))) {
          best = v;
          bestLen = ku.length;
        }
      }
      if (best) break;
    }
    if (best) return best;
  }
  return undefined;
}

/** True when the table's zone name is only a code ("Ln (Ln-0052)", "Lk-1/IV-3/1"). */
export function nameIsCode(name: string): boolean {
  return !new RegExp(`[${LOWER}]{5,}`).test(name);
}
