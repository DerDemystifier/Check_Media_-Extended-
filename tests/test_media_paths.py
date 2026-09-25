from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import _addon_path  # noqa: F401
from media_paths import (
    discover_media_files,
    empty_media_trash,
    media_trash_directory,
    prepare_media_trash_destination,
)


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

        result = discover_media_files(str(self.media_directory), ["assets/spanish-tts"])

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
                result = discover_media_files(str(self.media_directory), invalid_setting)

                self.assertEqual(result.filenames, ("root.mp3",))
                self.assertEqual(len(result.warnings), 1)
                self.assertIn("must be a list", result.warnings[0])

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
        self.assertTrue(any("symlinked media directory" in warning for warning in result.warnings))
        self.assertTrue(any("outside collection.media" in warning for warning in result.warnings))

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
            any("symbolic-link paths are not scanned" in warning for warning in result.warnings)
        )


class MediaTrashTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.profile_directory = Path(self._temporary_directory.name)
        self.media_directory = self.profile_directory / "collection.media"
        self.media_directory.mkdir()
        self.trash_directory = Path(media_trash_directory(str(self.media_directory)))

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def test_prepares_nested_destination_with_matching_relative_path(self) -> None:
        source = self.media_directory / "assets" / "spanish-tts" / "lesson-1" / "hola.mp3"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"audio")

        destination = prepare_media_trash_destination(
            str(self.media_directory), "assets/spanish-tts/lesson-1/hola.mp3"
        )

        self.assertEqual(
            destination,
            self.trash_directory / "assets" / "spanish-tts" / "lesson-1" / "hola.mp3",
        )
        self.assertTrue(destination.parent.is_dir())
        self.assertTrue(source.is_file())
        self.assertFalse(destination.exists())

    def test_prepares_root_file_destination(self) -> None:
        (self.media_directory / "root.mp3").write_bytes(b"audio")

        destination = prepare_media_trash_destination(str(self.media_directory), "root.mp3")

        self.assertEqual(destination, self.trash_directory / "root.mp3")
        self.assertTrue(self.trash_directory.is_dir())

    def test_rejects_unsafe_media_relative_paths(self) -> None:
        for filename in (
            "",
            ".",
            "assets/./file.mp3",
            "assets/../outside.mp3",
            "/outside.mp3",
            r"C:\outside.mp3",
            r"\\server\share\outside.mp3",
            "assets//file.mp3",
        ):
            with self.subTest(filename=filename):
                with self.assertRaises(ValueError):
                    prepare_media_trash_destination(str(self.media_directory), filename)
        self.assertFalse(self.trash_directory.exists())

    def test_refuses_to_overwrite_an_existing_trash_destination(self) -> None:
        relative_path = Path("assets") / "nested.mp3"
        source = self.media_directory / relative_path
        source.parent.mkdir(parents=True)
        source.write_bytes(b"source")
        destination = self.trash_directory / relative_path
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"existing trash")

        with self.assertRaises(FileExistsError):
            prepare_media_trash_destination(str(self.media_directory), "assets/nested.mp3")

        self.assertEqual(destination.read_bytes(), b"existing trash")
        self.assertEqual(source.read_bytes(), b"source")

    def test_rejects_missing_media_files(self) -> None:
        with self.assertRaises(FileNotFoundError):
            prepare_media_trash_destination(str(self.media_directory), "assets/missing.mp3")

    def test_refuses_symlinked_source_and_trash_directories(self) -> None:
        external_directory = self.profile_directory / "external"
        external_directory.mkdir()
        external_file = external_directory / "outside.mp3"
        external_file.write_bytes(b"outside")
        assets = self.media_directory / "assets"
        assets.mkdir()
        try:
            (assets / "linked.mp3").symlink_to(external_file)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink creation is unavailable: {error}")

        with self.assertRaises(ValueError):
            prepare_media_trash_destination(str(self.media_directory), "assets/linked.mp3")

        self.trash_directory.mkdir()
        linked_trash_subdirectory = self.trash_directory / "assets"
        linked_trash_subdirectory.symlink_to(external_directory, target_is_directory=True)
        (self.media_directory / "assets" / "ordinary.mp3").write_bytes(b"ordinary")
        with self.assertRaises(ValueError):
            prepare_media_trash_destination(str(self.media_directory), "assets/ordinary.mp3")
        self.assertEqual(external_file.read_bytes(), b"outside")

    def test_empty_trash_recursively_removes_contents_and_keeps_root(self) -> None:
        self.trash_directory.mkdir()
        (self.trash_directory / "root.mp3").write_bytes(b"root")
        nested = self.trash_directory / "assets" / "lesson-1" / "hola.mp3"
        nested.parent.mkdir(parents=True)
        nested.write_bytes(b"nested")

        empty_media_trash(str(self.media_directory))

        self.assertTrue(self.trash_directory.is_dir())
        self.assertEqual(list(self.trash_directory.iterdir()), [])

    def test_empty_trash_unlinks_symlinks_without_following_them(self) -> None:
        external_directory = self.profile_directory / "external"
        external_directory.mkdir()
        external_file = external_directory / "keep.mp3"
        external_file.write_bytes(b"keep")
        nested_directory = self.trash_directory / "assets"
        nested_directory.mkdir(parents=True)
        link = nested_directory / "external"
        try:
            link.symlink_to(external_directory, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink creation is unavailable: {error}")

        empty_media_trash(str(self.media_directory))

        self.assertFalse(link.exists())
        self.assertTrue(external_file.is_file())
        self.assertEqual(external_file.read_bytes(), b"keep")
        self.assertEqual(list(self.trash_directory.iterdir()), [])

    def test_empty_trash_refuses_a_linked_trash_root(self) -> None:
        external_directory = self.profile_directory / "external"
        external_directory.mkdir()
        external_file = external_directory / "keep.mp3"
        external_file.write_bytes(b"keep")
        try:
            self.trash_directory.symlink_to(external_directory, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink creation is unavailable: {error}")

        with self.assertRaises(ValueError):
            empty_media_trash(str(self.media_directory))
        self.assertTrue(external_file.is_file())

    def test_empty_trash_without_a_trash_folder_is_a_noop(self) -> None:
        empty_media_trash(str(self.media_directory))
        self.assertFalse(self.trash_directory.exists())


if __name__ == "__main__":
    unittest.main()
