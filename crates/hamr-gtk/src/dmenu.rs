//! Standalone dmenu mode: a one-shot, scriptable picker.
//!
//! Reads newline-separated items from stdin, shows an isolated layer-shell
//! window, and prints the chosen item to stdout (exit 0). Cancelling with Esc
//! exits 1 with no output. If nothing matches the query, Enter returns the
//! typed text verbatim (accept-typed-input), so it can also create new values.
//!
//! Unlike the main launcher this never talks to the daemon, so it works as a
//! generic chooser even when hamr is not running. It reuses the launcher's
//! result list, preview panel, theme, and fuzzy search engine (including the
//! match highlighting), but not the daemon/core event machinery.

use std::cell::RefCell;
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::rc::Rc;

use gtk4::gdk;
use gtk4::glib;
use gtk4::prelude::*;
use gtk4_layer_shell::{Edge, KeyboardMode, Layer, LayerShell};
use tracing_subscriber::{EnvFilter, fmt, prelude::*};

use hamr_core::search::{SearchEngine, Searchable, SearchableSource};
use hamr_types::{MetadataItem, PreviewData, ResultItem};

use crate::config::Theme;
use crate::widgets::preview_panel::PreviewPanel;
use crate::widgets::result_list::ResultList;

/// Maximum number of rows rendered at once (type to filter a larger set).
const MAX_RESULTS: usize = 100;
/// Maximum bytes read for a text preview.
const MAX_PREVIEW_BYTES: u64 = 64 * 1024;
const IMAGE_EXTS: &[&str] = &[
    "png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "ico", "avif",
];

/// Options parsed from argv when running in dmenu mode.
pub struct DmenuOptions {
    pub prompt: Option<String>,
}

/// Parse `--dmenu` / `--prompt` from argv. Returns `Some` only in dmenu mode.
pub fn parse_args() -> Option<DmenuOptions> {
    let mut args = std::env::args().skip(1);
    let mut is_dmenu = false;
    let mut prompt = None;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--dmenu" => is_dmenu = true,
            "--prompt" => prompt = args.next(),
            other if other.starts_with("--prompt=") => {
                prompt = Some(other["--prompt=".len()..].to_string());
            }
            _ => {}
        }
    }
    is_dmenu.then_some(DmenuOptions { prompt })
}

/// Entry point for dmenu mode. Returns an exit code only on setup failure;
/// a successful pick or cancel exits the process directly (so the exit code
/// reaches the calling script).
pub fn run(options: DmenuOptions) -> glib::ExitCode {
    setup_logging();

    // dmenu needs a display + layer-shell, but never the daemon.
    if !crate::wait_for_display() {
        eprintln!("hamr dmenu: Wayland display not available");
        return glib::ExitCode::FAILURE;
    }
    if !crate::compositor::Compositor::detect().supports_layer_shell() {
        eprintln!("hamr dmenu: compositor does not support wlr-layer-shell");
        return glib::ExitCode::FAILURE;
    }

    let items = Rc::new(read_stdin_items());
    let prompt = Rc::new(options.prompt);

    // NON_UNIQUE so each invocation is its own instance; otherwise GTK's
    // single-instance routing would hand off to a running hamr-gtk launcher.
    let app = gtk4::Application::builder()
        .application_id("org.hamr.Dmenu")
        .flags(gtk4::gio::ApplicationFlags::NON_UNIQUE)
        .build();

    app.connect_activate(move |app| {
        build_window(app, &items, prompt.as_deref());
    });

    // We already consumed argv; don't let GTK re-parse `--dmenu`/`--prompt`.
    app.run_with_args::<&str>(&[])
}

/// Log to stderr so stdout carries only the selection.
fn setup_logging() {
    let _ = tracing_subscriber::registry()
        .with(fmt::layer().with_writer(io::stderr))
        .with(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("hamr_gtk=warn")))
        .try_init();
}

/// Read stdin to EOF and split into non-empty lines.
fn read_stdin_items() -> Vec<String> {
    let mut buf = String::new();
    let _ = io::stdin().read_to_string(&mut buf);
    buf.lines()
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect()
}

/// Print the chosen line and exit successfully.
fn output_and_exit(line: &str) -> ! {
    let mut stdout = io::stdout();
    let _ = writeln!(stdout, "{line}");
    let _ = stdout.flush();
    std::process::exit(0);
}

/// Exit without output (cancelled).
fn cancel() -> ! {
    std::process::exit(1);
}

