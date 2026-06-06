//! Material Design 3 colors for the TUI.
//!
//! Loads the same `~/.config/hamr/colors.json` the GTK client uses so the TUI
//! follows the wallpaper/matugen theme. Falls back to a built-in dark palette
//! per-field when the file is missing or a key is absent.

use ratatui::style::Color;
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::LazyLock;

pub struct Palette {
    pub bg: Color,
    pub surface: Color,
    pub surface_high: Color,
    pub on_surface: Color,
    pub subtext: Color,
    pub outline: Color,
    pub primary: Color,
    pub primary_container: Color,
    pub secondary: Color,
    pub success: Color,
    pub error: Color,
    pub warning: Color,
}

impl Default for Palette {
    fn default() -> Self {
        Self {
            bg: Color::Rgb(0x14, 0x13, 0x13),
            surface: Color::Rgb(0x20, 0x1f, 0x20),
            surface_high: Color::Rgb(0x2b, 0x2a, 0x2a),
            on_surface: Color::Rgb(0xe6, 0xe1, 0xe1),
            subtext: Color::Rgb(0xcb, 0xc5, 0xca),
            outline: Color::Rgb(0x94, 0x8f, 0x94),
            primary: Color::Rgb(0xcb, 0xc4, 0xcb),
            primary_container: Color::Rgb(0x2d, 0x2a, 0x2f),
            secondary: Color::Rgb(0xca, 0xc5, 0xc8),
            success: Color::Rgb(0xb5, 0xcc, 0xba),
            error: Color::Rgb(0xff, 0xb4, 0xab),
            warning: Color::Rgb(0xff, 0xd9, 0x66),
        }
    }
}

fn parse_hex(s: &str) -> Option<Color> {
    let h = s.trim().trim_start_matches('#');
    if h.len() != 6 {
        return None;
    }
    let r = u8::from_str_radix(&h[0..2], 16).ok()?;
    let g = u8::from_str_radix(&h[2..4], 16).ok()?;
    let b = u8::from_str_radix(&h[4..6], 16).ok()?;
    Some(Color::Rgb(r, g, b))
}

fn config_path() -> PathBuf {
    let config_dir = std::env::var("XDG_CONFIG_HOME").map_or_else(
        |_| {
            std::env::var("HOME")
                .map(|h| PathBuf::from(h).join(".config"))
                .unwrap_or_default()
        },
        PathBuf::from,
    );
    config_dir.join("hamr").join("colors.json")
}

impl Palette {
    fn load() -> Self {
        let mut p = Self::default();
        let Ok(content) = std::fs::read_to_string(config_path()) else {
            return p;
        };
        let Ok(map) = serde_json::from_str::<HashMap<String, String>>(&content) else {
            return p;
        };
        let set = |slot: &mut Color, key: &str| {
            if let Some(c) = map.get(key).and_then(|v| parse_hex(v)) {
                *slot = c;
            }
        };
        set(&mut p.bg, "background");
        set(&mut p.surface, "surface_container");
        set(&mut p.surface_high, "surface_container_high");
        set(&mut p.on_surface, "on_surface");
        set(&mut p.subtext, "on_surface_variant");
        set(&mut p.outline, "outline");
        set(&mut p.primary, "primary");
        set(&mut p.primary_container, "primary_container");
        set(&mut p.secondary, "secondary");
        set(&mut p.error, "error");
        // No MD3 slot for success/warning; tertiary is the closest accent.
        set(&mut p.success, "tertiary");
        p
    }
}

static PALETTE: LazyLock<Palette> = LazyLock::new(Palette::load);

pub fn bg() -> Color {
    PALETTE.bg
}
pub fn surface() -> Color {
    PALETTE.surface
}
pub fn surface_high() -> Color {
    PALETTE.surface_high
}
pub fn on_surface() -> Color {
    PALETTE.on_surface
}
pub fn subtext() -> Color {
    PALETTE.subtext
}
pub fn outline() -> Color {
    PALETTE.outline
}
pub fn primary() -> Color {
    PALETTE.primary
}
pub fn primary_container() -> Color {
    PALETTE.primary_container
}
pub fn secondary() -> Color {
    PALETTE.secondary
}
pub fn success() -> Color {
    PALETTE.success
}
pub fn error() -> Color {
    PALETTE.error
}
pub fn warning() -> Color {
    PALETTE.warning
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_hex_valid() {
        assert_eq!(parse_hex("#141313"), Some(Color::Rgb(0x14, 0x13, 0x13)));
        assert_eq!(parse_hex("cbc4cb"), Some(Color::Rgb(0xcb, 0xc4, 0xcb)));
    }

    #[test]
    fn parse_hex_invalid() {
        assert_eq!(parse_hex("#xyz"), None);
        assert_eq!(parse_hex("#12345"), None);
        assert_eq!(parse_hex(""), None);
    }

    #[test]
    fn default_palette_matches_legacy_dark() {
        let p = Palette::default();
        assert_eq!(p.bg, Color::Rgb(0x14, 0x13, 0x13));
        assert_eq!(p.warning, Color::Rgb(0xff, 0xd9, 0x66));
    }
}
