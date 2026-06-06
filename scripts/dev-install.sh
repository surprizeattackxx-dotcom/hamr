#!/usr/bin/env bash
# Build the workspace in release mode and install it to ~/.local/bin, then
# restart the systemd user services so the running launcher picks up the build.
#
# Binaries in ~/.local/bin use the production socket (hamr.sock); binaries run
# straight from target/ use hamr-dev.sock, which splits the CLI from the daemon.
# That's why we install rather than point systemd at target/.
set -euo pipefail

BIN_DIR="${HAMR_BIN_DIR:-$HOME/.local/bin}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Building release binaries"
cargo build --release -p hamr-cli -p hamr-daemon -p hamr-gtk -p hamr-tui

have_systemd=0
if command -v systemctl >/dev/null && systemctl --user list-unit-files hamr-daemon.service >/dev/null 2>&1; then
    have_systemd=1
fi

if [ "$have_systemd" = 1 ]; then
    echo "==> Stopping services"
    systemctl --user stop hamr-gtk hamr-daemon 2>/dev/null || true
    sleep 1
fi

echo "==> Installing to $BIN_DIR"
mkdir -p "$BIN_DIR"
for bin in hamr hamr-daemon hamr-gtk hamr-tui; do
    install -m755 "target/release/$bin" "$BIN_DIR/$bin"
done

if [ "$have_systemd" = 1 ]; then
    # Repoint services at the freshly installed binaries (idempotent drop-ins).
    daemon_exec=$(systemctl --user cat hamr-daemon.service | grep '^ExecStart=' | head -1 \
        | sed "s#[^ \"']*/hamr-daemon#$BIN_DIR/hamr-daemon#")
    mkdir -p ~/.config/systemd/user/hamr-daemon.service.d ~/.config/systemd/user/hamr-gtk.service.d
    printf '[Service]\nExecStart=\n%s\n' "$daemon_exec" \
        > ~/.config/systemd/user/hamr-daemon.service.d/override.conf
    printf '[Service]\nExecStart=\nExecStart=%s/hamr-gtk\n' "$BIN_DIR" \
        > ~/.config/systemd/user/hamr-gtk.service.d/override.conf
    systemctl --user daemon-reload
    echo "==> Starting services"
    systemctl --user start hamr-daemon
    sleep 2
    systemctl --user start hamr-gtk
    echo "==> Live: $(hamr status 2>/dev/null | head -1)"
else
    echo "==> Installed. Start with: hamr"
fi
