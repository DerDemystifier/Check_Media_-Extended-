from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import _addon_path  # noqa: F401
from media_paths import discover_media_files, root_level_media_filenames


class MediaFileDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.media_directory = Path(self._temporary_directory.name) / "collection.media"
        self.media_directory.mkdir()

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def test_includes_root_files_and_recursively_scans_configured_paths(self) -> None:
        (self.media_directory / "root.mp3").write_bytes(b"root")
        nested_directory = self.media_directory / "assets" / "spanish-tts" / "lesson-1"
        nested_directory.mkdir(parents=True)
        (nested_directory / "hola.mp3").write_bytes(b"hola")
        (self.media_directory / "unconfigured").mkdir()
        (self.media_directory / "unconfigured" / "ignore.mp3").write_bytes(b"ignore")

        result = discover_media_files(
            str(self.media_directory), ["assets/spanish-tts"]
        )

        self.assertEqual(
            result.filenames,
            ("assets/spanish-tts/lesson-1/hola.mp3", "root.mp3"),
        )
        self.assertEqual(result.warnings, ())

    def test_normalizes_separators_and_deduplicates_overlapping_paths(self) -> None:
        nested_directory = self.media_directory / "assets" / "tts"
        nested_directory.mkdir(parents=True)
        (nested_directory / "line.mp3").write_bytes(b"line")

        result = discover_media_files(
            str(self.media_directory),
            ["assets", r"assets\tts", "assets//tts/./"],
        )

        self.assertEqual(result.filenames, ("assets/tts/line.mp3",))
        self.assertEqual(result.warnings, ())

    def test_missing_and_invalid_paths_are_skipped_with_warnings(self) -> None:
        (self.media_directory / "root.mp3").write_bytes(b"root")
        external_directory = Path(self._temporary_directory.name) / "outside"
        external_directory.mkdir()
        configured_paths = [
            "missing",
            "../outside",
            str(external_directory),
            "",
            ".",
            r"C:\outside",
            None,
        ]

        result = discover_media_files(str(self.media_directory), configured_paths)

        self.assertEqual(result.filenames, ("root.mp3",))
        self.assertGreaterEqual(len(result.warnings), len(configured_paths))
        self.assertTrue(any("does not exist" in warning for warning in result.warnings))
        self.assertTrue(any("traversal" in warning for warning in result.warnings))
        self.assertTrue(any("absolute paths" in warning for warning in result.warnings))
        self.assertTrue(
            any("must be a relative path string" in warning for warning in result.warnings)
        )

    def test_non_list_setting_is_reported_without_scanning_it(self) -> None:
        (self.media_directory / "root.mp3").write_bytes(b"root")
        assets = self.media_directory / "assets"
        assets.mkdir()
        (assets / "included.mp3").write_bytes(b"included")

        for invalid_setting in ("assets", None):
            with self.subTest(invalid_setting=invalid_setting):
                result = discover_media_files(
                    str(self.media_directory), invalid_setting
                )

                self.assertEqual(result.filenames, ("root.mp3",))
                self.assertEqual(len(result.warnings), 1)
                self.assertIn("must be a list", result.warnings[0])

    def test_only_unique_root_names_are_safe_for_media_trash(self) -> None:
        self.assertEqual(
            root_level_media_filenames(
                ["root.mp3", "assets/nested.mp3", r"assets\windows.mp3", "root.mp3"]
            ),
            ["root.mp3"],
        )

    def test_does_not_follow_symlink_directories_or_external_file_links(self) -> None:
        assets = self.media_directory / "assets"
        assets.mkdir()
        external_directory = Path(self._temporary_directory.name) / "external"
        external_directory.mkdir()
        external_file = external_directory / "outside.mp3"
        external_file.write_bytes(b"outside")
        root_link = self.media_directory / "root-linked-file.mp3"
        linked_directory = assets / "linked-directory"
        linked_file = assets / "linked-file.mp3"
        try:
            root_link.symlink_to(external_file)
            linked_directory.symlink_to(external_directory, target_is_directory=True)
            linked_file.symlink_to(external_file)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink creation is unavailable: {error}")

        result = discover_media_files(str(self.media_directory), ["assets"])

        self.assertEqual(result.filenames, ())
        self.assertTrue(
            any("symlinked media directory" in warning for warning in result.warnings)
        )
        self.assertTrue(
            any("outside collection.media" in warning for warning in result.warnings)
        )

    def test_rejects_a_configured_symlink_directory(self) -> None:
        external_directory = Path(self._temporary_directory.name) / "external"
        external_directory.mkdir()
        (external_directory / "outside.mp3").write_bytes(b"outside")
        linked_directory = self.media_directory / "linked"
        try:
            linked_directory.symlink_to(external_directory, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink creation is unavailable: {error}")

        result = discover_media_files(str(self.media_directory), ["linked"])

        self.assertEqual(result.filenames, ())
        self.assertTrue(
            any(
                "symbolic-link paths are not scanned" in warning
                for warning in result.warnings
            )
        )


if __name__ == "__main__":
    unittest.main()
