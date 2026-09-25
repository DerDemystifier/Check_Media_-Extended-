# Check Media (Extended) configuration

`batch_size` and `max_regex_length` control how note searches are divided into batches. Most users can leave these defaults unchanged.

`additional_paths` is a list of directories to search beneath the active profile's `collection.media` folder. Paths are shared across profiles and must be relative; use forward slashes. Each directory is scanned recursively.

For example, set `additional_paths` to include audio files in `collection.media/assets/spanish-tts` (keep any other settings already in the object):

```json
{
	"additional_paths": ["assets/spanish-tts"]
}
```

Missing or invalid paths are skipped with a warning. Nested unused files appear in the report but cannot be moved through Anki's built-in media trash. A note reference to either the full media-relative path or the filename alone counts as a match.
