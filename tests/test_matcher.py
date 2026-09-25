from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import _addon_path  # noqa: F401
import matcher
from exemptions import filter_candidates
from media_paths import media_trash_directory
from matcher import (
    MatcherConfig,
    build_batches,
    build_regex_query,
    filename_search_terms,
    scan_collection,
)


@dataclass
class FakeNote:
    fields: list[str]


class FakeCollection:
    def __init__(self, notes: dict[int, FakeNote], matching_ids: set[int]) -> None:
        self.notes = notes
        self.matching_ids = matching_ids
        self.queries: list[str] = []

    def find_notes(self, query: str) -> list[int]:
        self.queries.append(query)
        return list(self.matching_ids)

    def get_note(self, note_id: int) -> FakeNote:
        return self.notes[note_id]


class MatcherTests(unittest.TestCase):
    def test_matcher_defaults_use_code_managed_search_limits(self) -> None:
        config = MatcherConfig()

        self.assertEqual(config.batch_size, 300)
        self.assertEqual(config.max_regex_length, 24_000)

    def test_exemptions_never_become_candidates(self) -> None:
        self.assertEqual(
            filter_candidates(
                [
                    "_tmp.png",
                    "latex-abcd.svg",
                    "assets/_temporary.png",
                    "assets/latex-generated.svg",
                    "assets/keep.mp3",
                ]
            ),
            ["assets/keep.mp3"],
        )

    def test_special_characters_are_escaped_in_regex_query(self) -> None:
        filename = "a&(b).mp3"
        query = build_regex_query([filename])
        self.assertTrue(query.startswith('"re:'))
        self.assertTrue(query.endswith(')"'))
        self.assertIn(r"a\&\(b\)\.mp3", query)
        col = FakeCollection({1: FakeNote([f"customAudio('{filename}')"])}, {1})
        self.assertEqual(scan_collection(col, [filename]).unused, ())

    def test_regex_query_uses_anki_raw_input_for_escaped_dot(self) -> None:
        self.assertEqual(build_regex_query(["photo.png"]), r'"re:(?:photo\.png)"')

    def test_raw_nonstandard_references_are_used(self) -> None:
        col = FakeCollection(
            {1: FakeNote(["![diagram](markdown.png)", "playCustom('script.mp3')"])},
            {1},
        )
        result = scan_collection(col, ["markdown.png", "script.mp3", "unused.mp3"])
        self.assertEqual(result.media_file_count, 3)
        self.assertEqual(result.exempted_count, 0)
        self.assertEqual(result.matched_note_count, 1)
        self.assertEqual(result.unused, ("unused.mp3",))

    def test_nested_file_matches_its_media_relative_path(self) -> None:
        filename = "assets/spanish-tts/hola.mp3"
        col = FakeCollection({1: FakeNote([f"playCustom('{filename}')"])}, {1})

        result = scan_collection(col, [filename])

        self.assertEqual(result.unused, ())
        self.assertTrue(any("assets/spanish" in query and "hola" in query for query in col.queries))

    def test_nested_file_matches_windows_path_separators(self) -> None:
        col = FakeCollection({1: FakeNote([r"playCustom('assets\spanish-tts\hola.mp3')"])}, {1})

        result = scan_collection(col, ["assets/spanish-tts/hola.mp3"])

        self.assertEqual(result.unused, ())

    def test_nested_file_basename_fallback_keeps_duplicate_names_used(self) -> None:
        col = FakeCollection({1: FakeNote(["[sound:shared.mp3]"])}, {1})
        filenames = ["assets/one/shared.mp3", "assets/two/shared.mp3", "assets/two/unused.mp3"]

        result = scan_collection(col, filenames)

        self.assertEqual(result.unused, ("assets/two/unused.mp3",))
        self.assertTrue(any("shared\\.mp3" in query for query in col.queries))

    def test_nested_path_and_basename_matching_remain_case_sensitive(self) -> None:
        col = FakeCollection({1: FakeNote(["assets/spanish-tts/hola.mp3"])}, {1})

        result = scan_collection(col, ["assets/spanish-tts/Hola.mp3"])

        self.assertEqual(result.unused, ("assets/spanish-tts/Hola.mp3",))

    def test_filename_search_terms_include_both_path_styles_and_basename(self) -> None:
        self.assertEqual(
            filename_search_terms("assets/spanish-tts/hola.mp3"),
            (
                "assets/spanish-tts/hola.mp3",
                r"assets\spanish-tts\hola.mp3",
                "hola.mp3",
            ),
        )

    def test_scan_result_reports_exempted_media(self) -> None:
        result = scan_collection(
            FakeCollection({}, set()),
            ["_internal.png", "latex-generated.svg", "unused.png"],
        )
        self.assertEqual(result.media_file_count, 3)
        self.assertEqual(result.exempted_count, 2)
        self.assertEqual(result.candidates, ("unused.png",))

    def test_final_match_is_case_sensitive(self) -> None:
        col = FakeCollection({1: FakeNote(["<img src='Photo.PNG'>"])}, {1})
        result = scan_collection(col, ["photo.png"])
        self.assertEqual(result.unused, ("photo.png",))

    def test_large_input_is_batched_under_count_and_length_caps(self) -> None:
        filenames = [f"asset-{index:04d}.png" for index in range(3_000)]
        batches = build_batches(filenames, MatcherConfig(batch_size=100, max_regex_length=800))
        self.assertGreater(len(batches), 1)
        self.assertTrue(all(len(batch) <= 100 for batch in batches))
        self.assertTrue(all(len(build_regex_query(batch)) <= 800 for batch in batches))

    def test_extreme_config_values_are_bounded_for_count_and_query_length(self) -> None:
        config = MatcherConfig(batch_size=1_000, max_regex_length=80_000)
        short_terms = [f"asset-{index:04d}.png" for index in range(700)]
        short_batches = build_batches(short_terms, config)

        self.assertTrue(all(len(batch) <= 300 for batch in short_batches))
        self.assertTrue(all(len(build_regex_query(batch)) <= 24_000 for batch in short_batches))

        long_terms = [f"asset-{index:04d}-{'x' * 100}.png" for index in range(260)]
        long_batches = build_batches(long_terms, config)

        self.assertTrue(all(len(batch) < 300 for batch in long_batches))
        self.assertTrue(all(len(build_regex_query(batch)) <= 24_000 for batch in long_batches))

    def test_search_progress_reports_effective_batch_size(self) -> None:
        progress: list[str] = []
        scan_collection(
            FakeCollection({}, set()),
            [f"asset-{index:04d}.png" for index in range(301)],
            config=MatcherConfig(batch_size=1_000, max_regex_length=80_000),
            progress=progress.append,
        )

        self.assertTrue(any("Applying safe query ceilings" in message for message in progress))
        self.assertTrue(
            any(message.startswith("Searching batch 1 (300 terms, ") for message in progress)
        )

    def test_build_batches_escapes_each_term_once(self) -> None:
        filenames = [f"asset-{index}.png" for index in range(10)]

        with patch.object(matcher, "_escaped_filename", wraps=matcher._escaped_filename) as escape:
            batches = build_batches(filenames, MatcherConfig(batch_size=4, max_regex_length=1_000))

        self.assertEqual([name for batch in batches for name in batch], filenames)
        self.assertEqual(escape.call_count, len(filenames))

    def test_iter_batches_yields_before_consuming_remaining_terms(self) -> None:
        consumed: list[int] = []

        def terms():
            for index in range(5):
                consumed.append(index)
                yield f"asset-{index}.png"

        batches = matcher.iter_batches(terms(), MatcherConfig(batch_size=2, max_regex_length=1_000))

        self.assertEqual(next(batches), ["asset-0.png", "asset-1.png"])
        self.assertEqual(consumed, [0, 1])

    def test_scan_searches_first_batch_before_escaping_all_terms(self) -> None:
        filenames = [f"asset-{index}.png" for index in range(10)]
        collection = FakeCollection({}, set())
        original_find_notes = collection.find_notes
        escape_counts_at_search: list[int] = []

        with patch.object(matcher, "_escaped_filename", wraps=matcher._escaped_filename) as escape:

            def record_search(query: str) -> list[int]:
                escape_counts_at_search.append(escape.call_count)
                return original_find_notes(query)

            collection.find_notes = record_search
            scan_collection(
                collection,
                filenames,
                config=MatcherConfig(batch_size=2, max_regex_length=1_000),
            )

        self.assertEqual(escape_counts_at_search[0], 4)
        self.assertEqual(len(escape_counts_at_search), 5)

    def test_scan_reports_progress_during_large_batch_preparation(self) -> None:
        progress: list[str] = []
        scan_collection(
            FakeCollection({}, set()),
            [f"asset-{index:04d}.png" for index in range(1_000)],
            config=MatcherConfig(batch_size=2_000, max_regex_length=80_000),
            progress=progress.append,
        )

        preparing = "Preparing search terms: 1000 files scanned…"
        self.assertIn(preparing, progress)
        searching_indices = [
            index
            for index, message in enumerate(progress)
            if message.startswith("Searching batch ")
        ]
        self.assertTrue(searching_indices)
        searching_index = searching_indices[-1]
        self.assertLess(progress.index(preparing), searching_index)

    def test_scan_checks_cancellation_during_batch_preparation(self) -> None:
        collection = FakeCollection({}, set())

        with self.assertRaises(matcher.ScanCancelled):
            scan_collection(
                collection,
                [f"asset-{index}.png" for index in range(300)],
                config=MatcherConfig(batch_size=500, max_regex_length=80_000),
                cancelled=lambda: True,
            )

        self.assertEqual(collection.queries, [])

    def test_expanded_nested_search_terms_respect_batch_limits(self) -> None:
        filenames = [f"assets/tts/line-{index:04d}.mp3" for index in range(300)]
        terms = [term for filename in filenames for term in filename_search_terms(filename)]
        config = MatcherConfig(batch_size=12, max_regex_length=500)

        batches = build_batches(terms, config)

        self.assertGreater(len(batches), 1)
        self.assertTrue(all(len(batch) <= config.batch_size for batch in batches))
        self.assertTrue(
            all(len(build_regex_query(batch)) <= config.max_regex_length for batch in batches)
        )

    def test_single_search_term_cannot_exceed_query_length_cap(self) -> None:
        with self.assertRaises(ValueError):
            build_batches(["x" * 100], MatcherConfig(max_regex_length=20))


class MediaPathTests(unittest.TestCase):
    def test_trash_is_sibling_of_media_directory(self) -> None:
        media_directory = Path("profile") / "collection.media"
        expected = Path("profile") / "media.trash"
        self.assertEqual(media_trash_directory(str(media_directory)), str(expected))


if __name__ == "__main__":
    unittest.main()
