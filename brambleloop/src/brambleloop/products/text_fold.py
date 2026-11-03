"""One fold for reading a product's own words (A1-R: the children's text layer).

Every place that reads a child-audience word -- the drafting routes, the PDF renderer and the
catalogue survey -- reads the text through `fold`, so a title spelled in look-alike or
invisible characters is the word it renders as, and the readers cannot disagree.

    NFKC (full-width and mathematical letters: "Ｂaby", "𝐁aby")
    -> every format, unassigned, mark and invisible filler character removed (zero-width
       spaces and joiners, soft hyphens, variation selectors, Hangul fillers, the blank
       braille pattern)
    -> NFKD, combining marks dropped, NFKC ("Bébé" -> "bebe")
    -> look-alike CAPITALS from other scripts read as the Latin capital they imitate
       (Greek "Β", Cherokee "Ᏼ"), BEFORE case folding (A1R-2)
    -> lower case
    -> look-alike small letters read as the Latin letter they imitate ("Bаby", Cyrillic а).

It is the ONE fold (A1R-3): `creative.fallback_constructions.fold_title` (drafting routes)
and A2's motif reader call it, as do the renderer and the survey (`launch0.child_words_in`).

The look-alike table is explicit, not a full UTS #39 skeleton; every entry is a letter that
renders as the Latin one. A word in another script entirely is not a Latin word and is left
for the routes' own total allowlists to refuse.
"""
from __future__ import annotations

import unicodedata

INVISIBLE = frozenset({0x00AD, 0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x2800, 0x3164,
                       0xFFA0} | set(range(0x180B, 0x1810)) | set(range(0x200B, 0x2010))
                      | set(range(0x2060, 0x2070)) | set(range(0xFE00, 0xFE10)) | {0xFEFF})
# A1R-2: capitals are read BEFORE case folding. Lower-casing first turned Greek and Cherokee
# capitals into small letters of a different shape (Β -> β, Ν -> ν read as "v", Η -> η read
# as "n"), so "Βaby" escaped. Each entry is a capital that renders as the Latin capital.
CAPITAL_LOOKALIKES = str.maketrans({
    # Greek capitals
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M",
    "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X", "Ϲ": "C", "Ϳ": "J",
    # Cyrillic capitals
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P",
    "С": "C", "Т": "T", "У": "Y", "Х": "X", "Ү": "Y", "Ь": "B", "Ѕ": "S", "І": "I",
    "Ј": "J", "Ԁ": "D", "Ԛ": "Q", "Ԝ": "W", "Һ": "H", "Ӏ": "I", "З": "3",
    # Cherokee capitals that render as Latin capitals
    "Ꭺ": "A", "Ᏼ": "B", "Ꮯ": "C", "Ꭼ": "E", "Ꮐ": "G", "Ꮋ": "H", "Ꭵ": "I", "Ꭻ": "J",
    "Ꮶ": "K", "Ꮮ": "L", "Ꮇ": "M", "Ꮑ": "N", "Ꮎ": "O", "Ꮲ": "P", "Ꮢ": "R", "Ꮪ": "S",
    "Ꭲ": "T", "Ꮩ": "V", "Ꮃ": "W", "Ꮓ": "Z", "Ᏻ": "G", "Ꮤ": "W",
    # Armenian and Coptic capitals
    "Օ": "O", "Ս": "U", "Ⲟ": "O", "Ⲣ": "P", "Ⲥ": "C",
    # Latin letters that look like others
    "Ɩ": "l", "Ɪ": "I",
})
LOOKALIKES = str.maketrans({
    # Cyrillic
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "ү": "y", "ь": "b",
    "т": "t", "м": "m", "к": "k", "в": "b", "н": "h",
    "һ": "h", "ԁ": "d", "ԛ": "q", "ԝ": "w", "ӏ": "i", "Ӏ": "i",
    # Greek
    "ο": "o", "α": "a", "ι": "i", "τ": "t", "κ": "k", "ν": "v",
    "ρ": "p", "ε": "e", "η": "n", "μ": "u", "υ": "u", "χ": "x",
    "ϲ": "c", "ς": "c",
    # Latin small capitals and other look-alikes
    "ı": "i", "ɑ": "a", "ɡ": "g", "ɪ": "i", "ɴ": "n", "ʀ": "r",
    "ʏ": "y", "ʟ": "l", "ʙ": "b", "ᴀ": "a", "ᴄ": "c", "ᴅ": "d",
    "ᴇ": "e", "ᴊ": "j", "ᴋ": "k", "ᴍ": "m", "ᴏ": "o", "ᴘ": "p",
    "ᴛ": "t", "ᴜ": "u", "ᴡ": "w", "ɢ": "g", "ʜ": "h", "ꜰ": "f",
    "ꜱ": "s", "ø": "o",
    # Armenian
    "օ": "o", "ո": "n", "ս": "u",
})


def fold(text: str | None) -> str:
    t = unicodedata.normalize("NFKC", str(text or ""))
    t = "".join(c for c in t if ord(c) not in INVISIBLE
                and unicodedata.category(c) not in ("Cf", "Cn", "Mn", "Me"))
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if unicodedata.category(c) not in ("Mn", "Me"))
    t = unicodedata.normalize("NFKC", t)
    # A1R-2: capitals first, then case folding, then the small look-alikes.
    return t.translate(CAPITAL_LOOKALIKES).lower().translate(LOOKALIKES)