/// Anchor the dmenu window at the launcher's monitor and position, so it opens
/// in place of the launcher rather than at a fixed spot.
#[allow(
    clippy::cast_possible_truncation,
    clippy::cast_sign_loss,
    clippy::cast_precision_loss
)]
fn position_like_launcher(window: &gtk4::ApplicationWindow, theme: &Theme, width: i32) {
    let state = crate::state::StateManager::new();
    let launcher = state.launcher();
    // Match the launcher's fallback-to-config logic for the position ratios.
    let x_ratio = if (launcher.x_ratio - 0.5).abs() < 0.001 {
        theme.config.appearance.launcher_x_ratio
    } else {
        launcher.x_ratio
    };
    let y_ratio = if (launcher.y_ratio - 0.1).abs() < 0.001 {
        theme.config.appearance.launcher_y_ratio
    } else {
        launcher.y_ratio
    };

    window.set_anchor(Edge::Top, true);
    window.set_anchor(Edge::Left, true);

    let monitor = state
        .last_monitor()
        .and_then(|name| monitor_by_connector(&name))
        .or_else(|| {
            gdk::Display::default()
                .and_then(|d| d.monitors().item(0).and_downcast::<gdk::Monitor>())
        });

    if let Some(monitor) = monitor {
        window.set_monitor(Some(&monitor));
        let geo = monitor.geometry();
        let left = ((x_ratio * f64::from(geo.width())) - (f64::from(width) / 2.0)).floor() as i32;
        let top = (y_ratio * f64::from(geo.height())).floor() as i32;
        window.set_margin(Edge::Left, left.max(0));
        window.set_margin(Edge::Top, top.max(0));
    } else {
        window.set_margin(Edge::Top, 120);
    }
}

/// Find a monitor by its connector name (e.g. "DP-1").
fn monitor_by_connector(name: &str) -> Option<gdk::Monitor> {
    let monitors = gdk::Display::default()?.monitors();
    (0..monitors.n_items())
        .filter_map(|i| monitors.item(i).and_downcast::<gdk::Monitor>())
        .find(|m| m.connector().as_deref() == Some(name))
}

