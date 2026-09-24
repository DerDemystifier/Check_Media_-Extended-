from __future__ import annotations

import unittest
from dataclasses import dataclass

import _addon_path  # noqa: F401
from exemptions import filter_candidates
from matcher import MatcherConfig, build_batches, build_regex_query, scan_collection


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
    def test_exemptions_never_become_candidates(self) -> None:
        self.assertEqual(filter_candidates(["_tmp.png", "latex-abcd.svg", "keep.mp3"]), ["keep.mp3"])

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
        self.assertEqual(result.unused, ("unused.mp3",))

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


if __name__ == "__main__":
    unittest.main()
