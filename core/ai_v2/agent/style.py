"""Deterministic rioplatense voseo -> neutral Spanish normalization."""
from __future__ import annotations

import re

_VOSEO_TO_NEUTRAL: dict[str, str] = {
    "tenés": "tienes",
    "querés": "quieres",
    "podés": "puedes",
    "sabés": "sabes",
    "hacés": "haces",
    "sos": "eres",
    "decís": "dices",
    "venís": "vienes",
    "andás": "andas",
    "estás": "estás",
    "pensás": "piensas",
    "usás": "usas",
    "necesitás": "necesitas",
    "buscás": "buscas",
    "mirás": "miras",
    "manejás": "manejas",
    "trabajás": "trabajas",
    "seguís": "sigues",
    "pedís": "pides",
    "sentís": "sientes",
    "dormís": "duermes",
    "elegís": "eliges",
    "corregís": "corriges",
    "movés": "mueves",
    "empezás": "empiezas",
    "empezá": "empieza",
    "mirá": "mira",
    "revisá": "revisa",
    "revisás": "revisas",
    "corregí": "corrige",
    "mové": "mueve",
    "fijate": "fíjate",
    "decime": "dime",
    "mostrame": "muéstrame",
    "contame": "cuéntame",
    "explicame": "explícame",
    "pasá": "pasa",
    "seguí": "sigue",
    "probá": "prueba",
    "tomá": "toma",
    "usá": "usa",
    "dejá": "deja",
    "buscá": "busca",
    "pensá": "piensa",
    "agregá": "agrega",
    "cambiá": "cambia",
    "ajustá": "ajusta",
    "verificá": "verifica",
    "confirmá": "confirma",
    "elegí": "elige",
    "pedí": "pide",
    "abrí": "abre",
    "escribí": "escribe",
    "subí": "sube",
    "bajá": "baja",
    "cargá": "carga",
    "exportá": "exporta",
    "procesá": "procesa",
    "generá": "genera",
    "seleccioná": "selecciona",
    "marcá": "marca",
    "andá": "ve",
    "dale": "dale",
    "quedate": "quédate",
    "acordate": "acuérdate",
    "vos": "tú",
}

_VOSEO_RE = re.compile(
    r"(?<!\w)(?:"
    + "|".join(
        re.escape(key)
        for key in sorted(_VOSEO_TO_NEUTRAL, key=len, reverse=True)
    )
    + r")(?!\w)",
    re.IGNORECASE | re.UNICODE,
)
_CODE_SPAN_RE = re.compile(r"```.*?(?:```|\Z)|`[^`\n]*`", re.DOTALL)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_SENTENCE_ENDS = {".", "!", "?", "…", "\n", "\r"}


def neutralize_spanish(text: str) -> str:
    """Replace rioplatense voseo forms with neutral Spanish.

    Backtick code spans/blocks and URLs are preserved verbatim. Token
    case is preserved; ALL-CAPS tokens stay intact unless they open a
    sentence, so acronyms like ``SOS`` are never rewritten.
    """
    if not text:
        return text
    return "".join(
        chunk if protected else _neutralize_outside_code(chunk)
        for chunk, protected in _split_protected(text, _CODE_SPAN_RE)
    )


def _neutralize_outside_code(text: str) -> str:
    return "".join(
        chunk if protected else _replace_voseo(chunk)
        for chunk, protected in _split_protected(text, _URL_RE)
    )


def _replace_voseo(text: str) -> str:
    def _sub(match: re.Match[str]) -> str:
        token = match.group(0)
        replacement = _VOSEO_TO_NEUTRAL[token.lower()]
        if token.isupper() and not _is_sentence_start(text, match.start()):
            return token
        if token.islower():
            return replacement
        return replacement.capitalize()

    return _VOSEO_RE.sub(_sub, text)


def _split_protected(
    text: str, pattern: re.Pattern[str]
) -> list[tuple[str, bool]]:
    parts: list[tuple[str, bool]] = []
    pos = 0
    for match in pattern.finditer(text):
        if match.start() > pos:
            parts.append((text[pos:match.start()], False))
        parts.append((match.group(0), True))
        pos = match.end()
    if pos < len(text):
        parts.append((text[pos:], False))
    return parts


def _is_sentence_start(text: str, index: int) -> bool:
    cursor = index - 1
    while cursor >= 0 and text[cursor].isspace():
        cursor -= 1
    if cursor < 0:
        return True
    return text[cursor] in _SENTENCE_ENDS
