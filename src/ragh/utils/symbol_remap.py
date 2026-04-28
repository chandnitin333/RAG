"""Adobe Symbol-font private-use → real Unicode remap.

Many JEE PDFs embed math via the legacy Adobe Symbol font, which renders
beautifully but extracts as private-use codepoints in 0xF020–0xF0FF.
We map them back so chunk text shows π/θ/≤/≥/× instead of garbled glyphs.
"""
from __future__ import annotations
import re

# Lower- and upper-case Greek + maths operators that appear in JEE study text
SYMBOL_F0XX_TO_UNICODE = {
    # ASCII passthrough block (Symbol uses 0xF020–0xF07F as reshaped ASCII)
    0xF020: " ",  0xF021: "!",  0xF022: "∀", 0xF023: "#",
    0xF024: "∃",  0xF025: "%",  0xF026: "&", 0xF027: "∋",
    0xF028: "(",  0xF029: ")",  0xF02A: "∗", 0xF02B: "+",
    0xF02C: ",",  0xF02D: "−", 0xF02E: ".",  0xF02F: "/",
    **{0xF030 + i: chr(0x30 + i) for i in range(10)},
    0xF03A: ":",  0xF03B: ";",  0xF03C: "<", 0xF03D: "=",
    0xF03E: ">",  0xF03F: "?",  0xF040: "≅",
    # Greek capitals (A→Α etc.)
    0xF041: "Α", 0xF042: "Β", 0xF043: "Χ", 0xF044: "Δ", 0xF045: "Ε",
    0xF046: "Φ", 0xF047: "Γ", 0xF048: "Η", 0xF049: "Ι", 0xF04A: "ϑ",
    0xF04B: "Κ", 0xF04C: "Λ", 0xF04D: "Μ", 0xF04E: "Ν", 0xF04F: "Ο",
    0xF050: "Π", 0xF051: "Θ", 0xF052: "Ρ", 0xF053: "Σ", 0xF054: "Τ",
    0xF055: "Υ", 0xF056: "ς", 0xF057: "Ω", 0xF058: "Ξ", 0xF059: "Ψ",
    0xF05A: "Ζ",
    0xF05B: "[", 0xF05C: "∴", 0xF05D: "]", 0xF05E: "⊥", 0xF05F: "_",
    # Greek lowercase (a→α etc.)
    0xF061: "α", 0xF062: "β", 0xF063: "χ", 0xF064: "δ", 0xF065: "ε",
    0xF066: "φ", 0xF067: "γ", 0xF068: "η", 0xF069: "ι", 0xF06A: "ϕ",
    0xF06B: "κ", 0xF06C: "λ", 0xF06D: "μ", 0xF06E: "ν", 0xF06F: "ο",
    0xF070: "π", 0xF071: "θ", 0xF072: "ρ", 0xF073: "σ", 0xF074: "τ",
    0xF075: "υ", 0xF076: "ϖ", 0xF077: "ω", 0xF078: "ξ", 0xF079: "ψ",
    0xF07A: "ζ",
    0xF07B: "{", 0xF07C: "|", 0xF07D: "}", 0xF07E: "~",
    # Math operators / arrows / set theory
    0xF0A1: "ϒ", 0xF0A2: "′", 0xF0A3: "≤", 0xF0A4: "⁄", 0xF0A5: "∞",
    0xF0A6: "ƒ", 0xF0AB: "↔", 0xF0AC: "←", 0xF0AD: "↑", 0xF0AE: "→",
    0xF0AF: "↓",
    0xF0B0: "°", 0xF0B1: "±", 0xF0B2: "″", 0xF0B3: "≥", 0xF0B4: "×",
    0xF0B5: "∝", 0xF0B6: "∂", 0xF0B7: "·", 0xF0B8: "÷", 0xF0B9: "≠",
    0xF0BA: "≡", 0xF0BB: "≈", 0xF0BC: "…", 0xF0BD: "|",  0xF0BE: "—",
    0xF0BF: "↵",
    0xF0C0: "ℵ", 0xF0C1: "ℑ", 0xF0C2: "ℜ", 0xF0C3: "℘", 0xF0C4: "⊗",
    0xF0C5: "⊕", 0xF0C6: "∅", 0xF0C7: "∩", 0xF0C8: "∪", 0xF0C9: "⊃",
    0xF0CA: "⊇", 0xF0CB: "⊄", 0xF0CC: "⊂", 0xF0CD: "⊆", 0xF0CE: "∈",
    0xF0CF: "∉",
    0xF0D0: "∠", 0xF0D1: "∇", 0xF0D2: "®", 0xF0D3: "©", 0xF0D4: "™",
    0xF0D5: "∏", 0xF0D6: "√", 0xF0D7: "·", 0xF0D8: "¬", 0xF0D9: "∧",
    0xF0DA: "∨", 0xF0DB: "⇔", 0xF0DC: "⇐", 0xF0DD: "⇑", 0xF0DE: "⇒",
    0xF0DF: "⇓",
    0xF0E0: "◊", 0xF0E5: "∑", 0xF0F2: "∫",
}


_TABLE = str.maketrans({chr(k): v for k, v in SYMBOL_F0XX_TO_UNICODE.items()})

# any other private-use char we don't know about: drop (don't leave garbage)
_PRIVATE_USE = re.compile(r"[-]")


def remap(text: str) -> str:
    if not text:
        return text
    return _PRIVATE_USE.sub("", text.translate(_TABLE))


def remap_lite_cleanup(text: str) -> str:
    """remap + collapse PDF column whitespace + dehyphenate line breaks."""
    if not text:
        return text
    s = remap(text)
    # de-hyphenated line break: "perpen-\ndicular" → "perpendicular"
    s = re.sub(r"(\w)-\n(\w)", r"\1\2", s)
    # multiple spaces from columnar layout
    s = re.sub(r"[ \t]{2,}", " ", s)
    # blank lines
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
