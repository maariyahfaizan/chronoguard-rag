"""V2-only lexical safety rules; no numeric or semantic inference."""
import re
import unicodedata
from .answer_judge import normalize


def surface(text):
    return unicodedata.normalize("NFKC", text)


def has_quotation(text):
    text = surface(text)
    # Apostrophes inside words are allowed for contractions/possessives.
    text = re.sub(r"(?<=\w)['\u2019](?=\w)", "", text)
    return any(c in "\"'`" or unicodedata.category(c) in {"Pi", "Pf"}
               or "QUOTATION MARK" in unicodedata.name(c, "")
               or c in "\u201a\u201e\u2032\u2033\u300c\u300d\u300e\u300f\u301d\u301e\u301f"
               for c in text)


def _unsafe_math_representation(text):
    """One safety policy, applied before and after compatibility normalization."""
    has_number = any(c.isnumeric() for c in text)
    for c in text:
        category = unicodedata.category(c)
        if c.isnumeric() and c not in "0123456789":
            return True
        if category.startswith(("M", "S")) and c != "+":
            return True
        if has_number and category == "Pd" and c != "-":
            return True
        if category == "Cf":
            return True
        if has_number and ord(c) > 127 and category.startswith("L"):
            return True
    return bool(
        re.search(r"[*/\\^%=<>]|\d\s*[:!]|\d\s*[xX_]\s*\d|\+(?![0-9])", text)
        or re.search(r"\d\s*[eE]\s*[+-]?\s*\d|\d\s*[-+\u2010-\u2015]\s*\d|\d\s+to\s+[+-]?\d", text, re.I)
        or re.search(r"[\u2212\u2070-\u209f]|\d[,\'\u2019]\d|(?<!\d)\.\d|\d\.\.\d|\d\.\d+\.\d", text)
        or re.search(r"[+-]\s+[0-9]|[+-]{2,}\d|\d[+-]", text))


def unsupported_math(text):
    """Reject unsafe original characters AND unsafe NFKC-introduced syntax.

    The original representation must never be discarded before this call.
    Applying the same policy twice prevents compatibility punctuation from
    escaping syntax checks, without interpreting mathematical equivalence.
    """
    return _unsafe_math_representation(text) or _unsafe_math_representation(surface(text))


def expression_normalize(text):
    if unsupported_math(text):
        return None
    # Quotation detection uses the original text and its NFKC surface. Attribution
    # parsing remains on the original answer in the judge, before lexical matching.
    if has_quotation(text):
        return None
    text = surface(text)
    # Normalize text pieces independently: no placeholder can collide with input.
    pieces = re.split(r"([+-]?\d+(?:\.\d+)?)", text)
    return " ".join(value for index, piece in enumerate(pieces)
                    if (value := piece if index % 2 else normalize(piece)))
