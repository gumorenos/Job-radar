from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_SEGMENT_SPLIT = re.compile(r"(?:\r?\n)+|(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ0-9•\-])")
_WHITESPACE = re.compile(r"\s+")
_QUANTIFIED = re.compile(r"(?:\d[\d.,]*\s*%|\b\d[\d.,]*\b|S/\s*\d|US\$\s*\d|USD\s*\d|\$\s*\d)", re.I)


@dataclass(frozen=True)
class CvTextChange:
    kind: str
    original: str | None
    proposed: str | None


@dataclass(frozen=True)
class CvComparisonResult:
    changes: tuple[CvTextChange, ...]
    unchanged_count: int
    parent_word_count: int
    current_word_count: int
    quantified_statement_count: int


def _segments(text: str | None) -> list[str]:
    if not text:
        return []
    items = []
    for raw in _SEGMENT_SPLIT.split(text):
        value = _WHITESPACE.sub(" ", raw).strip()
        if value:
            items.append(value)
    return items[:400]


def _key(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip().casefold()


def _word_count(text: str | None) -> int:
    return len(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ'-]+\b", text or "", flags=re.UNICODE))


def _quantified_statement_count(segments: list[str]) -> int:
    return sum(1 for item in segments if _QUANTIFIED.search(item))


def compare_cv_text(parent_text: str | None, current_text: str | None) -> CvComparisonResult:
    parent = _segments(parent_text)
    current = _segments(current_text)
    matcher = SequenceMatcher(
        a=[_key(item) for item in parent],
        b=[_key(item) for item in current],
        autojunk=False,
    )
    changes: list[CvTextChange] = []
    unchanged = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            unchanged += i2 - i1
            continue
        if tag == "delete":
            changes.extend(CvTextChange("REMOVED", value, None) for value in parent[i1:i2])
            continue
        if tag == "insert":
            changes.extend(CvTextChange("ADDED", None, value) for value in current[j1:j2])
            continue

        removed = parent[i1:i2]
        added = current[j1:j2]
        paired = min(len(removed), len(added))
        changes.extend(
            CvTextChange("REPLACED", removed[index], added[index]) for index in range(paired)
        )
        changes.extend(CvTextChange("REMOVED", value, None) for value in removed[paired:])
        changes.extend(CvTextChange("ADDED", None, value) for value in added[paired:])

    return CvComparisonResult(
        changes=tuple(changes),
        unchanged_count=unchanged,
        parent_word_count=_word_count(parent_text),
        current_word_count=_word_count(current_text),
        quantified_statement_count=_quantified_statement_count(current),
    )


def required_skill_signals(required_skills: list[str], content_text: str | None) -> list[dict[str, object]]:
    haystack = _key(content_text or "")
    signals: list[dict[str, object]] = []
    seen: set[str] = set()
    for skill in required_skills:
        label = _WHITESPACE.sub(" ", skill).strip()
        key = _key(label)
        if not key or key in seen:
            continue
        seen.add(key)
        signals.append({"skill": label, "present": key in haystack})
    return signals
