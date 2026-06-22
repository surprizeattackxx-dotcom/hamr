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
    window.set_anchor(Edge::Top, true);
    window.set_anchor(Edge::Left, true);
    window.set_anchor(Edge::Right, true);
    window.set_anchor(Edge::Bottom, true);
    window.set_exclusive_zone(-1);

    let width = theme.config.sizes.search_width;

    let outer = gtk4::Box::builder()
        .orientation(gtk4::Orientation::Vertical)
        .halign(gtk4::Align::Center)
        .valign(gtk4::Align::Start)
        .margin_top(120)
        .css_classes(["launcher-container"])
        .build();
    outer.set_size_request(width, -1);

    let search_entry = gtk4::Entry::builder()
        .placeholder_text(prompt.unwrap_or("Select..."))
        .css_classes(["search-entry"])
        .build();
    outer.append(&search_entry);

    let body = gtk4::Box::builder()
        .orientation(gtk4::Orientation::Horizontal)
        .spacing(8)
        .build();

    let result_list = Rc::new(ResultList::new());
    result_list.set_max_height(500);
    body.append(result_list.widget());

    let preview_panel = Rc::new(PreviewPanel::new());
    preview_panel.set_width(360);
    preview_panel.set_max_height(500);
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
                (*result_items).clone()
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

    // Initial population + preview.
    render("");
    update_preview(&preview_panel, result_list.selected_result().as_ref());

    {
        let render = render.clone();
        let preview_panel = preview_panel.clone();
        let result_list = result_list.clone();
        search_entry.connect_changed(move |entry| {
            render(&entry.text());
            update_preview(&preview_panel, result_list.selected_result().as_ref());
        });
    }

    // Activation by mouse click.
    {
        let result_items = result_items.clone();
        result_list.connect_select(move |id| {
            if let Ok(idx) = id.parse::<usize>() {
                output_and_exit(&result_items[idx].name);
            }
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
