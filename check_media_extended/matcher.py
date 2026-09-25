"""Raw-field matching pipeline for the extended media checker.

The Anki search phase is deliberately only a prefilter.  The final verdict is
always made with Python's case-sensitive substring operator on unrendered note
fields, which permits arbitrary markup while avoiding false positives caused by
Anki's more permissive search semantics.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from math import ceil
from typing import Protocol

try:  # Allows direct imports by the offline test suite.
    from .exemptions import is_exempt
except ImportError:  # pragma: no cover - only used outside the addon package
    from exemptions import is_exempt

MAX_SAFE_BATCH_SIZE = 300
MAX_SAFE_REGEX_LENGTH = 24_000
DEFAULT_BATCH_SIZE = MAX_SAFE_BATCH_SIZE
DEFAULT_MAX_REGEX_LENGTH = MAX_SAFE_REGEX_LENGTH
_REGEX_QUERY_PREFIX = '"re:(?:'
_REGEX_QUERY_SUFFIX = ')"'
_REGEX_QUERY_FIXED_LENGTH = len(_REGEX_QUERY_PREFIX) + len(_REGEX_QUERY_SUFFIX)


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
    escaped_filenames = (_escaped_filename(filename) for filename in filenames)
    return _REGEX_QUERY_PREFIX + "|".join(escaped_filenames) + _REGEX_QUERY_SUFFIX


def iter_batches(
    filenames: Iterable[str], config: MatcherConfig = MatcherConfig()
) -> Iterator[list[str]]:
    """Yield incrementally sized batches under conservative search ceilings."""

    batch: list[str] = []
    query_length = _REGEX_QUERY_FIXED_LENGTH
    batch_size_limit = min(config.batch_size, MAX_SAFE_BATCH_SIZE)
    query_length_limit = min(config.max_regex_length, MAX_SAFE_REGEX_LENGTH)

    for filename in filenames:
        escaped_length = len(_escaped_filename(filename))
        if _REGEX_QUERY_FIXED_LENGTH + escaped_length > query_length_limit:
            raise ValueError(
                f"Search term exceeds the effective max_regex_length "
                f"({query_length_limit:,} characters): {filename!r}"
            )

        proposed_query_length = query_length + escaped_length + (1 if batch else 0)
        if batch and (len(batch) >= batch_size_limit or proposed_query_length > query_length_limit):
            yield batch
            batch = []
            query_length = _REGEX_QUERY_FIXED_LENGTH

        batch.append(filename)
        query_length += escaped_length + (1 if len(batch) > 1 else 0)
        if len(batch) >= batch_size_limit:
            yield batch
            batch = []
            query_length = _REGEX_QUERY_FIXED_LENGTH

    if batch:
        yield batch


def build_batches(
    filenames: Iterable[str], config: MatcherConfig = MatcherConfig()
) -> list[list[str]]:
    """Materialize batches for callers that need the complete batch list."""

    return list(iter_batches(filenames, config))


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

    candidate_names: list[str] = []
    media_file_count = 0
    exempted_count = 0

    def unique_search_terms() -> Iterator[str]:
        nonlocal media_file_count, exempted_count
        seen_terms: set[str] = set()
        for filename in filenames:
            media_file_count += 1
            if media_file_count % 256 == 0:
                _raise_if_cancelled(cancelled)
            if progress and media_file_count % 1_000 == 0:
                progress(f"Preparing search terms: {media_file_count} files scanned…")

            if is_exempt(filename):
                exempted_count += 1
                continue

            candidate_names.append(filename)
            for term in filename_search_terms(filename):
                if term not in seen_terms:
                    seen_terms.add(term)
                    yield term

    matched_note_ids: set[int] = set()

    if progress and (
        config.batch_size > MAX_SAFE_BATCH_SIZE or config.max_regex_length > MAX_SAFE_REGEX_LENGTH
    ):
        progress(
            "Applying safe query ceilings: "
            f"{MAX_SAFE_BATCH_SIZE:,} terms / "
            f"{MAX_SAFE_REGEX_LENGTH:,} query characters per search…"
        )

    for index, batch in enumerate(iter_batches(unique_search_terms(), config), start=1):
        _raise_if_cancelled(cancelled)
        query = build_regex_query(batch)
        if progress:
            progress(
                f"Searching batch {index} ({len(batch):,} terms, " f"{len(query):,} characters)…"
            )
        matched_note_ids.update(int(note_id) for note_id in col.find_notes(query))

    candidates = tuple(candidate_names)
    _raise_if_cancelled(cancelled)
    if progress:
        progress(f"Reading {len(matched_note_ids)} matching notes…")
    # Newlines prevent an accidental match across separate fields or notes.
    raw_text = "\n".join("\n".join(col.get_note(note_id).fields) for note_id in matched_note_ids)
    normalized_raw_text = raw_text.replace("\\", "/")

    unused: list[str] = []
    verification_total = len(candidates)
    update_every = max(1, ceil(verification_total / 100))
    for index, filename in enumerate(candidates, start=1):
        _raise_if_cancelled(cancelled)
        normalized_terms = {term.replace("\\", "/") for term in filename_search_terms(filename)}
        if not any(term in normalized_raw_text for term in normalized_terms):
            unused.append(filename)
        if progress and (index == verification_total or index % update_every == 0):
            progress(f"Verifying filenames: {index} of {verification_total}…")

    return ScanResult(
        media_file_count=media_file_count,
        exempted_count=exempted_count,
        candidates=candidates,
        unused=tuple(unused),
        matched_note_count=len(matched_note_ids),
    )


def _raise_if_cancelled(cancelled: CancelCallback | None) -> None:
    if cancelled and cancelled():
        raise ScanCancelled()
