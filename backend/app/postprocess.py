from __future__ import annotations

import re
from typing import Iterable

from .config import settings


FILLER_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(word) for word in settings.filler_words) + r")\b",
    flags=re.IGNORECASE,
)


def remove_filler_words(text: str) -> str:
    cleaned = FILLER_PATTERN.sub("", text)
    return collapse_spaces(cleaned)


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def apply_cleaners(text: str, cleaners: Iterable[str]) -> str:
    result = text
    for cleaner in cleaners:
        if cleaner == "remove_fillers":
            result = remove_filler_words(result)
        elif cleaner == "collapse_spaces":
            result = collapse_spaces(result)
    return result
