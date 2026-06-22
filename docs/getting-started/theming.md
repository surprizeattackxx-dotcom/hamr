# Theming Hamr

Hamr uses Material Design 3 colors for its UI. This guide explains how to set up dynamic theming so Hamr's colors update automatically when you change your wallpaper.

## Matugen (Recommended)

[Matugen](https://github.com/InioX/matugen) generates Material You colors from images.

### Quick Setup

1.  **Install matugen:**

    === "Arch"

        ```bash
        paru -S matugen
        ```

    === "Gentoo"

        ```bash
        sudo emerge x11-misc/matugen
        ```

    === "Other"

        See [matugen releases](https://github.com/InioX/matugen/releases) for binaries or build from source.

2.  **Download the template:**

    ```bash
    mkdir -p ~/.config/matugen/templates
    curl -o ~/.config/matugen/templates/hamr-colors.json \
      https://raw.githubusercontent.com/stewart86/hamr/main/docs/templates/matugen-colors.json
    ```

3.  **Add to your matugen config** (`~/.config/matugen/config.toml`):

    ```toml
    [templates.hamr_colors]
    input_path = '~/.config/matugen/templates/hamr-colors.json'
    output_path = '~/.config/hamr/colors.json'
    ```

4.  **Generate colors:**
    ```bash
    matugen image /path/to/wallpaper.jpg
    ```

Hamr will automatically pick up the new colors.

### Using Hamr's Wallpaper Plugin

The easiest way: use Hamr's built-in wallpaper plugin (`/wallpaper`). It calls matugen automatically when you select a wallpaper, so colors sync without any manual steps.

## Pywal / Wallust

For [pywal](https://github.com/dylanaraps/pywal) or [wallust](https://codeberg.org/explosion-mental/wallust) users, a template is provided that maps terminal colors to Material Design tokens.

1. **Download the template:**

   ```bash
   # For pywal
   mkdir -p ~/.config/wal/templates
   curl -o ~/.config/wal/templates/hamr-colors.json \
     https://raw.githubusercontent.com/stewart86/hamr/main/docs/templates/pywal-colors.json

   # For wallust
   mkdir -p ~/.config/wallust/templates
   curl -o ~/.config/wallust/templates/hamr-colors.json \
     https://raw.githubusercontent.com/stewart86/hamr/main/docs/templates/pywal-colors.json
   ```

2. **Configure output path:**

   For pywal, colors are generated to `~/.cache/wal/`. Point Hamr to this file in `~/.config/hamr/config.json`:

   ```json
   {
     "paths": {
       "colorsJson": "~/.cache/wal/hamr-colors.json"
     }
   }
   ```

   For wallust, configure the output in `~/.config/wallust/wallust.toml`:

   ```toml
   [[entry]]
   template = "hamr-colors.json"
   target = "~/.config/hamr/colors.json"
   ```

3. **Generate colors:**
   ```bash
   wal -i /path/to/wallpaper.jpg
   # or
   wallust run /path/to/wallpaper.jpg
   ```

## Integration with Other Tools

### DankMaterialShell (DMS)

If you use DankMaterialShell with matugen for wallpaper-based theming, simply add the Hamr template to your existing matugen config. When DMS triggers matugen on wallpaper change, Hamr will receive updated colors from the same run.

### Other Shells (AGS, EWW, etc.)

The same approach works for any tool that uses matugen. Add the Hamr template to your config and all tools will receive colors from the same matugen invocation.

## Manual colors.json

If you prefer not to use a color generator, create `~/.config/hamr/colors.json` manually. The file uses a **flat** format with underscore-separated keys.

Hamr reads **only** the keys below. Material 3 generators (matugen, pywal) emit many more — those extra keys are simply ignored. Any key you omit falls back to its built-in dark default, so a partial file is fine.

| Key | Used for |
| --- | --- |
| `background` | Window background |
| `surface` | Base surface |
| `surface_container_low` / `surface_container` / `surface_container_high` / `surface_container_highest` | Layered surface tiers (low = recessed, highest = raised) |
| `on_surface` | Primary text |
| `on_surface_variant` | Secondary / dimmed text |
| `outline` / `outline_variant` | Borders and separators |
| `primary` | Accent — selection, focus, highlights |
| `on_primary` | Text/icon on `primary` |
| `primary_container` / `on_primary_container` | Accent container and its text |
| `secondary` | Secondary accent |
| `secondary_container` / `on_secondary_container` | Secondary container and its text |
| `shadow` | Read for compatibility; not currently used in any styling |

A complete example using the built-in defaults (copy and recolor):

```json
{
  "background": "#141313",

  "surface": "#141313",
  "surface_container_low": "#1c1b1c",
  "surface_container": "#201f20",
  "surface_container_high": "#2b2a2a",
  "surface_container_highest": "#363435",

  "on_surface": "#e6e1e1",
  "on_surface_variant": "#cbc5ca",

  "outline": "#948f94",
  "outline_variant": "#49464a",

  "primary": "#cbc4cb",
  "on_primary": "#1c1b1c",
  "primary_container": "#2d2a2f",
  "on_primary_container": "#bcb6bc",

  "secondary": "#cac5c8",
  "secondary_container": "#4d4b4d",
  "on_secondary_container": "#cbc5c8",

  "shadow": "#000000"
}
```

Or download it directly:

```bash
curl -o ~/.config/hamr/colors.json \
  https://raw.githubusercontent.com/stewart86/hamr/main/docs/templates/colors.example.json
```

**Note:** Material Theme Builder exports a nested format (`schemes.dark.primary`) which Hamr cannot read directly. Use matugen or manually flatten the structure.

## Custom colors.json Path

By default, Hamr reads from `~/.config/hamr/colors.json`. To use a different path:

```json
{
  "paths": {
    "colorsJson": "~/.local/state/quickshell/user/generated/colors.json"
  }
}
```

## Troubleshooting

**Colors not updating?**

- Check that the colors.json file exists at the expected path
- Verify the JSON is valid (use `jq . ~/.config/hamr/colors.json`)
- Hamr watches the file for changes; updates should apply within seconds

**Warning: "Read of colors.json failed"**

- This is harmless. Hamr uses built-in dark theme defaults when no colors.json exists.
