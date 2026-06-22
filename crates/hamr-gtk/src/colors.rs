//! Colors loading from colors.json

use serde::Deserialize;
use std::path::PathBuf;

/// Material Design 3 colors from colors.json.
///
/// These are the only keys hamr reads. Any other keys in the file - for
/// example the full Material 3 set emitted by matugen or pywal - are ignored.
///
/// `#[serde(default)]` makes every field individually optional: a missing key
/// falls back to its value in [`Colors::default`], so a partial colors.json
/// themes what it can instead of being rejected wholesale. (`shadow` is read
/// but not currently used in any styling.)
#[derive(Debug, Clone, Deserialize)]
#[serde(default)]
pub struct Colors {
    pub background: String,
    pub surface: String,
    pub surface_container: String,
    pub surface_container_low: String,
    pub surface_container_high: String,
    pub surface_container_highest: String,
    pub on_surface: String,
    pub on_surface_variant: String,
    pub outline: String,
    pub outline_variant: String,
    pub primary: String,
    pub primary_container: String,
    pub on_primary_container: String,
    pub on_primary: String,
    pub secondary: String,
    pub secondary_container: String,
    pub on_secondary_container: String,
    pub shadow: String,
}

impl Default for Colors {
    fn default() -> Self {
        Self {
            background: "#141313".to_string(),
            surface: "#141313".to_string(),
            surface_container: "#201f20".to_string(),
            surface_container_low: "#1c1b1c".to_string(),
            surface_container_high: "#2b2a2a".to_string(),
            surface_container_highest: "#363435".to_string(),
            on_surface: "#e6e1e1".to_string(),
            on_surface_variant: "#cbc5ca".to_string(),
            outline: "#948f94".to_string(),
            outline_variant: "#49464a".to_string(),
            primary: "#cbc4cb".to_string(),
            primary_container: "#2d2a2f".to_string(),
            on_primary_container: "#bcb6bc".to_string(),
            on_primary: "#1c1b1c".to_string(),
            secondary: "#cac5c8".to_string(),
            secondary_container: "#4d4b4d".to_string(),
            on_secondary_container: "#cbc5c8".to_string(),
            shadow: "#000000".to_string(),
        }
    }
}

impl Colors {
    /// Load colors from `XDG_CONFIG_HOME/hamr/colors.json`
    pub fn load() -> Self {
        let path = Self::config_path();

        if path.exists()
            && let Ok(content) = std::fs::read_to_string(&path)
        {
            match serde_json::from_str(&content) {
                Ok(colors) => {
                    tracing::info!("Loaded colors from {:?}", path);
                    return colors;
                }
                Err(e) => {
                    tracing::warn!("Failed to parse {:?} ({e}); using default colors", path);
                }
            }
        }

        tracing::info!("Using default colors");
        Self::default()
    }

    fn config_path() -> PathBuf {
        let config_dir = std::env::var("XDG_CONFIG_HOME").map_or_else(
            |_| {
                dirs::home_dir()
                    .map(|h| h.join(".config"))
                    .unwrap_or_default()
            },
            PathBuf::from,
        );

        config_dir.join("hamr").join("colors.json")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn partial_json_defaults_only_missing_keys() {
        // A file that sets primary and omits everything else (including the
        // previously-required `surface`) must keep `primary` and fall back to
        // defaults for the rest - not reject the whole file.
        let colors: Colors = serde_json::from_str(r##"{"primary": "#ff0000"}"##).unwrap();
        assert_eq!(colors.primary, "#ff0000");
        assert_eq!(colors.surface, Colors::default().surface);
        assert_eq!(colors.on_surface, Colors::default().on_surface);
    }

    #[test]
    fn unknown_material3_keys_are_ignored() {
        // Keys from the full Material 3 set (matugen/pywal) that hamr does not
        // read must be ignored rather than causing a parse failure.
        let json = r##"{
            "primary": "#abcdef",
            "scrim": "#000000",
            "inverse_surface": "#ffffff",
            "tertiary": "#123456",
            "on_error_container": "#654321"
        }"##;
        let colors: Colors = serde_json::from_str(json).unwrap();
        assert_eq!(colors.primary, "#abcdef");
    }
}
