"""Raw-field matching pipeline for the extended media checker.

The Anki search phase is deliberately only a prefilter.  The final verdict is
always made with Python's case-sensitive substring operator on unrendered note
fields, which permits arbitrary markup while avoiding false positives caused by
Anki's more permissive search semantics.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from math import ceil
from typing import Protocol

try:  # Allows direct imports by the offline test suite.
    from .exemptions import filter_candidates
except ImportError:  # pragma: no cover - only used outside the addon package
    from exemptions import filter_candidates

DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_REGEX_LENGTH = 8_000


class Note(Protocol):
    fields: Sequence[str]


class Collection(Protocol):
    def find_notes(self, query: str) -> Sequence[int]: ...

    def get_note(self, note_id: int) -> Note: ...


class ScanCancelled(Exception):
    """Raised when the user cancels the read-only scan."""


@dataclass(frozen=True)
class MatcherConfig:
    batch_size: int = DEFAULT_BATCH_SIZE
    max_regex_length: int = DEFAULT_MAX_REGEX_LENGTH

    def __post_init__(self) -> None:
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if self.max_regex_length < len("re:(?:)") + 1:
            raise ValueError("max_regex_length is too small for a regex query")


@dataclass(frozen=True)
class ScanResult:
    media_file_count: int
    exempted_count: int
    candidates: tuple[str, ...]
    unused: tuple[str, ...]
    matched_note_count: int


ProgressCallback = Callable[[str], None]
CancelCallback = Callable[[], bool]


def _escaped_filename(filename: str) -> str:
    """Escape a filename for both Python regex and Anki search parsing."""

    # re.escape() is required for all regex metacharacters.  Ampersand is not
    # special to Python's regex engine, but is meaningful in Anki's search
    # grammar, so escape it as well before embedding the regex in ``re:``.
    escaped = re.escape(filename)
    return re.sub(r"(?<!\\)&", r"\\&", escaped)


def filename_search_terms(filename: str) -> tuple[str, ...]:
    """Return query terms for a media-relative filename.

    Nested files can be referenced by their full media-relative path or by
    basename. Both slash styles are queried so platform-specific card text is
    included in Anki's prefilter.
    """

    normalized = filename.replace("\\", "/")
    if "/" not in normalized:
        return (normalized,)
    return tuple(
        dict.fromkeys(
            (
                normalized,
                normalized.replace("/", "\\"),
                normalized.rsplit("/", maxsplit=1)[-1],
            )
        )
    )


def build_regex_query(filenames: Sequence[str]) -> str:
    """Build one escaped Anki ``re:`` search query for *filenames*."""

    if not filenames:
        raise ValueError("cannot build a query for an empty batch")
    # Anki's search parser interprets unquoted backslashes itself and rejects
    # regex escapes such as ``\.``.  Quoted ``re:`` input is passed through to
    # the regex engine, preserving the ``re.escape()`` output unchanged.
    return '"re:(?:' + "|".join(_escaped_filename(filename) for filename in filenames) + ')"'


def build_batches(
    filenames: Iterable[str], config: MatcherConfig = MatcherConfig()
) -> list[list[str]]:
    """Split filenames without exceeding count or conservative query limits."""

    batches: list[list[str]] = []
    batch: list[str] = []

    for filename in filenames:
        if len(build_regex_query([filename])) > config.max_regex_length:
            raise ValueError(
                f"Search term exceeds max_regex_length: {filename!r}"
            )
        proposed = [*batch, filename]
        query_is_too_long = len(build_regex_query(proposed)) > config.max_regex_length
        if batch and (len(batch) >= config.batch_size or query_is_too_long):
            batches.append(batch)
            batch = [filename]
        else:
            batch = proposed

    if batch:
        batches.append(batch)
    return batches


def scan_collection(
    col: Collection,
    filenames: Iterable[str],
    *,
    config: MatcherConfig = MatcherConfig(),
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> ScanResult:
    """Return candidates not referenced in any raw note field.

    ``find_notes()`` prefilters the collection using batch regexes.  Only that
    reduced note set is loaded, and each filename is then verified with a
    case-sensitive exact substring check.
    """

    media_filenames = tuple(filenames)
    candidates = tuple(filter_candidates(media_filenames))
    candidate_terms = {
        filename: filename_search_terms(filename) for filename in candidates
    }
    query_terms = tuple(
        dict.fromkeys(term for terms in candidate_terms.values() for term in terms)
    )
    batches = build_batches(query_terms, config)
    matched_note_ids: set[int] = set()
    total_batches = len(batches)

    for index, batch in enumerate(batches, start=1):
        _raise_if_cancelled(cancelled)
        if progress:
            progress(f"Searching batch {index} of {total_batches}…")
        matched_note_ids.update(int(note_id) for note_id in col.find_notes(build_regex_query(batch)))

    _raise_if_cancelled(cancelled)
    if progress:
        progress(f"Reading {len(matched_note_ids)} matching notes…")
    # Newlines prevent an accidental match across separate fields or notes.
    raw_text = "\n".join(
        "\n".join(col.get_note(note_id).fields) for note_id in matched_note_ids
    )
    normalized_raw_text = raw_text.replace("\\", "/")

    unused: list[str] = []
    verification_total = len(candidates)
    update_every = max(1, ceil(verification_total / 100))
    for index, filename in enumerate(candidates, start=1):
        _raise_if_cancelled(cancelled)
        normalized_terms = {
            term.replace("\\", "/") for term in candidate_terms[filename]
        }
        if not any(term in normalized_raw_text for term in normalized_terms):
            unused.append(filename)
        if progress and (index == verification_total or index % update_every == 0):
            progress(f"Verifying filenames: {index} of {verification_total}…")

    return ScanResult(
        media_file_count=len(media_filenames),
        exempted_count=len(media_filenames) - len(candidates),
        candidates=candidates,
        unused=tuple(unused),
        matched_note_count=len(matched_note_ids),
    )


def _raise_if_cancelled(cancelled: CancelCallback | None) -> None:
    if cancelled and cancelled():
        raise ScanCancelled()
