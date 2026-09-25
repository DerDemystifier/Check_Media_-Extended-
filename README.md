# Check Media (Extended)

Find media files in your Anki collection that may no longer be used by any of your notes.

## Why use this add-on?

Some notes refer to pictures or audio using Markdown, JavaScript, or custom templates. Anki's regular **Check Media** may not recognize those references, as it only handles basic `<img>` for images or `[sound:]` for audio, etc... This add-on also looks for filenames in your note text, so it can find media used in those less common ways. It works alongside Anki's regular check and does not change it. If you want a more thorough search, use this addon. Especially built for power users. If you don't know what I'm talking about, this means you haven't faced this problem before, and so this addon is not for you (yet).

## How to check your media

1. Open your Anki profile.
2. From the **Tools** menu, choose **Check Media (Extended)**.
3. Wait for the scan to finish. You can cancel it while it is running.
4. Review the results window. It shows a summary and a copyable list of files that may be unused.

The add-on checks whether each exact filename appears in the text of any note in your collection. Uppercase and lowercase letters must match. Files whose names start with `_`, as well as Anki-generated LaTeX files, are automatically skipped.

## Search additional media folders

To include files stored in subfolders of `collection.media`, open **Tools → Add-ons**, select **Check Media (Extended)**, and choose **Config**. Set `additional_paths` to a list of paths relative to `collection.media`. For example (keep any other settings already in the object):

```json
{
	"additional_paths": ["assets/spanish-tts"]
}
```

Configured folders are scanned recursively. Use forward slashes; absolute paths and paths that leave `collection.media` are rejected. This add-on setting is shared across profiles, so each profile uses the same list; a folder missing from the active profile is skipped with a warning. A nested file counts as used if a note mentions its relative path or its basename, so a basename-only reference can conservatively keep same-named files in multiple folders.

Because the add-on looks for filenames in note text rather than interpreting every kind of formatting, a filename mentioned in a note for another reason may count as being used. Treat the results as suggestions and review them before moving any files.

## What happens to files?

Scanning does not delete or move anything. **Move Unused Files to Trash** asks for confirmation and moves unused files from the root and configured subfolders of `collection.media` to Anki's media trash. Nested files keep their relative folder structure there.

Anki's built-in **Restore Trash** does not support nested entries. To recover a nested file, manually move it from the matching path under `media.trash` back to its original relative path under `collection.media` before emptying the trash. The add-on's **Empty Trash** recursively and permanently deletes all contents of `media.trash`, including nested folders and files from previous checks; it cannot be undone. Do not use it until you have manually restored any nested files you want to keep.

- **Open Media Collection** opens the folder containing your collection's media files.
- **Open Trash Bin** opens Anki's media trash folder.
- **Empty Trash** recursively and permanently deletes everything in Anki's media trash, including nested contents and files from earlier checks. This cannot be undone.

## Requirements

Anki 23.10 (2.1.65) or newer with Qt 6.
