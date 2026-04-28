"""Difficulty tagger for ingested chunks.

Heuristic-first (free, runs in microseconds). Looks at:
  - exam-name keywords ("JEE Main", "JEE Advanced", "Olympiad", "NEET")
  - "Level-1/2/3" markers commonly used in Indian study material
  - lexical complexity (long math expressions, more equations, longer chunks)

Returns one of: "Easy" | "JEE Main" | "JEE Advanced" | "Olympiad" | "Unknown".

You can later pass each chunk through an LLM for a higher-quality label;
schema stays the same.
"""
from typing import Dict
import re


_LEVEL_RE = re.compile(r"\bLEVEL[-\s]?([123])\b", re.IGNORECASE)
_OLYMPIAD_RE = re.compile(r"\bolympiad|inpho|inchemo|inmo\b", re.IGNORECASE)
_JEE_ADV_RE = re.compile(r"\bjee\s*(adv|advanced|advance)\b", re.IGNORECASE)
_JEE_MAIN_RE = re.compile(r"\bjee\s*main\b", re.IGNORECASE)
_NEET_RE = re.compile(r"\bneet\b", re.IGNORECASE)


def classify_difficulty(text: str, chapter: str = "", book: str = "") -> str:
    haystack = f"{chapter}\n{book}\n{text[:4000]}"
    if _OLYMPIAD_RE.search(haystack):
        return "Olympiad"

    m = _LEVEL_RE.search(haystack)
    if m:
        lvl = m.group(1)
        if lvl == "1":
            return "JEE Main"
        if lvl == "2":
            return "JEE Advanced"
        return "Olympiad"

    if _JEE_ADV_RE.search(haystack):
        return "JEE Advanced"
    if _JEE_MAIN_RE.search(haystack):
        return "JEE Main"
    if _NEET_RE.search(haystack):
        return "NEET"

    # lexical fallback — long mathy chunks tend to be Advanced
    eqn_density = (text.count("=") + text.count("∫") + text.count("∑")) / max(len(text), 1)
    if eqn_density > 0.01 and len(text) > 1500:
        return "JEE Advanced"
    if eqn_density > 0.005:
        return "JEE Main"
    return "Unknown"


def tagged_metadata(text: str, base: Dict[str, str]) -> Dict[str, str]:
    """Return base metadata with `difficulty` added."""
    base = dict(base)
    base["difficulty"] = classify_difficulty(
        text, chapter=base.get("chapter", ""), book=base.get("book", "")
    )
    return base
