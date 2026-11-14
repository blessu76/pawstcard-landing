#!/usr/bin/env python3
"""The 12 site languages — the same values as ipe_web_kit v0.7.1 `ipe_web_kit/languages.py` (tests pin them).

The kit is not vendored in this repo, so the list lives here. When the kit comes back, import it instead of this module.
Never use the ended codes (ENDED, plus bare `zh` / `pt`) in a file name, URL or hreflang.
"""
import re

SUPPORTED = ("en", "ko", "ja", "zh-Hant", "es", "pt-BR", "fr", "de", "id", "th", "vi", "tr")
DEFAULT = "en"
ENDED = ("zh-Hans", "ru", "ar", "hi")
NAMES = {
    "en": "English", "ko": "한국어", "ja": "日本語", "zh-Hant": "繁體中文", "es": "Español", "pt-BR": "Português (Brasil)",
    "fr": "Français", "de": "Deutsch", "id": "Bahasa Indonesia", "th": "ไทย", "vi": "Tiếng Việt", "tr": "Türkçe",
}
# og:locale per language (this repo only; the kit has no such table)
OG_LOCALE = {
    "en": "en_US", "ko": "ko_KR", "ja": "ja_JP", "zh-Hant": "zh_TW", "es": "es_ES", "pt-BR": "pt_BR",
    "fr": "fr_FR", "de": "de_DE", "id": "id_ID", "th": "th_TH", "vi": "vi_VN", "tr": "tr_TR",
}
_ZH_HANT_REGIONS = {"tw", "hk", "mo"}
_ALIASES = {"in": "id"}


def resolve(tag):
    """A browser / Accept-Language tag -> one of SUPPORTED (DEFAULT when nothing matches). Same rules as the kit:
    zh-Hant / zh-TW / zh-HK / zh-MO -> zh-Hant, any other zh -> en; pt* -> pt-BR; in -> id; else the primary subtag."""
    parts = [x for x in re.split(r"[-_]", str(tag or "").strip().lower()) if x]
    if not parts:
        return DEFAULT
    primary = _ALIASES.get(parts[0], parts[0])
    if primary == "zh":
        script = next((x for x in parts[1:] if len(x) == 4 and x.isalpha()), None)
        region = next((x for x in parts[1:] if len(x) == 2 and x.isalpha()), None)
        if script == "hant" or (script is None and region in _ZH_HANT_REGIONS):
            return "zh-Hant"
        return DEFAULT
    if primary == "pt":
        return "pt-BR"
    for code in SUPPORTED:
        if code.lower() == primary:
            return code
    return DEFAULT


def hreflang(lang):
    """The hreflang value of a supported language (its own spelling); anything else is a bug."""
    if lang not in SUPPORTED:
        raise ValueError("unsupported language %r (supported: %s)" % (lang, ", ".join(SUPPORTED)))
    return lang
