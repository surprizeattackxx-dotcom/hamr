# Changelog

This fork tracks [Stewart86/hamr](https://github.com/Stewart86/hamr) and adds
features on top. Notable changes since forking from upstream `v1.1.0`:

## Unreleased (fork)

### Added

- **AI plugin** (`ai`): Claude-backed assistant via `claude -p` — streaming,
  conversational follow-ups, vision (screenshot/clipboard Q&A), selected-text
  actions, modes (`explain`/`eli5`/`code`/`cmd`/`fix`/`grammar`/`proofread`/
  `rewrite`/`tldr`/`translate`/…) and inline model switching
  (`opus`/`sonnet`/`haiku <query>`).
- **units**: unit, number-base and live currency conversion
  (`100 km to mi`, `255 to hex`, `100 usd to eur`; rates cached 12h).
- **weather**: current conditions + 3-day forecast card (wttr.in, cached 15m).
- **translate**: instant no-LLM translation with source auto-detect.
- **websearch**: bang-style dispatcher across 28 engines.
- **sysinfo**: live CPU/RAM/disk/temp/net/uptime dashboard card.
- **worldclock**: current time in any city or IANA zone.
- **kill**: find and terminate a process (`!` prefix = SIGKILL).
- **random**: dice, coin flips, ranges, list picks, lorem ipsum.
- **devtools**: offline base64/url/hex/jwt/hash/uuid/epoch transforms.
- **passgen**: password and passphrase generator.
- **qrcode**: inline ASCII QR + PNG export.
- **GTK**: launcher elevation shadow, focus glow, selection accent bar and an
  entrance animation — each toggleable via `appearance` config
  (`elevationShadow`/`openAnimation`/`selectionAccent`).
- **GTK**: `Alt+1…9` jumps to and launches the Nth visible result.
- Matugen theming: both the GTK launcher and the TUI follow the wallpaper
  palette from `~/.config/hamr/colors.json`.
- `scripts/dev-install.sh` (build + install to `~/.local/bin` + restart) and
  `scripts/smoke-test-plugins.sh` (per-plugin JSON smoke tests).

### Changed

- Stdio plugins honor their manifest `handler.command` (any interpreter, e.g.
  `python3 handler.py`) and no longer need the executable bit.
- README reframed as an active fork; plugin docs note `handler.command`.

### Fixed

- Core: `PluginProcess::spawn` parsed the manifest `command` instead of always
  exec'ing `handler.py` directly (which had required `chmod +x`).
- Restored the executable bit on all bundled handlers.
- `weather`: strip wttr.in descriptions so Markdown bold renders.