#[allow(clippy::too_many_lines)]
fn build_window(app: &gtk4::Application, items: &[String], prompt: Option<&str>) {
    let theme = Rc::new(Theme::load());

    let css_provider = gtk4::CssProvider::new();
    crate::styles::apply_css(&css_provider, &theme);
    gtk4::style_context_add_provider_for_display(
        &gdk::Display::default().expect("no display"),
        &css_provider,
        gtk4::STYLE_PROVIDER_PRIORITY_USER,
    );

    // Precompute one ResultItem per line (with preview), plus parallel
    // Searchables. The item id is its line index, used to map matches back.
    let result_items: Rc<Vec<ResultItem>> = Rc::new(
        items
            .iter()
            .enumerate()
            .map(|(i, line)| ResultItem {
                id: i.to_string(),
                name: line.clone(),
                preview: build_preview(line),
                ..Default::default()
            })
            .collect(),
    );
    let searchables: Rc<Vec<Searchable>> = Rc::new(
        result_items
            .iter()
            .map(|item| Searchable {
                id: item.id.clone(),
                name: item.name.clone(),
                keywords: Vec::new(),
                source: SearchableSource::Plugin {
                    id: item.id.clone(),
                },
                is_history_term: false,
            })
            .collect(),
    );
    let engine = Rc::new(RefCell::new(SearchEngine::new()));

    let window = gtk4::ApplicationWindow::builder()
        .application(app)
        .title("Hamr dmenu")
        .decorated(false)
        .resizable(false)
        .build();
    window.init_layer_shell();
    window.set_layer(Layer::Overlay);
    window.set_keyboard_mode(KeyboardMode::Exclusive);
    window.set_namespace(Some("hamr-dmenu"));
    window.set_exclusive_zone(-1);

    // Wider than the launcher so the result list still has room beside the
    // preview panel (long file paths otherwise ellipsize to nothing).
    let width = theme.config.sizes.search_width.max(900);

    // Open where the launcher is (same monitor and position).
    position_like_launcher(&window, &theme, width);

    let outer = gtk4::Box::builder()
        .orientation(gtk4::Orientation::Vertical)
        .css_classes(["launcher-container"])
        .build();
    outer.set_size_request(width, -1);

    // Search row: gavel logo + rounded pill entry, mirroring the launcher.
    let search_row = gtk4::Box::builder()
        .orientation(gtk4::Orientation::Horizontal)
        .spacing(8)
        .margin_start(8)
        .margin_end(8)
        .margin_top(8)
        .margin_bottom(6)
        .valign(gtk4::Align::Center)
        .build();

    let icon_container = gtk4::Box::builder()
        .valign(gtk4::Align::Center)
        .halign(gtk4::Align::Center)
        .css_classes(["icon-container"])
        .build();
    let icon = gtk4::Label::builder()
        .label("gavel")
        .css_classes(["material-icon"])
        .build();
    icon_container.append(&icon);
    // Clicking the dmenu's gavel closes it and reopens the regular launcher.
    let icon_gesture = gtk4::GestureClick::new();
    icon_gesture.connect_released(|_, _, _, _| {
        let _ = std::process::Command::new("hamr").arg("show").spawn();
        std::process::exit(1);
    });
    icon_container.add_controller(icon_gesture);
    icon_container.set_cursor(gdk::Cursor::from_name("pointer", None).as_ref());
    search_row.append(&icon_container);

    let search_input_container = gtk4::Box::builder()
        .hexpand(true)
        .valign(gtk4::Align::Center)
        .css_classes(["search-input-container"])
        .build();
    let search_entry = gtk4::Entry::builder()
        .placeholder_text(prompt.unwrap_or("Select..."))
        .hexpand(true)
        .has_frame(false)
        .css_classes(["launcher-search"])
        .build();
    search_input_container.append(&search_entry);
    search_row.append(&search_input_container);
    outer.append(&search_row);

    let body = gtk4::Box::builder()
        .orientation(gtk4::Orientation::Horizontal)
        .spacing(8)
        .margin_start(8)
        .margin_end(8)
        .margin_bottom(8)
        .build();

    let result_list = Rc::new(ResultList::new());
    result_list.set_max_height(500);
    // The ResultList container is created hidden; the launcher reveals it via
    // ResultView, but here we show it ourselves. (An invisible widget reports
    // zero size, which otherwise collapses the row area.)
    result_list.widget().set_visible(true);
    result_list.widget().set_hexpand(true);
    body.append(result_list.widget());

    let preview_panel = Rc::new(PreviewPanel::new());
    preview_panel.set_width(380);
    preview_panel.set_max_height(500);
    // Keep the preview at a fixed width so it doesn't expand and squeeze the
    // result list (its inner content is hexpand=true).
    preview_panel.widget().set_hexpand(false);
    preview_panel.widget().set_halign(gtk4::Align::End);
    preview_panel.widget().set_visible(false);
    body.append(preview_panel.widget());

    outer.append(&body);
    window.set_child(Some(&outer));

    // Render the (filtered) result set for a query.
    let render: Rc<dyn Fn(&str)> = {
        let result_items = result_items.clone();
        let searchables = searchables.clone();
        let engine = engine.clone();
        let theme = theme.clone();
        let result_list = result_list.clone();
        Rc::new(move |query: &str| {
            let results: Vec<ResultItem> = if query.is_empty() {
                result_items.iter().take(MAX_RESULTS).cloned().collect()
            } else {
                engine
                    .borrow_mut()
                    .search(query, &searchables)
                    .into_iter()
                    .filter_map(|m| {
                        let idx: usize = m.searchable.id.parse().ok()?;
                        let mut item = result_items[idx].clone();
                        item.name_markup = m.name_markup;
                        Some(item)
                    })
                    .take(MAX_RESULTS)
                    .collect()
            };
            result_list.set_results(&results, &theme);
        })
    };

    // Keep the preview in sync with the selected row.
    {
        let preview_panel = preview_panel.clone();
        result_list.connect_selection_change(move |selected| {
            update_preview(&preview_panel, selected);
        });
    }

    // Initial population is deferred until after the window is mapped (below):
    // measuring the list height before realization collapses the scrolled
    // window to a single visible row.
    let populate = {
        let render = render.clone();
        let preview_panel = preview_panel.clone();
        let result_list = result_list.clone();
        move || {
            render("");
            update_preview(&preview_panel, result_list.selected_result().as_ref());
        }
    };

    {
        let render = render.clone();
        let preview_panel = preview_panel.clone();
        let result_list = result_list.clone();
        search_entry.connect_changed(move |entry| {
            render(&entry.text());
            update_preview(&preview_panel, result_list.selected_result().as_ref());
        });
    }

    // Clicking a row selects and previews it (without confirming); Enter
    // confirms the selection.
    {
        let preview_panel = preview_panel.clone();
        let result_list_cb = result_list.clone();
        result_list.connect_select(move |_id| {
            update_preview(&preview_panel, result_list_cb.selected_result().as_ref());
        });
    }

    // Keyboard: Up/Down navigate, Enter accepts, Esc cancels. Capture phase so
    // navigation keys are handled before the focused entry consumes them.
    let key_controller = gtk4::EventControllerKey::new();
    key_controller.set_propagation_phase(gtk4::PropagationPhase::Capture);
    {
        let result_list = result_list.clone();
        let search_entry = search_entry.clone();
        key_controller.connect_key_pressed(move |_, key, _, _| {
            use gtk4::gdk::Key;
            match key {
                Key::Escape => cancel(),
                Key::Down | Key::Tab => {
                    result_list.select_next();
                    glib::Propagation::Stop
                }
                Key::Up | Key::ISO_Left_Tab => {
                    result_list.select_prev();
                    glib::Propagation::Stop
                }
                Key::Return | Key::KP_Enter => match result_list.selected_result() {
                    Some(result) => output_and_exit(&result.name),
                    // Nothing selected/matched: return what the user typed.
                    None => output_and_exit(&search_entry.text()),
                },
                _ => glib::Propagation::Proceed,
            }
        });
    }
    window.add_controller(key_controller);

    search_entry.grab_focus();
    window.present();

    // Populate once the window is mapped so the list measures its real height.
    glib::idle_add_local_once(populate);
}

