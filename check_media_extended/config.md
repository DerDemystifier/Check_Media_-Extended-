# Check Media (Extended) configuration

`additional_paths` is a list of directories to search beneath the active profile's `collection.media` folder. Paths are shared across profiles and must be relative; use forward slashes. Each directory is scanned recursively.

For example, set `additional_paths` to include audio files in `collection.media/assets/spanish-tts` (keep any other settings already in the object):

```json
{
    "additional_paths": ["assets/spanish-tts"]
}
```

Missing or invalid paths are skipped with a warning. Unused files in configured paths can be moved to media trash while preserving their relative folder structure.
Anki's built-in Restore Trash does not support nested entries, so nested files must be manually moved back to their original paths.
The add-on's Empty Trash recursively and permanently deletes all trash contents, including nested folders. A note reference to either the full media-relative path or the filename alone counts as a match.
