# dmenu Mode

`hamr dmenu` turns Hamr into a generic **picker** — the same role as
[`dmenu`](https://tools.suckless.org/dmenu/), `rofi -dmenu`, or `fuzzel
--dmenu`. Pipe it a list, the user chooses one, and the choice is printed to
stdout. It runs as a one-shot, daemon-independent process, so it works in
scripts even when the Hamr launcher isn't running.

## Usage

```bash
items | hamr dmenu [-p/--prompt <text>]
```

- **Input:** newline-separated items on **stdin** (blank lines are ignored).
- **Output:** the chosen line is printed to **stdout**.
- **Exit code:** `0` when an item is chosen or text is typed, `1` when
  cancelled with `Esc`.

## Keys

| Key | Action |
|-----|--------|
| Type | Fuzzy-filter the list (matched letters are highlighted) |
| `↑` / `↓` | Move selection |
| `Enter` | Choose the selected item — or, if nothing matches, return exactly what you typed |
| `Esc` | Cancel (no output, exit code `1`) |

## Examples

```bash
# Basic pick
printf 'one\ntwo\nthree\n' | hamr dmenu

# Custom prompt and use the result
choice=$(ls ~/scripts | hamr dmenu -p 'Run:') && exec "$HOME/scripts/$choice"

# Cancellation handling
pick=$(some-list | hamr dmenu) || { echo "cancelled"; exit 0; }

# Create-or-pick: typing a value that isn't listed returns that text
tag=$(cat ~/.tags | hamr dmenu -p 'Tag:')   # prints a new tag if you type one
```

## File previews

When an item is a path to an existing file, the chooser shows a preview panel
for the selected item — mirroring the behaviour of the `files` plugin:

- **Images** (`png`, `jpg`, `jpeg`, `gif`, `webp`, `bmp`, `svg`, `ico`, `avif`)
  render as a thumbnail.
- **Text / Markdown** files show their contents (capped at 64 KiB; `.md` /
  `.markdown` render as Markdown).
- Other files show size and path metadata.

Pipe **full paths** to enable this:

```bash
fd . ~/Pictures | hamr dmenu          # image previews
fd -e md ~/notes | hamr dmenu         # markdown previews
```

Bare filenames (e.g. `ls *.qml`) have no previews because the paths don't
resolve from the chooser's working directory — use `ls "$PWD"/*.qml` or `fd`.

## Notes

- Each invocation is its own isolated window; running `hamr dmenu` while the
  normal launcher is open does not interfere with it.
- Only the selection is written to stdout; logs go to stderr, so command
  substitution (`$(... | hamr dmenu)`) stays clean.