/// Show the preview panel for the selected item, or hide it when the item has
/// no preview.
fn update_preview(panel: &PreviewPanel, selected: Option<&ResultItem>) {
    if let Some((id, preview)) =
        selected.and_then(|item| item.preview.as_ref().map(|p| (item.id.as_str(), p)))
    {
        panel.set_preview(id, preview);
        panel.widget().set_visible(true);
    } else {
        panel.clear();
        panel.widget().set_visible(false);
    }
}

/// Build preview data when `line` is a path to an existing file. Mirrors the
/// behaviour of the `files` plugin's `get_file_preview`: image files preview as
/// images, text files show their (capped) contents, other files show metadata.
pub(crate) fn build_preview(line: &str) -> Option<PreviewData> {
    let path = expand_tilde(line);
    let meta = std::fs::metadata(&path).ok()?;
    if !meta.is_file() {
        return None;
    }

    let title = path.file_name().map_or_else(
        || line.to_string(),
        |n| n.to_string_lossy().into_owned(),
    );
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    let metadata = vec![
        MetadataItem {
            label: "Size".to_string(),
            value: human_size(meta.len()),
            icon: None,
        },
        MetadataItem {
            label: "Path".to_string(),
            value: path.display().to_string(),
            icon: None,
        },
    ];

    if IMAGE_EXTS.contains(&ext.as_str()) {
        return Some(PreviewData {
            title: Some(title),
            image: Some(path.display().to_string()),
            metadata,
            ..Default::default()
        });
    }

    match read_text_capped(&path, MAX_PREVIEW_BYTES) {
        Some(text) if ext == "md" || ext == "markdown" => Some(PreviewData {
            title: Some(title),
            markdown: Some(text),
            metadata,
            ..Default::default()
        }),
        Some(text) => Some(PreviewData {
            title: Some(title),
            content: Some(text),
            metadata,
            ..Default::default()
        }),
        // Binary/unreadable: still show file metadata.
        None => Some(PreviewData {
            title: Some(title),
            metadata,
            ..Default::default()
        }),
    }
}

fn expand_tilde(input: &str) -> PathBuf {
    if let Some(rest) = input.strip_prefix("~/")
        && let Some(home) = std::env::var_os("HOME")
    {
        return Path::new(&home).join(rest);
    }
    PathBuf::from(input)
}

/// Read up to `max` bytes as UTF-8 text, returning `None` for binary content.
fn read_text_capped(path: &Path, max: u64) -> Option<String> {
    let file = std::fs::File::open(path).ok()?;
    let mut buf = Vec::new();
    file.take(max).read_to_end(&mut buf).ok()?;
    if buf.contains(&0) {
        return None; // NUL byte -> treat as binary
    }
    String::from_utf8(buf).ok()
}

#[allow(clippy::cast_precision_loss)]
fn human_size(bytes: u64) -> String {
    const UNITS: &[&str] = &["B", "KB", "MB", "GB", "TB"];
    let mut size = bytes as f64;
    let mut unit = 0;
    while size >= 1024.0 && unit < UNITS.len() - 1 {
        size /= 1024.0;
        unit += 1;
    }
    if unit == 0 {
        format!("{bytes} {}", UNITS[0])
    } else {
        format!("{size:.1} {}", UNITS[unit])
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn non_path_lines_have_no_preview() {
        assert!(build_preview("just some text").is_none());
        assert!(build_preview("not/a/real/path/xyzzy").is_none());
    }

    #[test]
    fn text_file_previews_as_content() {
        let mut file = tempfile::NamedTempFile::new().unwrap();
        write!(file, "hello preview").unwrap();
        let preview = build_preview(file.path().to_str().unwrap()).expect("preview");
        assert_eq!(preview.content.as_deref(), Some("hello preview"));
        assert!(preview.image.is_none());
    }

    #[test]
    fn image_extension_previews_as_image() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("pic.png");
        std::fs::write(&path, [0u8, 1, 2, 3]).unwrap();
        let preview = build_preview(path.to_str().unwrap()).expect("preview");
        assert!(preview.image.is_some());
        assert!(preview.content.is_none());
    }

    #[test]
    fn human_size_formats() {
        assert_eq!(human_size(512), "512 B");
        assert_eq!(human_size(2048), "2.0 KB");
    }
}
