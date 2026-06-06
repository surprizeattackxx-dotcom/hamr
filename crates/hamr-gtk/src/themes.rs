//! Built-in theme presets

use crate::colors::Colors;

/// Return a built-in theme by name, or None if unknown.
pub fn get_preset(name: &str) -> Option<Colors> {
    match name {
        "catppuccin-mocha" => Some(catppuccin_mocha()),
        "catppuccin-latte" => Some(catppuccin_latte()),
        "gruvbox-dark" => Some(gruvbox_dark()),
        "gruvbox-light" => Some(gruvbox_light()),
        "nord" => Some(nord()),
        "dracula" => Some(dracula()),
        "rose-pine" => Some(rose_pine()),
        "rose-pine-dawn" => Some(rose_pine_dawn()),
        "tokyo-night" => Some(tokyo_night()),
        "one-dark" => Some(one_dark()),
        _ => None,
    }
}

/// List all available preset names.
pub fn preset_names() -> &'static [&'static str] {
    &[
        "catppuccin-mocha",
        "catppuccin-latte",
        "gruvbox-dark",
        "gruvbox-light",
        "nord",
        "dracula",
        "rose-pine",
        "rose-pine-dawn",
        "tokyo-night",
        "one-dark",
    ]
}

fn catppuccin_mocha() -> Colors {
    Colors {
        background:                "#1e1e2e".into(),
        surface:                   "#1e1e2e".into(),
        surface_container:         "#313244".into(),
        surface_container_low:     "#181825".into(),
        surface_container_high:    "#45475a".into(),
        surface_container_highest: "#585b70".into(),
        on_surface:                "#cdd6f4".into(),
        on_surface_variant:        "#bac2de".into(),
        outline:                   "#7f849c".into(),
        outline_variant:           "#45475a".into(),
        primary:                   "#cba6f7".into(),
        primary_container:         "#3d2f5c".into(),
        on_primary_container:      "#e0cbff".into(),
        on_primary:                "#11111b".into(),
        secondary:                 "#b4befe".into(),
        secondary_container:       "#313263".into(),
        on_secondary_container:    "#d0d8ff".into(),
        shadow:                    "#11111b".into(),
    }
}

fn catppuccin_latte() -> Colors {
    Colors {
        background:                "#eff1f5".into(),
        surface:                   "#eff1f5".into(),
        surface_container:         "#ccd0da".into(),
        surface_container_low:     "#e6e9ef".into(),
        surface_container_high:    "#bcc0cc".into(),
        surface_container_highest: "#acb0be".into(),
        on_surface:                "#4c4f69".into(),
        on_surface_variant:        "#5c5f77".into(),
        outline:                   "#8c8fa1".into(),
        outline_variant:           "#ccd0da".into(),
        primary:                   "#8839ef".into(),
        primary_container:         "#ddc9ff".into(),
        on_primary_container:      "#4a0087".into(),
        on_primary:                "#eff1f5".into(),
        secondary:                 "#7287fd".into(),
        secondary_container:       "#c8ccff".into(),
        on_secondary_container:    "#2a3287".into(),
        shadow:                    "#acb0be".into(),
    }
}

fn gruvbox_dark() -> Colors {
    Colors {
        background:                "#282828".into(),
        surface:                   "#282828".into(),
        surface_container:         "#3c3836".into(),
        surface_container_low:     "#1d2021".into(),
        surface_container_high:    "#504945".into(),
        surface_container_highest: "#665c54".into(),
        on_surface:                "#ebdbb2".into(),
        on_surface_variant:        "#d5c4a1".into(),
        outline:                   "#928374".into(),
        outline_variant:           "#504945".into(),
        primary:                   "#d3869b".into(),
        primary_container:         "#4a2840".into(),
        on_primary_container:      "#ebbacc".into(),
        on_primary:                "#1d2021".into(),
        secondary:                 "#83a598".into(),
        secondary_container:       "#1e3836".into(),
        on_secondary_container:    "#a9d5c9".into(),
        shadow:                    "#1d2021".into(),
    }
}

fn gruvbox_light() -> Colors {
    Colors {
        background:                "#fbf1c7".into(),
        surface:                   "#fbf1c7".into(),
        surface_container:         "#ebdbb2".into(),
        surface_container_low:     "#f9f5d7".into(),
        surface_container_high:    "#d5c4a1".into(),
        surface_container_highest: "#bdae93".into(),
        on_surface:                "#3c3836".into(),
        on_surface_variant:        "#504945".into(),
        outline:                   "#928374".into(),
        outline_variant:           "#d5c4a1".into(),
        primary:                   "#b16286".into(),
        primary_container:         "#f0d0dd".into(),
        on_primary_container:      "#5a1a3a".into(),
        on_primary:                "#fbf1c7".into(),
        secondary:                 "#458588".into(),
        secondary_container:       "#c8e8ea".into(),
        on_secondary_container:    "#1a4446".into(),
        shadow:                    "#bdae93".into(),
    }
}

