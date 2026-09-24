# Check Media (Lenient)

Find media files in your Anki collection that may no longer be used by any of your notes.

## Why use this add-on?

Some notes refer to pictures or audio using Markdown, JavaScript, or custom templates. Anki's regular **Check Media** may not recognize those references. This add-on also looks for filenames in your note text, so it can find media used in those less common ways. It works alongside Anki's regular check and does not change it.

## How to check your media

1. Open your Anki profile.
2. From the **Tools** menu, choose **Check Media (Lenient)**.
3. Wait for the scan to finish. You can cancel it while it is running.
4. Review the results window. It shows a summary and a copyable list of files that may be unused.

The add-on checks whether each exact filename appears in the text of any note in your collection. Uppercase and lowercase letters must match. Files whose names start with `_`, as well as Anki-generated LaTeX files, are automatically skipped.

Because the add-on looks for filenames in note text rather than interpreting every kind of formatting, a filename mentioned in a note for another reason may count as being used. Treat the results as suggestions and review them before moving any files.

## What happens to files?

Scanning does not delete or move anything. If you choose **Delete Unused**, Anki asks for confirmation and moves all files in the results list to its media trash. They remain recoverable until you empty that trash.

- **Open Media Collection** opens the folder containing your collection's media files.
- **Open Trash Bin** opens Anki's media trash folder.
- **Empty Trash** permanently deletes everything in Anki's media trash, including files from earlier checks. This cannot be undone.

## Requirements

Anki 23.10 (2.1.65) or newer with Qt 6.
