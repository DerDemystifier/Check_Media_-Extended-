# Check Media (Lenient)

An Anki 23.10 / 2.1.65+ (Qt6) add-on that finds media whose exact, case-sensitive filename is absent from all raw note fields.  Unlike stock **Check Media**, it recognizes arbitrary Markdown, JavaScript, and custom markup references because it checks raw substrings after using Anki's `re:` search only as a prefilter.

## Install for development

Copy the `better_check_media_lenient` folder into Anki's `addons21` directory, then restart Anki.  The **Tools** menu will contain **Check Media (Lenient)**; stock **Check Media** is unchanged.

The checker excludes underscore-prefixed and `latex-` generated files. Results are never deleted automatically.  Selected files are moved only via Anki's recoverable media trash.

## Test

From this directory, run `python -m unittest discover -s tests -v` using any Python 3.9+ interpreter.  Tests do not require Anki or Qt.