fn nord() -> Colors {
    Colors {
        background:                "#2e3440".into(),
        surface:                   "#2e3440".into(),
        surface_container:         "#3b4252".into(),
        surface_container_low:     "#242933".into(),
        surface_container_high:    "#434c5e".into(),
        surface_container_highest: "#4c566a".into(),
        on_surface:                "#eceff4".into(),
        on_surface_variant:        "#d8dee9".into(),
        outline:                   "#81a1c1".into(),
        outline_variant:           "#434c5e".into(),
        primary:                   "#88c0d0".into(),
        primary_container:         "#1e3a4a".into(),
        on_primary_container:      "#b8dde6".into(),
        on_primary:                "#2e3440".into(),
        secondary:                 "#81a1c1".into(),
        secondary_container:       "#2a3a50".into(),
        on_secondary_container:    "#b4cce0".into(),
        shadow:                    "#191d23".into(),
    }
}

fn dracula() -> Colors {
    Colors {
        background:                "#282a36".into(),
        surface:                   "#282a36".into(),
        surface_container:         "#44475a".into(),
        surface_container_low:     "#21222c".into(),
        surface_container_high:    "#4e5166".into(),
        surface_container_highest: "#6272a4".into(),
        on_surface:                "#f8f8f2".into(),
        on_surface_variant:        "#d0d0d0".into(),
        outline:                   "#6272a4".into(),
        outline_variant:           "#44475a".into(),
        primary:                   "#bd93f9".into(),
        primary_container:         "#3a2060".into(),
        on_primary_container:      "#ddc6ff".into(),
        on_primary:                "#21222c".into(),
        secondary:                 "#ff79c6".into(),
        secondary_container:       "#5a1a40".into(),
        on_secondary_container:    "#ffc0e6".into(),
        shadow:                    "#191a21".into(),
    }
}

fn rose_pine() -> Colors {
    Colors {
        background:                "#191724".into(),
        surface:                   "#1f1d2e".into(),
        surface_container:         "#26233a".into(),
        surface_container_low:     "#16141f".into(),
        surface_container_high:    "#312e45".into(),
        surface_container_highest: "#403d52".into(),
        on_surface:                "#e0def4".into(),
        on_surface_variant:        "#908caa".into(),
        outline:                   "#6e6a86".into(),
        outline_variant:           "#26233a".into(),
        primary:                   "#c4a7e7".into(),
        primary_container:         "#34224a".into(),
        on_primary_container:      "#dcc8f6".into(),
        on_primary:                "#191724".into(),
        secondary:                 "#9ccfd8".into(),
        secondary_container:       "#1a3e44".into(),
        on_secondary_container:    "#c6edf2".into(),
        shadow:                    "#0f0e17".into(),
    }
}

fn rose_pine_dawn() -> Colors {
    Colors {
        background:                "#faf4ed".into(),
        surface:                   "#fffaf3".into(),
        surface_container:         "#f2e9de".into(),
        surface_container_low:     "#faf4ed".into(),
        surface_container_high:    "#e4dfda".into(),
        surface_container_highest: "#d4e2e4".into(),
        on_surface:                "#575279".into(),
        on_surface_variant:        "#797593".into(),
        outline:                   "#9893a5".into(),
        outline_variant:           "#dfdad9".into(),
        primary:                   "#907aa9".into(),
        primary_container:         "#e8def8".into(),
        on_primary_container:      "#40326a".into(),
        on_primary:                "#faf4ed".into(),
        secondary:                 "#56949f".into(),
        secondary_container:       "#cce8ec".into(),
        on_secondary_container:    "#1a4a52".into(),
        shadow:                    "#c4c0c0".into(),
    }
}

fn tokyo_night() -> Colors {
    Colors {
        background:                "#1a1b26".into(),
        surface:                   "#1a1b26".into(),
        surface_container:         "#24283b".into(),
        surface_container_low:     "#16161e".into(),
        surface_container_high:    "#292e42".into(),
        surface_container_highest: "#3b4261".into(),
        on_surface:                "#c0caf5".into(),
        on_surface_variant:        "#a9b1d6".into(),
        outline:                   "#565f89".into(),
        outline_variant:           "#292e42".into(),
        primary:                   "#7aa2f7".into(),
        primary_container:         "#1a2a5a".into(),
        on_primary_container:      "#b0c8ff".into(),
        on_primary:                "#16161e".into(),
        secondary:                 "#bb9af7".into(),
        secondary_container:       "#2a1a5a".into(),
        on_secondary_container:    "#dbc8ff".into(),
        shadow:                    "#0d0e14".into(),
    }
}

fn one_dark() -> Colors {
    Colors {
        background:                "#282c34".into(),
        surface:                   "#282c34".into(),
        surface_container:         "#31343e".into(),
        surface_container_low:     "#21252b".into(),
        surface_container_high:    "#3e4452".into(),
        surface_container_highest: "#4b5263".into(),
        on_surface:                "#abb2bf".into(),
        on_surface_variant:        "#9da5b4".into(),
        outline:                   "#5c6370".into(),
        outline_variant:           "#3e4452".into(),
        primary:                   "#c678dd".into(),
        primary_container:         "#3a1a4a".into(),
        on_primary_container:      "#e4b8f4".into(),
        on_primary:                "#21252b".into(),
        secondary:                 "#61afef".into(),
        secondary_container:       "#1a3050".into(),
        on_secondary_container:    "#aad4f8".into(),
        shadow:                    "#16191e".into(),
    }
}
