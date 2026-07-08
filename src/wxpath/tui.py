"""TUI for interactive wxpath expression testing.

A two-panel terminal interface:
- Top panel: Editor for wxpath DSL expressions  
- Bottom panel: Live output of executed expressions

Warning:
    Pre-1.0.0 - APIs and contracts may change

Example:
    Launch the TUI from command line::

        $ wxpath-tui

    Or run as a module::

        $ python -m wxpath.tui

"""
import asyncio
import csv
import importlib
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Iterable

from elementpath.xpath_tokens import XPathMap
from lxml.html import HtmlElement, tostring
from rich.console import RenderableType
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    ProgressBar,
    Static,
    Switch,
    TabbedContent,
    TabPane,
    TextArea,
)

from wxpath.core.runtime import ProgressBarInterface, WXPathEngine
from wxpath.hooks import registry
from wxpath.hooks.builtin import SerializeXPathMapAndNodeHook
from wxpath.settings import SETTINGS
from wxpath.tui_settings import (
    TUISettingsSchema,
    load_tui_settings,
    save_tui_settings,
    validate_tui_settings,
)


class SettingsScreen(ModalScreen):
    """Modal screen for editing persistent TUI settings.

    Includes crawler options (CONCURRENCY, PER_HOST, RESPECT_ROBOTS, VERIFY_SSL),
    TUI options (DEBUG_PANEL, CACHE, WSQL), and HTTP headers (JSON).
    Settings are saved to ~/.config/wxpath/tui_settings.json.
    """

    CSS = """
    SettingsScreen {
        align: center middle;
    }

    #settings-dialog {
        width: 70;
        min-height: 22;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #settings-title {
        background: $primary;
        color: $text;
        text-style: bold;
        padding: 0 2;
        dock: top;
    }

    .settings-row {
        height: auto;
        padding: 1 0;
    }

    .settings-label {
        width: 18;
        text-style: bold;
    }

    .settings-input {
        width: 1fr;
    }

    #setting-custom_headers {
        height: 8;
        min-height: 5;
    }

    #settings-help {
        color: $text-muted;
        margin: 1 0;
    }

    #settings-buttons {
        height: auto;
        align: center middle;
        padding: 1 0;
    }

    #settings-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, current: dict[str, Any]):
        super().__init__()
        self.current = dict(current)

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("TUI Settings (persistent)", id="settings-title")
            yield Static(
                "Values are saved to config. Ctrl+S save, Esc cancel. Headers as JSON object.",
                id="settings-help",
            )
            for entry in TUISettingsSchema:
                key = entry["key"]
                label = entry["label"]
                typ = entry["type"]
                value = self.current.get(key, entry["default"])
                if typ == "headers":
                    with Vertical(classes="settings-row"):
                        yield Static(label, classes="settings-label")
                        headers_json = json.dumps(value, indent=2) if value else "{}"
                        yield TextArea(
                            headers_json,
                            language="json",
                            id=f"setting-{key}",
                            classes="settings-input",
                        )
                else:
                    with Horizontal(classes="settings-row"):
                        yield Static(label, classes="settings-label")
                        if typ == "int":
                            inp = Input(
                                str(value),
                                type="integer",
                                id=f"setting-{key}",
                                classes="settings-input",
                            )
                            yield inp
                        elif typ == "str":
                            inp = Input(
                                str(value),
                                id=f"setting-{key}",
                                classes="settings-input",
                            )
                            yield inp
                        else:
                            sw = Switch(
                                value=bool(value),
                                id=f"setting-{key}",
                                classes="settings-input",
                            )
                            yield sw
            with Container(id="settings-buttons"):
                yield Button("Save (Ctrl+S)", variant="primary", id="settings-save-btn")
                yield Button("Cancel (Esc)", variant="default", id="settings-cancel-btn")

    def on_mount(self) -> None:
        first_id = f"setting-{TUISettingsSchema[0]['key']}"
        self.query_one(f"#{first_id}").focus()

    def _gather(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for entry in TUISettingsSchema:
            key = entry["key"]
            typ = entry["type"]
            node = self.query_one(f"#setting-{key}")
            if isinstance(node, Input):
                raw = node.value.strip()
                if typ == "int":
                    result[key] = int(raw) if raw else entry["default"]
                else:
                    result[key] = raw
            elif isinstance(node, TextArea):
                result[key] = node.text
            else:
                result[key] = node.value
        return result

    def _validate(self, data: dict[str, Any]) -> str | None:
        errors = validate_tui_settings(data)
        return errors[0] if errors else None

    def _coerce_custom_headers(self, data: dict[str, Any]) -> None:
        """Coerce custom_headers from TextArea string to dict for save and dismiss."""
        ch = data.get("custom_headers")
        if isinstance(ch, str):
            data["custom_headers"] = (
                json.loads(ch) if ch.strip() else {}
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-save-btn":
            data = self._gather()
            err = self._validate(data)
            if err:
                self.notify(err, severity="error")
                return
            self._coerce_custom_headers(data)
            save_tui_settings(data)
            self.dismiss(data)
        elif event.button.id == "settings-cancel-btn":
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "ctrl+s":
            data = self._gather()
            err = self._validate(data)
            if err:
                self.notify(err, severity="error")
                return
            self._coerce_custom_headers(data)
            save_tui_settings(data)
            self.dismiss(data)
            event.prevent_default()
        elif event.key == "escape":
            self.dismiss(None)
            event.prevent_default()


class ExportScreen(ModalScreen):
    """Modal screen for choosing export format (CSV or JSON).

    Exports the current output data table to a file in the current
    working directory with a timestamped default filename.
    """

    CSS = """
    ExportScreen {
        align: center middle;
    }

    #export-dialog {
        width: 50;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #export-title {
        background: $primary;
        color: $text;
        text-style: bold;
        padding: 0 2;
        dock: top;
    }

    #export-buttons {
        height: auto;
        align: center middle;
        padding: 1 0;
    }

    #export-buttons Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Build the export dialog layout."""
        with Vertical(id="export-dialog"):
            yield Static("Export table data", id="export-title")
            yield Static(
                "Choose format. File is saved in the current directory.",
                id="export-help",
            )
            with Container(id="export-buttons"):
                yield Button("Export CSV", variant="primary", id="export-csv-btn")
                yield Button("Export JSON", variant="primary", id="export-json-btn")
                yield Button("Cancel (Esc)", variant="default", id="export-cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle export or cancel."""
        if event.button.id == "export-cancel-btn":
            self.dismiss(None)
        elif event.button.id == "export-csv-btn":
            self.dismiss("csv")
        elif event.button.id == "export-json-btn":
            self.dismiss("json")

    def on_key(self, event) -> None:
        """Escape cancels."""
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()


class OutputPanel(Vertical, can_focus=True):
    """Display panel for expression results.
    
    A reactive Static widget that displays formatted output from wxpath
    expression execution. Supports multiple output formats including plain
    text, HTML elements, and table views.
    
    Attributes:
        output_text: Reactive string that triggers display updates
    """
    
    # output_text: reactive[str] = reactive("Waiting for expression...")
    
    def __init__(self, *args, **kwargs):
        """Initialize the output panel.
        
        Args:
            *args: Positional arguments passed to Static
            **kwargs: Keyword arguments passed to Static
        """
        super().__init__(*args, **kwargs)
        self.border_title = "Output"
    
    def clear(self) -> None:
        self.remove_children()

    def append(self, renderable) -> None:
        self.mount(Static(renderable))
        # self.scroll_end(animate=False)

    # def watch_output_text(self, new_text: str) -> None:
    #     """Update display when output changes.
        
    #     Args:
    #         new_text: New text content to display
    #     """
    #     self.update(new_text)


class DebugPanel(VerticalScroll, can_focus=False):
    """Scrollable panel for debug messages.
    
    A simple vertical scroll region that collects timestamped debug
    messages. Intended for lightweight, append-only logging during
    interactive sessions.
    """
    
    def __init__(self, *args, **kwargs):
        """Initialize the debug panel."""
        super().__init__(*args, **kwargs)
        # self.border_title = "Debug"
    
    def clear(self) -> None:
        """Clear all debug messages."""
        self.remove_children()
    
    def append(self, message: str) -> None:
        """Append a new debug message and scroll to bottom.
        
        Args:
            message: Message text to append
        """
        # Keep debug output simple Rich-markup strings.
        self.mount(Static(message, classes="debug-line"))
        self.scroll_end(animate=False)


class TextualProgressAdapter:
    """ProgressBarInterface adapter that drives a Textual ProgressBar widget.

    Used when the engine runs from the TUI so the bar reflects crawl progress
    (responses completed, total = URLs enqueued) instead of result count.
    """

    def __init__(
        self,
        get_widget: Any,
        *,
        initial_total: int = 0,
    ) -> None:
        """Initialize the adapter.

        Args:
            get_widget: Callable that returns the Textual ProgressBar widget
                (e.g. lambda: self._progress_bar()).
            initial_total: Initial total (engine expects 0 and does pbar.total += 1).
        """
        self._get_widget = get_widget
        self._progress = 0
        self._total = initial_total

    @property
    def total(self) -> int:
        return self._total

    @total.setter
    def total(self, value: int) -> None:
        self._total = value
        self._refresh_widget()

    def update(self, n: int = 1) -> None:
        self._progress += n
        self._refresh_widget()

    def refresh(self) -> None:
        self._refresh_widget()

    def set_postfix(self, **kwargs: Any) -> None:
        # Optional: Textual ProgressBar has no postfix; no-op.
        pass

    def close(self) -> None:
        # Show complete: progress = total (or 1 if total is 0 to avoid indeterminate)
        total = self._total if self._total > 0 else 1
        self._progress = total
        self._refresh_widget()

    def _refresh_widget(self) -> None:
        try:
            widget = self._get_widget()
            total = self._total if self._total > 0 else None
            widget.update(progress=self._progress, total=total)
        except Exception:
            pass


class PanelDivider(Static):
    """Draggable divider between editor and output panels."""

    class DragStart(Message):
        """Message emitted when divider dragging starts."""

        def __init__(self, sender: "PanelDivider", screen_x: int, screen_y: int) -> None:
            super().__init__()
            self.sender = sender
            self.screen_x = screen_x
            self.screen_y = screen_y

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Begin divider drag interaction."""
        self.post_message(self.DragStart(self, event.screen_x, event.screen_y))
        event.stop()


class WXPathTUI(App):
    """Interactive TUI for wxpath expression testing.
    
    Top panel: Expression editor
    Bottom panel: Live output display
    """
    
    TITLE = "wxpath TUI - Interactive Expression Testing"
    # SUB_TITLE will be set dynamically based on cache state
    
    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
        overflow: hidden;
    }

    #main-panels {
        layout: vertical;
        height: 1fr;
        width: 1fr;
    }
    
    #editor-container {
        height: 1fr;
        width: 1fr;
        border: heavy $primary;
        background: $panel;
    }

    #editor-header,
    #output-header {
        height: auto;
        background: $primary;
        color: $text;
        padding: 0 1;
        dock: top;
    }

    .panel-header-title {
        width: auto;
        text-style: bold;
        padding: 0 1;
    }

    .panel-header-spacer {
        width: 1fr;
    }

    .panel-max-button {
        min-width: 10;
        height: 1;
        min-height: 1;
        max-height: 1;
        padding: 0 1;
        margin: 0;
        border: none;
    }

    #editor-tabs {
        height: 1fr;
    }

    #editor-tabs TabPane {
        height: 1fr;
        padding: 0;
    }
    
    #output-container {
        height: 1fr;
        width: 1fr;
        border: heavy $accent;
        background: $panel;
    }

    #panel-divider {
        height: 1;
        width: 100%;
        background: $surface-darken-1;
        color: $text-muted;
        content-align: center middle;
    }
    
    #output-panel {
        height: 3fr;
    }

    #output-panel DataTable {
        height: 1fr;
        width: 100%;
    }
    
    #debug-container {
        layout: vertical;
        height: 1fr;
        min-height: 5;
        border-top: tall $accent-darken-1;
        background: $surface-darken-1;
    }
    
    #debug-header {
        background: $accent-darken-1;
        color: $text;
        text-style: bold;
        padding: 0 2;
        dock: top;
    }
    
    #debug-panel {
        height: 1fr;
        min-height: 3;
        padding: 0 2;
        overflow-y: auto;
        background: $surface-darken-1;
    }
    
    #progress-bar-container {
        height: auto;
        min-height: 0;
        /* padding: 0 2 1 2; */
        dock: bottom;
        width: 100%;
    }
    
    #progress-bar-container ProgressBar {
        width: 100%;
    }
    
    TextArea {
        height: 1fr;
        width: 100%;
        background: $surface;
    }
    
    OutputPanel {
        height: 100%;
        padding: 1 2;
        overflow-y: auto;
        background: $surface;
    }
    
    DebugPanel {
        height: 100%;
        padding: 1 0;
        overflow-y: auto;
        background: $surface;
    }
    
    .panel-header {
        background: $primary;
        color: $text;
        text-style: bold;
        padding: 0 2;
        dock: top;
    }
    
    Header {
        background: $primary-darken-2;
    }
    
    Footer {
        background: $primary-darken-2;
    }
    """
    
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+r", "execute", "Execute"),
        ("escape", "cancel_crawl", "Cancel/Dismiss"),
        ("ctrl+c", "clear", "Clear"),
        ("ctrl+shift+backspace", "clear_editor", "Clear Editor"),
        ("ctrl+d", "clear_debug", "Clear Debug"),
        ("ctrl+shift+d", "toggle_debug", "Toggle Debug"),
        # ("ctrl+p", "toggle_progress", "Progress bar"),
        ("ctrl+e", "export", "Export"),
        ("ctrl+l", "toggle_cache", "Cache"),
        ("ctrl+shift+s", "edit_settings", "Settings"),
        ("ctrl+shift+c", "copy_expression", "Copy Expression"),
        ("f5", "execute", "Execute"),
    ]

    cache_enabled = reactive(False)
    debug_panel_visible = reactive(False)
    progress_bar_enabled = reactive(True)
    custom_headers = reactive({})
    tui_settings = reactive({})
    wsql_enabled = reactive(False)
    wsql_install_path = reactive("")
    _max_table_cell_chars = 400
    panel_view_mode = reactive("split")
    editor_panel_percent = reactive(40)
    panels_side_by_side = reactive(False)
    
    def __init__(self):
        """Initialize the TUI application.
        
        Sets up the wxpath engine with XPathMap serialization hook for
        clean dict output in table views.
        """
        super().__init__()
        # Register serialization hook to convert XPathMap to dicts
        registry.register(SerializeXPathMapAndNodeHook)
        # self.engine = WXPathEngine()
        self._executing = False
        self._crawl_worker = None  # Worker for current crawl; used for cancellation
        self._last_sort_column: str | None = None
        self._last_sort_reverse = False
        # Skip first TextArea.Changed from initial editor content
        self._skip_next_live_execution = True
        self._wsql_path_added = False
        self._dragging_divider = False

    def _progress_bar_container(self) -> Container:
        """Return the progress bar container (for show/hide during execution)."""
        return self.query_one("#progress-bar-container", Container)

    def _progress_bar(self) -> ProgressBar:
        """Return the ProgressBar widget."""
        return self.query_one("#progress-bar", ProgressBar)

    def _editor_container(self) -> Container:
        """Return the editor panel container."""
        return self.query_one("#editor-container", Container)

    def _output_container(self) -> Container:
        """Return the output panel container."""
        return self.query_one("#output-container", Container)

    def _panel_divider(self) -> PanelDivider:
        """Return the draggable divider widget."""
        return self.query_one("#panel-divider", PanelDivider)

    def _main_panels(self) -> Container:
        """Return the main panels container."""
        return self.query_one("#main-panels", Container)

    def _editor_tabs(self) -> TabbedContent:
        """Return the editor tab container."""
        return self.query_one("#editor-tabs", TabbedContent)

    def _active_editor_mode(self) -> str:
        """Return active editor mode: ``wxpath`` or ``wsql``."""
        return "wsql" if self._editor_tabs().active == "wsql-tab" else "wxpath"

    def _active_editor(self) -> TextArea:
        """Return the currently active editor widget."""
        editor_id = "#wsql-editor" if self._active_editor_mode() == "wsql" else "#expression-editor"
        return self.query_one(editor_id, TextArea)
    
    def compose(self) -> ComposeResult:
        """Build the application layout."""
        yield Header()
        with Container(id="main-panels"):
            with Container(id="editor-container"):
                with Horizontal(id="editor-header"):
                    yield Static("Editor (Ctrl+R to execute active tab)", classes="panel-header-title") # noqa: E501
                    yield Static("", classes="panel-header-spacer")
                    yield Button("Max.", id="maximize-editor-btn", classes="panel-max-button")
                with TabbedContent(id="editor-tabs", initial="wxpath-tab"):
                    with TabPane("WXPath", id="wxpath-tab"):
                        yield TextArea(id="expression-editor", language="python")
                    with TabPane("WSQL", id="wsql-tab"):
                        yield TextArea(id="wsql-editor", language="sql")

            yield PanelDivider("drag to resize", id="panel-divider")
            
            with Container(id="output-container"):
                with Horizontal(id="output-header"):
                    yield Static("Output", classes="panel-header-title")
                    yield Static("", classes="panel-header-spacer")
                    yield Button("Max.", id="maximize-output-btn", classes="panel-max-button")
                yield OutputPanel(id="output-panel")
                with Container(id="progress-bar-container"):
                    yield ProgressBar(id="progress-bar", show_eta=True)
                # with OutputPanel(id="output-panel"):

                # yield Button("Export (Ctrl+E)", id="export_button")
            
                with Container(id="debug-container"):
                    yield Static("Debug", id="debug-header", classes="panel-header")
                    yield DebugPanel(id="debug-panel")
            
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize with a sample expression."""
        # Load all TUI settings from config (crawler, debug panel, cache, headers)
        self.tui_settings = load_tui_settings()
        self.debug_panel_visible = bool(
            self.tui_settings.get("debug_panel_enabled", False)
        )
        self.cache_enabled = bool(self.tui_settings.get("cache_enabled", True))
        SETTINGS.http.client.cache.enabled = self.cache_enabled
        self.custom_headers = dict(
            self.tui_settings.get("custom_headers") or {}
        )
        self.wsql_enabled = bool(self.tui_settings.get("wsql_enabled", False))
        self.wsql_install_path = str(self.tui_settings.get("wsql_install_path", "")).strip()
        self.panels_side_by_side = bool(
            self.tui_settings.get("panels_side_by_side", False)
        )
        
        editor = self.query_one("#expression-editor", TextArea)
        wsql_editor = self.query_one("#wsql-editor", TextArea)
        # Start with a simple example
        editor.text = (
            "url('https://quotes.toscrape.com', depth=5, follow=//li[@class='next']/a/@href)\n"
            "  //url(//a[contains(@href, '/author/')]/@href)\n"
            "    /map {\n"
            "      'url': string(base-uri(.)),\n"
            "      'name': //h3[@class='author-title']/text(),\n"
            "      'born': //span[@class='author-born-date']/text(),\n"
            "      'bio': //div[@class='author-description']/text() ! normalize-space(.) ! string(.)\n" # noqa: E501
            "    }\n"
        )
        wsql_editor.text = (
            "SELECT\n"
            "    string(base-uri(.)) AS url,\n"
            "    ./span[@class='text']/text() AS quote,\n"
            "    .//small[@class='author']/text() AS author\n"
            "FROM https://quotes.toscrape.com\n"
            "    PER //div[@class='row']//div[@class='quote']\n"
            "    FOLLOW //li[@class='next']/a/@href\n"
            "    DEPTH 5\n"
        )
        editor.focus()
        self._apply_orientation_layout()
        self._apply_split_layout()
        self._update_panel_button_labels()
        
        # Progress bar container hidden until execution starts (and progress bar enabled)
        self._progress_bar_container().display = False

        # Show initial help text
        self._update_output(
            "[dim]Welcome to wxpath TUI![/dim]\n\n"
            "[cyan]Quick Start:[/cyan]\n"
            "  • Edit the expression above\n"
            "  • Press [bold]Ctrl+R[/bold] or [bold]F5[/bold] to execute\n"
            "  • Press [bold]Escape[/bold] to cancel a running crawl\n"
            "  • Press [bold]Ctrl+E[/bold] to export table (CSV/JSON)\n"
            "  • Press [bold]Ctrl+C[/bold] to clear output\n"
            "  • Press [bold]Ctrl+Shift+Backspace[/bold] to clear expression editor\n"
            "  • Press [bold]Ctrl+Shift+D[/bold] to toggle debug panel\n"
            "  • Press [bold]Ctrl+P[/bold] to toggle progress bar (on by default)\n"
            "  • Press [bold]Ctrl+Shift+S[/bold] to edit settings (crawler, cache, headers)\n"
            "  • Press [bold]Ctrl+L[/bold] to toggle HTTP caching\n"
            "  • Use [bold]WXPath / WSQL[/bold] tabs to switch editor modes\n"
            "  • Use [bold]arrow keys[/bold] or [bold]scroll[/bold] to view results\n\n"
            "[cyan]Example expressions:[/cyan]\n"
            "  • Extract text: url('...')//div//text()\n"
            "  • Extract as dict/table: url('...')//div/map { 'title': .//h1/text() }\n"
            "  • Follow links: url('...') ///url(//a/@href) //div/text()\n\n"
            "[green]Expression appears valid - Press Ctrl+R or F5 to execute[/green]"
        )

    def watch_cache_enabled(self, new_value: bool) -> None:
        """Update global settings, persist to config, and update subtitle."""
        SETTINGS.http.client.cache.enabled = bool(new_value)
        self.tui_settings = {**self.tui_settings, "cache_enabled": new_value}
        save_tui_settings(self.tui_settings)
        self._debug(f"Cache enabled: {SETTINGS.http.client.cache.enabled}")
        self._update_subtitle()

    def watch_editor_panel_percent(self, new_value: int) -> None:
        """Apply split height updates while in split mode."""
        if self.panel_view_mode == "split":
            self._apply_split_layout()

    def watch_panels_side_by_side(self, new_value: bool) -> None:
        """Apply panel orientation changes."""
        self._apply_orientation_layout()
        if self.panel_view_mode == "split":
            self._apply_split_layout()

    def watch_panel_view_mode(self, new_value: str) -> None:
        """Switch between split/editor-max/output-max panel modes."""
        editor = self._editor_container()
        output = self._output_container()
        divider = self._panel_divider()
        if new_value == "editor-max":
            editor.display = True
            editor.styles.height = "1fr"
            output.display = False
            divider.display = False
        elif new_value == "output-max":
            editor.display = False
            output.display = True
            output.styles.height = "1fr"
            divider.display = False
        else:
            editor.display = True
            output.display = True
            divider.display = True
            self._apply_split_layout()
        self._update_panel_button_labels()
        self.refresh(layout=True)

    def _clamp_split_percent(self, percent: int) -> int:
        """Clamp editor panel split percent into safe bounds."""
        return max(20, min(80, int(percent)))

    def _apply_split_layout(self) -> None:
        """Apply current editor/output split percentages."""
        editor_percent = self._clamp_split_percent(self.editor_panel_percent)
        output_percent = 100 - editor_percent
        if self.panels_side_by_side:
            self._editor_container().styles.height = "1fr"
            self._output_container().styles.height = "1fr"
            self._editor_container().styles.width = f"{editor_percent}fr"
            self._output_container().styles.width = f"{output_percent}fr"
        else:
            # Use fr units so split fits available viewport space
            # (header/footer/divider included) without causing screen overflow.
            self._editor_container().styles.height = f"{editor_percent}fr"
            self._output_container().styles.height = f"{output_percent}fr"
            self._editor_container().styles.width = "1fr"
            self._output_container().styles.width = "1fr"

    def _apply_orientation_layout(self) -> None:
        """Apply stacked vs side-by-side orientation styles."""
        panels = self._main_panels()
        divider = self._panel_divider()
        if self.panels_side_by_side:
            panels.styles.layout = "horizontal"
            divider.styles.width = 1
            divider.styles.height = "100%"
            divider.update("drag")
        else:
            panels.styles.layout = "vertical"
            divider.styles.height = 1
            divider.styles.width = "100%"
            divider.update("drag to resize")

    def _update_panel_button_labels(self) -> None:
        """Update maximize/restore button labels for current panel mode."""
        editor_btn = self.query_one("#maximize-editor-btn", Button)
        output_btn = self.query_one("#maximize-output-btn", Button)
        editor_btn.label = (
            "Min." if self.panel_view_mode == "editor-max" else "Max."
        )
        output_btn.label = (
            "Min." if self.panel_view_mode == "output-max" else "Max."
        )

    def _set_split_from_screen_position(self, screen_x: int, screen_y: int) -> None:
        """Convert absolute mouse position to panel split percent."""
        editor = self._editor_container()
        output = self._output_container()
        if self.panels_side_by_side:
            left = editor.region.x
            right = output.region.x + output.region.width
            total = max(1, right - left)
            relative = max(1, min(total - 1, screen_x - left))
        else:
            top = editor.region.y
            bottom = output.region.y + output.region.height
            total = max(1, bottom - top)
            relative = max(1, min(total - 1, screen_y - top))
        percent = int((relative / total) * 100)
        self.editor_panel_percent = self._clamp_split_percent(percent)
    
    def watch_custom_headers(self, new_value: dict) -> None:
        """Update subtitle when custom headers change."""
        self._update_subtitle()

    def watch_tui_settings(self, new_value: dict) -> None:
        """Update subtitle when persistent settings change."""
        self._update_subtitle()
    
    def _update_subtitle(self) -> None:
        """Update subtitle with current cache, headers, and persistent settings."""
        # cache_state = "ON" if self.cache_enabled else "OFF"
        cache_state = SETTINGS.http.client.cache.enabled
        headers_count = len(self.custom_headers)
        headers_info = f"{headers_count} custom" if headers_count > 0 else "default"
        wsql_state = "ON" if self.wsql_enabled else "OFF"
        layout_state = "SIDE" if self.panels_side_by_side else "STACKED"
        conc = self.tui_settings.get("concurrency", 16)
        ph = self.tui_settings.get("per_host", 8)
        robots = "ON" if self.tui_settings.get("respect_robots", True) else "OFF"
        self.sub_title = (
            f"Cache: {cache_state} | Headers: {headers_info} | "
            f"Concurrency: {conc} | Per host: {ph} | Robots: {robots} | WSQL: {wsql_state} | Layout: {layout_state} | " # noqa: E501
            f"Ctrl+R: Run | Ctrl+Shift+S: Settings | Ctrl+Q: Quit"
        )

    def action_copy_expression(self) -> None:
        """Copy the expression to the clipboard."""
        expression = self._active_editor().text
        self.copy_to_clipboard(expression)
        self._debug(f"Expression copied to clipboard: {expression}")

    async def action_toggle_cache(self) -> None:
        """Toggle HTTP caching on/off for new requests."""
        old_state = self.cache_enabled
        self.cache_enabled = not self.cache_enabled
        new_state = self.cache_enabled
        
        old_label = "ON" if old_state else "OFF"
        new_label = "ON" if new_state else "OFF"
        
        self._update_output(
            f"[cyan]HTTP caching toggled: {old_label} → {new_label}[/cyan]\n\n"
            "[dim]This setting will apply to the next expression execution.[/dim]"
        )
        self._debug(f"Toggled cache from {old_label} to {new_label}")
    
    def action_edit_settings(self) -> None:
        """Open the settings modal (crawler, debug panel, cache, headers)."""
        def handle_settings_result(result: dict[str, Any] | None) -> None:
            if result is not None:
                self.tui_settings = result
                self.debug_panel_visible = bool(
                    result.get("debug_panel_enabled", False)
                )
                self.cache_enabled = bool(result.get("cache_enabled", True))
                SETTINGS.http.client.cache.enabled = self.cache_enabled
                ch = result.get("custom_headers") or {}
                if isinstance(ch, str):
                    try:
                        ch = json.loads(ch) if ch.strip() else {}
                    except json.JSONDecodeError:
                        ch = {}
                self.custom_headers = dict(ch) if isinstance(ch, dict) else {}
                self.wsql_enabled = bool(result.get("wsql_enabled", False))
                self.wsql_install_path = str(result.get("wsql_install_path", "")).strip()
                self.panels_side_by_side = bool(
                    result.get("panels_side_by_side", False)
                )
                self._update_output(
                    "[cyan]Settings saved[/cyan]\n\n"
                    f"CONCURRENCY: {result.get('concurrency', 16)} | "
                    f"PER_HOST: {result.get('per_host', 8)} | "
                    f"RESPECT_ROBOTS: {result.get('respect_robots', True)} | "
                    f"DEBUG: {result.get('debug_panel_enabled', False)} | "
                    f"CACHE: {result.get('cache_enabled', True)} | "
                    f"HEADERS: {len(self.custom_headers)} custom | "
                    f"WSQL: {self.wsql_enabled} | "
                    f"WSQL_PATH: {self.wsql_install_path or '(auto)'} | "
                    f"SIDE_BY_SIDE: {self.panels_side_by_side}\n\n"
                    "[dim]Apply to the next run.[/dim]"
                )
                self._debug("Settings saved and applied")

        self.push_screen(SettingsScreen(dict(self.tui_settings)), handle_settings_result)
        self._debug("Opened settings screen")

    def _get_output_data_table(self) -> DataTable | None:
        """Return the first DataTable in the output panel, or None if none.

        Returns:
            The output DataTable when the last run produced a table; None otherwise.
        """
        panel = self.query_one("#output-panel", OutputPanel)
        tables = panel.query(DataTable)
        return tables.first() if tables else None

    def _export_table_csv(self, data_table: DataTable, path: Path) -> None:
        """Write table data to a CSV file.

        Args:
            data_table: The DataTable to export.
            path: Output file path.
        """
        columns = data_table.ordered_columns
        if not columns:
            return
        headers = [str(c.label) for c in columns]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row_meta in data_table.ordered_rows:
                row_key = row_meta.key
                cells = data_table.get_row(row_key)
                writer.writerow([str(c) for c in cells])

    def _export_table_json(self, data_table: DataTable, path: Path) -> None:
        """Write table data to a JSON file (list of row objects).

        Args:
            data_table: The DataTable to export.
            path: Output file path.
        """
        columns = data_table.ordered_columns
        if not columns:
            return
        keys = [str(c.label) for c in columns]
        rows = []
        for row_meta in data_table.ordered_rows:
            cells = data_table.get_row(row_meta.key)
            rows.append(dict(zip(keys, [str(c) for c in cells], strict=True)))
        with path.open("w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)

    def action_export(self) -> None:
        """Open export dialog to save table as CSV or JSON."""
        def handle_export_result(fmt: str | None) -> None:
            if fmt is None:
                self._debug("Export cancelled")
                return
            table = self._get_output_data_table()
            if table is None:
                self.notify(
                    "No table to export. Run an expression that produces a table first.",
                    severity="warning",
                )
                self._debug("Export attempted but output panel has no DataTable")
                return
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            ext = ".csv" if fmt == "csv" else ".json"
            path = Path.cwd() / f"wxpath_export_{stamp}{ext}"
            try:
                if fmt == "csv":
                    self._export_table_csv(table, path)
                else:
                    self._export_table_json(table, path)
                self.notify(f"Exported to {path}", severity="information")
                self._debug(f"Exported table to {path} ({fmt.upper()}, {table.row_count} rows)")
            except OSError as e:
                self.notify(f"Export failed: {e}", severity="error")
                self._debug(f"Export failed: {e}")

        self.push_screen(ExportScreen(), handle_export_result)
        self._debug("Opened export dialog")

    def _numeric_sort_key(self, value: Any) -> tuple[int, float | str]:
        """Key for sorting: numbers by value, then non-numeric by string.
        
        Used so numeric columns sort numerically (e.g. 2 < 10) instead of
        lexicographically (e.g. "10" < "2"). Single cell value is passed
        when sorting by one column.
        """
        s = "" if value is None else str(value).strip()
        if not s:
            return (1, "")
        try:
            return (0, float(s))
        except (ValueError, TypeError):
            return (1, str(value))

    def _is_numeric_column(self, table: DataTable, column_key: Any) -> bool:
        """Return True if column appears to be numeric (majority of non-empty parse as float)."""
        numeric = 0
        non_empty = 0
        for cell in table.get_column(column_key):
            if non_empty >= 10:
                break
            s = "" if cell is None else str(cell).strip()
            if not s:
                continue
            non_empty += 1
            try:
                float(s)
                numeric += 1
            except (ValueError, TypeError):
                pass
        return numeric > 0 and numeric >= (non_empty / 2)

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Handle column header click: sort by that column (toggle asc/desc on repeat click)."""
        table = event.data_table
        column_key = event.column_key
        key_str = str(column_key)
        if self._last_sort_column == key_str:
            self._last_sort_reverse = not self._last_sort_reverse
        else:
            self._last_sort_column = key_str
            self._last_sort_reverse = False
        if self._is_numeric_column(table, column_key):
            table.sort(column_key, key=self._numeric_sort_key, reverse=self._last_sort_reverse)
            direction = "desc" if self._last_sort_reverse else "asc"
            self._debug(f"Sorted by column {key_str!r} numerically ({direction})")
        else:
            table.sort(column_key, reverse=self._last_sort_reverse)
            direction = "desc" if self._last_sort_reverse else "asc"
            self._debug(f"Sorted by column {key_str!r} ({direction})")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses (e.g. Export)."""
        if event.button.id == "export_button":
            self.action_export()
        elif event.button.id == "maximize-editor-btn":
            self.panel_view_mode = (
                "split" if self.panel_view_mode == "editor-max" else "editor-max"
            )
        elif event.button.id == "maximize-output-btn":
            self.panel_view_mode = (
                "split" if self.panel_view_mode == "output-max" else "output-max"
            )

    @on(PanelDivider.DragStart)
    def _on_panel_divider_drag_start(self, event: PanelDivider.DragStart) -> None:
        """Start drag-to-resize interaction from divider."""
        self._dragging_divider = True
        if self.panel_view_mode != "split":
            self.panel_view_mode = "split"
        self._set_split_from_screen_position(event.screen_x, event.screen_y)

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Resize split continuously while divider is being dragged."""
        if not self._dragging_divider:
            return
        self._set_split_from_screen_position(event.screen_x, event.screen_y)

    def on_mouse_up(self, _event: events.MouseUp) -> None:
        """Stop drag-to-resize interaction."""
        self._dragging_divider = False
    
    @work(exclusive=True)
    @on(TextArea.Changed)
    async def live_expression_execution(self, event: TextArea.Changed) -> None:
        """Execute expression as user types. Will produce results if the expression is valid."""
        if event.text_area.id not in {"expression-editor", "wsql-editor"}:
            return
        if self._skip_next_live_execution:
            self._skip_next_live_execution = False
            return
        self._debug("Text area changed")
        self._debug("Live expression execution started")
        await self.action_execute()

    def _prep_row(self, result: XPathMap | dict, keys: list[str]) -> list[str]:
        """Prepare a row for table display from a dict-like result.
        
        Args:
            result: Dictionary or XPathMap to extract values from
            keys: Ordered list of column keys to extract
            
        Returns:
            List of string values in the same order as keys
        """
        row = []
        # Handle both dict and XPathMap for backward compatibility
        d = result if isinstance(result, dict) else dict(result.items())
        for key in keys:  # Use provided order, not sorted
            value = d.get(key, "")
            if isinstance(value, Iterable) and not isinstance(value, str):
                # Limit iterables (except strings) to first 10 items for display
                if isinstance(value, list):
                    value = value[:10]
                elif isinstance(value, set):
                    value = list(value)[:10]
                else:
                    value = list(value)[:10]
            # Convert to string for table display
            text_value = "" if value is None else str(value)
            if len(text_value) > self._max_table_cell_chars:
                text_value = text_value[: self._max_table_cell_chars] + "..."
            row.append(text_value)
        return row

    @work(exclusive=True)
    async def collect_results(self, expression: Any, mode: str = "wxpath") -> None:
        """Collect results from the expression."""
        count = 0
        show_progress = self.progress_bar_enabled
        try:
            # Wrap the async iteration with timeout (60s for larger result sets)

            # Import here to avoid circular imports
            from wxpath.http.client.crawler import Crawler

            conc = self.tui_settings.get("concurrency", 16)
            ph = self.tui_settings.get("per_host", 8)
            robots = self.tui_settings.get("respect_robots", True)
            verify_ssl = self.tui_settings.get("verify_ssl", True)
            crawler = Crawler(
                concurrency=conc,
                per_host=ph,
                respect_robots=robots,
                verify_ssl=verify_ssl,
                headers=dict(self.custom_headers) if self.custom_headers else None,
            )
            engine = WXPathEngine(crawler=crawler, yield_errors=True)
            
            # Streaming approach
            panel = self.query_one("#output-panel", OutputPanel)
            panel.clear()

            # Create progress adapter if enabled (engine will drive the bar)
            progress_adapter: ProgressBarInterface | None = None
            if show_progress and mode != "wsql":
                self._progress_bar_container().display = True
                self._progress_bar().update(progress=0, total=None)
                progress_adapter = TextualProgressAdapter(
                    lambda: self._progress_bar(),
                    initial_total=0,
                )
                self._debug("Progress bar shown (engine-driven)")

            # data_table = None
            data_table = DataTable(show_header=True, zebra_stripes=True)
            data_table.styles.height = "1fr"
            data_table.styles.width = "100%"
            panel.mount(data_table)
            columns_initialized = False
            column_keys: list[str] = []

            result_stream: AsyncGenerator[Any, None]
            if mode == "wsql":
                if show_progress:
                    self._debug(
                        "WSQLExecutor drives execution DAG; TUI progress bar is disabled for WSQL mode." # noqa: E501
                    )
                executor = self._create_wsql_executor(
                    concurrency=conc,
                    per_host=ph,
                    respect_robots=robots,
                    verify_ssl=verify_ssl,
                    headers=dict(self.custom_headers) if self.custom_headers else None,
                )
                result_stream = executor.execute(
                    expression,
                    progress=False,
                    yield_errors=True,
                )
            else:
                result_stream = engine.run(
                    expression,
                    max_depth=1,
                    progress=progress_adapter if progress_adapter is not None else False,
                )

            async for result in result_stream:
                if isinstance(result, dict) and result.get("__type__") == "error":
                    self._debug(f"Error: {result.get('reason')}: {result}")
                    continue
                count += 1
                if count % 100 == 0:
                    self._debug(f"Received result {count} of type {type(result).__name__}")

                if result.__class__.__name__ == "DataIntentWithProjection":
                    result = result.value

                if isinstance(result, XPathMap):
                    # result = dict(result.items())
                    result = result._map

                

                if not columns_initialized:
                    self._debug("Initializing table columns")
                    if isinstance(result, dict):
                        column_keys = list(result.keys())
                        for key in column_keys:
                            data_table.add_column(str(key), key=key)
                        columns_initialized = True
                    else:
                        data_table.add_column("value", key="value")
                        column_keys = ["value"]
                        columns_initialized = True
                    self._debug(f"Initializing table columns: {column_keys}")

                # Format row using existing logic
                if isinstance(result, dict):
                    row = self._prep_row(result, column_keys)
                else:
                    row = [result]
                # Add row with unique key for efficient updates
                data_table.add_row(*row, key=str(count))

        except asyncio.CancelledError:
            # Keep partial results; append status without clearing the panel
            panel = self.query_one("#output-panel", OutputPanel)
            if count > 0:
                panel.append(f"[yellow]Crawl cancelled - {count} partial result(s) shown.[/yellow]")
            else:
                panel.append("[yellow]Crawl cancelled. Run the expression again to continue.[/yellow]") # noqa: E501
            self._debug("Crawl cancelled by user.")
            raise
        except asyncio.TimeoutError:
            if count > 0:
                pass
            else:
                self._update_output(
                    "[yellow]Timeout after 60s - no results returned[/yellow]\n"
                    "The site may be slow or unresponsive."
                )
            self._executing = False
            return
        except Exception as e:
            # Log full stack trace to debug panel
            self._debug(traceback.format_exc())
            # Append error as next row of table (do not clear output panel)
            err_msg = f"Execution Error: {type(e).__name__}: {e}"
            if columns_initialized and column_keys:
                row = [err_msg] + [""] * (len(column_keys) - 1)
                data_table.add_row(*row, key=f"error-{count}")
            else:
                data_table.add_column("error", key="error")
                data_table.add_row(err_msg, key="error-0")
            self._executing = False
            return
        finally:
            if show_progress:
                self._progress_bar_container().display = False
            self._executing = False
            self._debug(f"Processed {count} results.")
        

    async def action_execute(self) -> None:
        """Execute the current expression."""
        if self._executing:
            return
        
        editor = self._active_editor()
        mode = self._active_editor_mode()
        expression = editor.text.strip()
        
        if not expression:
            self._update_output("[yellow]Waiting - No expression to execute[/yellow]")
            return
        
        self._executing = True
        self._update_output("[cyan]Executing...[/cyan]")
        self._debug(f"Executing {mode} expression: {expression!r}")

        try:
            if mode == "wsql":
                self._create_wsql_executor()
                self._update_output(
                    "[cyan]Executing WSQL via WSQLExecutor (DAG orchestration + transpilation)...[/cyan]" # noqa: E501
                )
                self._crawl_worker = self.collect_results(expression, mode="wsql")
            else:
                # Validate expression first
                if not self._validate_expression(expression):
                    self._update_output("[yellow]Waiting - Expression incomplete or invalid[/yellow]") # noqa: E501
                    self._executing = False
                    return
                self._crawl_worker = self.collect_results(expression)
        except (ImportError, RuntimeError, ValueError, AttributeError) as e:
            self._update_output(f"[yellow]WSQL integration error:[/yellow] {e}")
            self._debug(f"WSQL integration error: {type(e).__name__}: {e}")
            self._executing = False
        except SyntaxError as e:
            self._update_output(f"[yellow]Waiting - Syntax Error:[/yellow] {e}")
            self._executing = False
        # except ValueError as e:
        #     self._update_output(f"[yellow]Waiting - Validation Error:[/yellow] {e}")
        #     self._executing = False
        except Exception as e:
            self._update_output(f"[red]Error:[/red] {type(e).__name__}: {e}")
            self._executing = False
        # Do not set _executing = False here: execution runs in the collect_results
        # coroutine; only that coroutine's finally block should clear the flag.

    def action_cancel_crawl(self) -> None:
        """Cancel the currently running crawl (if any)."""
        self._debug(f"Cancelling crawl... executing: {self._executing}, "
                    f"crawl_worker.name: {getattr(self._crawl_worker, 'name', None)}, "
                    f"crawl_worker.is_running: {getattr(self._crawl_worker, 'is_running', False)}")
        if self._executing and self._crawl_worker and self._crawl_worker.is_running:
            self._debug("Cancel requested for crawl.")
            self._crawl_worker.cancel()
    
    def _validate_expression(self, expression: str) -> bool:
        """Validate if expression is complete and well-formed.
        
        Args:
            expression: Expression string to validate
            
        Returns:
            True if expression appears complete, False otherwise
        """
        # Check for balanced parentheses
        paren_count = expression.count('(') - expression.count(')')
        if paren_count != 0:
            return False
        
        # Check for balanced braces
        brace_count = expression.count('{') - expression.count('}')
        if brace_count != 0:
            return False
        
        # Check for balanced brackets
        bracket_count = expression.count('[') - expression.count(']')
        if bracket_count != 0:
            return False
        
        # Check for unclosed quotes
        # Simple check: even number of unescaped quotes
        single_quotes = len([c for i, c in enumerate(expression) 
                            if c == "'" and (i == 0 or expression[i-1] != '\\')])
        double_quotes = len([c for i, c in enumerate(expression)
                            if c == '"' and (i == 0 or expression[i-1] != '\\')])
        
        if single_quotes % 2 != 0 or double_quotes % 2 != 0:
            return False
        
        return True
    
    def action_clear(self) -> None:
        """Clear the output panel."""
        self._update_output("Waiting for expression...")
        self._debug("Cleared output panel.")

    def action_clear_editor(self) -> None:
        """Clear the expression editor (all text)."""
        editor = self._active_editor()
        editor.text = ""
        self._debug(f"{self._active_editor_mode().upper()} editor cleared.")

    def _create_wsql_executor(
        self,
        *,
        concurrency: int = 16,
        per_host: int = 8,
        respect_robots: bool = True,
        verify_ssl: bool = True,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Create a configured ``WSQLExecutor`` from installed WSQL runtime APIs."""
        if not self.wsql_enabled:
            raise RuntimeError(
                "WSQL is disabled. Enable WSQL in Settings (Ctrl+Shift+S) to use this tab."
            )

        install_path = self.wsql_install_path.strip()
        if install_path:
            path = Path(install_path).expanduser()
            if not path.exists():
                raise ValueError(f"WSQL_PATH does not exist: {path}")
            path_text = str(path.resolve())
            if path_text not in sys.path:
                sys.path.insert(0, path_text)
                self._wsql_path_added = True
                self._debug(f"Added WSQL_PATH to sys.path: {path_text}")

        try:
            wsql_runtime_module = importlib.import_module("wsql.runtime.executor")
        except ImportError as e:
            raise ImportError(
                "Could not import 'wsql.runtime.executor'. Install WSQL or set WSQL_PATH in TUI settings." # noqa: E501
            ) from e

        executor_cls = getattr(wsql_runtime_module, "WSQLExecutor", None)
        if executor_cls is None:
            raise AttributeError(
                "wsql.runtime.executor must expose WSQLExecutor"
            )

        # Use a custom executor wrapper so each query context gets a fresh engine.
        # This avoids shared-state issues (e.g. seen_urls) in JOIN/DAG execution.
        class _TUIWSQLExecutor(executor_cls):
            """WSQL executor configured for TUI crawler settings."""

            def _create_engine(self) -> WXPathEngine:  # type: ignore[override]
                from wxpath.http.client.crawler import Crawler

                crawler = Crawler(
                    concurrency=concurrency,
                    per_host=per_host,
                    respect_robots=respect_robots,
                    verify_ssl=verify_ssl,
                    headers=dict(headers) if headers else None,
                )
                return WXPathEngine(crawler=crawler, yield_errors=True)

        return _TUIWSQLExecutor(
            engine=None,
            concurrency=concurrency,
            per_host=per_host,
            respect_robots=respect_robots,
            yield_errors=True,
        )

    def _update_output(self, content: str | RenderableType) -> None:
        """Update the output panel with new content."""
        # output_panel = self.query_one("#output-panel", OutputPanel)
        
        # if isinstance(content, str):
        #     output_panel.update(content)
        # else:
        #     output_panel.update(content)
        panel = self.query_one("#output-panel", OutputPanel)
        panel.remove_children()

        if isinstance(content, str):
            panel.mount(Static(content))
        else:
            panel.mount(Static(content))
    
    def action_clear_debug(self) -> None:
        """Clear the debug panel."""
        panel = self.query_one("#debug-panel", DebugPanel)
        panel.clear()

    def watch_debug_panel_visible(self, visible: bool) -> None:
        """Show or hide the debug panel and persist to config when toggled."""
        container = self.query_one("#debug-container", Container)
        container.display = visible
        self.tui_settings = {
            **self.tui_settings,
            "debug_panel_enabled": visible,
        }
        save_tui_settings(self.tui_settings)

    def action_toggle_debug(self) -> None:
        """Toggle the debug panel visibility."""
        self.debug_panel_visible = not self.debug_panel_visible
        state = "shown" if self.debug_panel_visible else "hidden"
        self._debug(f"Debug panel {state}")

    def action_toggle_progress(self) -> None:
        """Toggle the progress bar (shown during execution when enabled)."""
        self.progress_bar_enabled = not self.progress_bar_enabled
        state = "on" if self.progress_bar_enabled else "off"
        self._debug(f"Progress bar {state}")
        if not self.progress_bar_enabled and self._executing:
            self._progress_bar_container().display = False

    def _escape_rich_markup(self, s: str) -> str:
       """Escape [ and ] so Rich does not interpret them as markup."""
       return s.replace("[", "\\[").replace("]", "\\]")

    def _debug(self, message: str) -> None:
        """Append a timestamped message to the debug panel."""
        panel = self.query_one("#debug-panel", DebugPanel)
        timestamp = datetime.now().strftime("%H:%M:%S")
        panel.append(f"[dim]{timestamp}[/dim] {self._escape_rich_markup(message)}")

    def _format_stream_item(self, result: Any):
        """Helps format stream items for display."""
        if isinstance(result, dict):
            return self._format_dict(result)
        elif isinstance(result, HtmlElement):
            return self._format_html_element(result)
        else:
            return str(result)

    def _format_html_element(self, elem: HtmlElement) -> str:
        """Format HTML element with partial content display.
        
        Converts lxml HtmlElement to string representation, truncating at
        300 characters and escaping Rich markup brackets.
        
        Args:
            elem: HTML element to format
            
        Returns:
            Formatted string representation with Rich markup
        """
        try:
            html_str = tostring(elem, encoding='unicode', method='html')
            
            # Truncate long HTML
            if len(html_str) > 300:
                html_str = html_str[:300] + "..."
            
            # Escape brackets for Rich markup
            html_str = html_str.replace("[", "\\[")
            
            return f"  [green]{html_str}[/green]"
        except Exception as e:
            return f"  [yellow]<{elem.tag}> (error formatting: {e})[/yellow]"
    
    def _format_dict(self, d: dict) -> str:
        """Format dictionary with indentation.
        
        Args:
            d: Dictionary to format
            
        Returns:
            Formatted string
        """
        lines = ["  {"]
        for key, value in d.items():
            if isinstance(value, str) and len(value) > 100:
                value = value[:100] + "..."
            lines.append(f"    {key!r}: {value!r},")
        lines.append("  }")
        return "\n".join(lines)

def main():
    """Launch the wxpath TUI application.
    
    Entry point for the wxpath-tui command-line tool. Creates and runs
    the interactive terminal interface for testing wxpath expressions.
    
    Example:
        Run from command line::
        
            $ wxpath-tui
    
    Note:
        This function blocks until the user quits the application with
        Ctrl+Q or closes the terminal.
    """
    app = WXPathTUI()
    app.run()


if __name__ == "__main__":
    main()
