from __future__ import annotations

from typing import Iterable

from .errors import SearchError

# Contractions are listed without the apostrophe because that is how the
# tokenizer emits them ("don't" -> "dont"). The ones that would collide with a
# real word once the apostrophe is gone (shell, well, ill, id, wed, hell, shed)
# are left out on purpose: losing "shell" on a programming blog is worse than
# indexing the odd "she'll".
_ENGLISH = """
a about above after again against all am an and any are arent as at be because
been before being below between both but by cant cannot could couldnt did
didnt do does doesnt doing dont down during each few for from further had
hadnt has hasnt have havent having he hes her here heres hers herself him
himself his how hows i if im in into is isnt it its itself ive lets me more
most mustnt my myself no nor not of off on once only or other ought our ours
ourselves out over own same shant she shes should shouldnt so some such than
that thats the their theirs them themselves then there theres these they
theyd theyll theyre theyve this those through to too under until up very was
wasnt we were werent weve what whats when whens where wheres which while who
whom whos why whys with wont would wouldnt you youd youll your youre yours
yourself yourselves youve
"""

_registry: dict[str, frozenset[str]] = {"en": frozenset(_ENGLISH.split())}


def primary_language(language: str | None) -> str:
    """Reduce "en-GB" or "pt_BR" to the bare language code."""
    if not language:
        return ""
    return language.replace("_", "-").split("-", 1)[0].lower()


def register_stopwords(
    language: str, words: Iterable[str], *, extend: bool = False
) -> None:
    """Add a stopword list for a language, or grow an existing one.

    Words should already look the way the tokenizer produces them: lowercase,
    accents folded, apostrophes removed.
    """
    code = primary_language(language)
    if not code:
        raise SearchError("stopword language code must not be empty")
    new = frozenset(word.strip().lower() for word in words if word.strip())
    if extend:
        new |= _registry.get(code, frozenset())
    _registry[code] = new


def get_stopwords(language: str | None) -> frozenset[str]:
    """Stopwords for a language; empty when nothing is registered for it."""
    return _registry.get(primary_language(language), frozenset())


def stopword_languages() -> list[str]:
    return sorted(_registry)
