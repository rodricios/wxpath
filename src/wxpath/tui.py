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
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from elementpath.xpath_tokens import XPathMap
from lxml.html import HtmlElement, tostring
from rich.console import RenderableType
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Static,
    Switch,
    TextArea,
)

from wxpath.core.runtime.engine import WXPathEngine
from wxpath.hooks import registry
from wxpath.hooks.builtin import SerializeXPathMapAndNodeHook
from wxpath.settings import SETTINGS
from wxpath.tui_settings import (
    TUISettingsSchema,
    load_tui_settings,
    save_tui_settings,
    validate_tui_settings,
)


class HeadersScreen(ModalScreen):
    """Modal screen for editing HTTP headers.
    
    Allows users to paste and edit custom HTTP headers in JSON format.
    Headers are applied to all subsequent HTTP requests.
    """
    
    CSS = """
    HeadersScreen {
        align: center middle;
    }
    
    #headers-dialog {
        width: 80;
        height: 25;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    
    #headers-title {
        background: $primary;
        color: $text;
        text-style: bold;
        padding: 0 2;
        dock: top;
    }
    
    #headers-editor {
        height: 1fr;
        margin: 1 0;
    }
    
    #headers-help {
        color: $text-muted;
        margin-bottom: 1;
    }
    
    #headers-buttons {
        height: auto;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
    }
    """
    
    def __init__(self, current_headers: dict):
        """Initialize headers screen with current headers.
        
        Args:
            current_headers: Dictionary of current HTTP headers
        """
        super().__init__()
        self.current_headers = current_headers
    
    def compose(self) -> ComposeResult:
        """Build the headers dialog layout."""
        with Vertical(id="headers-dialog"):
            yield Static("HTTP Headers Configuration", id="headers-title")
            yield Static(
                ("Enter headers as JSON (one per line or as object)."
                 " Press Ctrl+S to save, Escape to cancel."),
                id="headers-help"
            )
            
            # Pre-populate with current headers in JSON format
            headers_json = json.dumps(self.current_headers, indent=2)
            yield TextArea(headers_json, language="json", id="headers-editor")
            
            with Container(id="headers-buttons"):
                yield Button("Save (Ctrl+S)", variant="primary", id="save-btn")
                yield Button("Cancel (Esc)", variant="default", id="cancel-btn")
    
    def on_mount(self) -> None:
        """Focus the editor when screen mounts."""
        self.query_one("#headers-editor", TextArea).focus()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "save-btn":
            self._save_headers()
        elif event.button.id == "cancel-btn":
            self.dismiss(None)
    
    def on_key(self, event) -> None:
        """Handle keyboard shortcuts."""
        if event.key == "ctrl+s":
            self._save_headers()
            event.prevent_default()
        elif event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
    
    def _save_headers(self) -> None:
        """Parse and save the headers."""
        editor = self.query_one("#headers-editor", TextArea)
        headers_text = editor.text.strip()
        
        if not headers_text:
            # Empty headers = use defaults
            self.dismiss({})
            return
        
        try:
            # Try to parse as JSON
            headers = json.loads(headers_text)
            
            if not isinstance(headers, dict):
                self.notify("Headers must be a JSON object/dict", severity="error")
                return
            
            # Validate all keys and values are strings
            for key, value in headers.items():
                if not isinstance(key, str):
                    self.notify(f"Header key must be string: {key}", severity="error")
                    return
                if not isinstance(value, str):
                    self.notify(f"Header value must be string: {value}", severity="error")
                    return
            
            self.dismiss(headers)
            
        except json.JSONDecodeError as e:
            self.notify(f"Invalid JSON: {e}", severity="error")


class SettingsScreen(ModalScreen):
    """Modal screen for editing persistent TUI settings (CONCURRENCY, PER_HOST, RESPECT_ROBOTS).

    Settings are saved to ~/.config/wxpath/tui_settings.json and applied to the
    crawler/engine on the next run.
    """

    CSS = """
    SettingsScreen {
        align: center middle;
    }

    #settings-dialog {
        width: 60;
        min-height: 18;
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
            yield Static("Crawler Settings (persistent)", id="settings-title")
            yield Static(
                "Values are saved to config and used for the next run. Ctrl+S save, Esc cancel.",
                id="settings-help",
            )
            for entry in TUISettingsSchema:
                key = entry["key"]
                label = entry["label"]
                typ = entry["type"]
                value = self.current.get(key, entry["default"])
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
        result = {}
        for entry in TUISettingsSchema:
            key = entry["key"]
            # typ = entry["type"]
            node = self.query_one(f"#setting-{key}")
            if isinstance(node, Input):
                raw = node.value.strip()
                result[key] = int(raw) if raw else entry["default"]
            else:
                result[key] = node.value
        return result

    def _validate(self, data: dict[str, Any]) -> str | None:
        errors = validate_tui_settings(data)
        return errors[0] if errors else None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-save-btn":
            data = self._gather()
            err = self._validate(data)
            if err:
                self.notify(err, severity="error")
                return
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
    }
    
    #editor-container {
        height: 40%;
        border: heavy $primary;
        background: $panel;
    }
    
    #output-container {
        /* height: 60%; */
        height: 60%;
        border: heavy $accent;
        background: $panel;
    }
    
    #output-panel {
        height: 3fr;
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
    
    TextArea {
        height: 100%;
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
        ("escape", "cancel_crawl", "Cancel Crawl"),
        ("ctrl+c", "clear", "Clear"),
        ("ctrl+d", "clear_debug", "Clear Debug"),
        ("ctrl+shift+d", "toggle_debug", "Toggle Debug"),
        ("ctrl+e", "export", "Export"),
        ("ctrl+l", "toggle_cache", "Cache"),
        ("ctrl+h", "edit_headers", "Headers"),
        ("ctrl+shift+s", "edit_settings", "Settings"),
        ("f5", "execute", "Execute"),
        ("tab", "focus_next", "Focus Next"),
    ]

    cache_enabled = reactive(False)
    debug_panel_visible = reactive(True)
    custom_headers = reactive({})
    tui_settings = reactive({})
    
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
        # Don't set cache_enabled here - let on_mount handle it
    
    def compose(self) -> ComposeResult:
        """Build the application layout."""
        yield Header()
        
        with Container(id="editor-container"):
            yield Static("Expression Editor (Ctrl+R to execute)", classes="panel-header")
            yield TextArea(id="expression-editor", language="python")
        
        with Container(id="output-container"):
            yield Static("Output", classes="panel-header") 
            yield OutputPanel(id="output-panel")
            # yield Button("Export (Ctrl+E)", id="export_button")
        
            with Container(id="debug-container"):
                yield Static("Debug", id="debug-header", classes="panel-header")
                yield DebugPanel(id="debug-panel")
            
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize with a sample expression."""
        # Set cache_enabled from settings - this will trigger the watcher and update subtitle
        self.cache_enabled = bool(SETTINGS.http.client.cache.enabled)
        # Load persistent TUI settings (CONCURRENCY, PER_HOST, RESPECT_ROBOTS)
        self.tui_settings = load_tui_settings()
        
        editor = self.query_one("#expression-editor", TextArea)
        # Start with a simple example
        editor.text = "url('https://quotes.toscrape.com')//span[@class='text']/text()"
        editor.focus()
        
        # Show initial help text
        self._update_output(
            "[dim]Welcome to wxpath TUI![/dim]\n\n"
            "[cyan]Quick Start:[/cyan]\n"
            "  • Edit the expression above\n"
            "  • Press [bold]Ctrl+R[/bold] or [bold]F5[/bold] to execute\n"
            "  • Press [bold]Escape[/bold] to cancel a running crawl\n"
            "  • Press [bold]Ctrl+E[/bold] to export table (CSV/JSON)\n"
            "  • Press [bold]Ctrl+C[/bold] to clear output\n"
            "  • Press [bold]Ctrl+Shift+D[/bold] to toggle debug panel\n"
            "  • Press [bold]Ctrl+H[/bold] to configure HTTP headers\n"
            "  • Press [bold]Ctrl+Shift+S[/bold] to edit persistent settings (concurrency, robots)\n" # noqa: E501
            "  • Press [bold]Ctrl+L[/bold] to toggle HTTP caching\n"
            "  • Use [bold]arrow keys[/bold] or [bold]scroll[/bold] to view results\n\n"
            "[cyan]Example expressions:[/cyan]\n"
            "  • Extract text: url('...')//div//text()\n"
            "  • Extract as dict/table: url('...')//div/map { 'title': .//h1/text() }\n"
            "  • Follow links: url('...') ///url(//a/@href) //div/text()\n\n"
            "[green]Expression appears valid - Press Ctrl+R or F5 to execute[/green]"
        )

    def watch_cache_enabled(self, new_value: bool) -> None:
        """Update global settings and subtitle when cache setting changes."""
        # Update the global settings - this is what the HTTP crawler will read
        SETTINGS.http.client.cache.enabled = bool(new_value)
        print(f"Cache enabled: {SETTINGS.http.client.cache.enabled}")
        self._update_subtitle()
    
    def watch_custom_headers(self, new_value: dict) -> None:
        """Update subtitle when custom headers change."""
        self._update_subtitle()

    def watch_tui_settings(self, new_value: dict) -> None:
        """Update subtitle when persistent settings change."""
        self._update_subtitle()
    
    def _update_subtitle(self) -> None:
        """Update subtitle with current cache, headers, and persistent settings."""
        cache_state = "ON" if self.cache_enabled else "OFF"
        headers_count = len(self.custom_headers)
        headers_info = f"{headers_count} custom" if headers_count > 0 else "default"
        conc = self.tui_settings.get("concurrency", 16)
        ph = self.tui_settings.get("per_host", 8)
        robots = "ON" if self.tui_settings.get("respect_robots", True) else "OFF"
        self.sub_title = (
            f"Cache: {cache_state} | Headers: {headers_info} | "
            f"Concurrency: {conc} | Per host: {ph} | Robots: {robots} | "
            f"Ctrl+R: Run | Ctrl+Shift+S: Settings | Ctrl+Q: Quit"
        )

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
    
    def action_edit_headers(self) -> None:
        """Open the headers configuration screen."""
        def handle_headers_result(result):
            """Handle the result from the headers screen."""
            if result is not None:
                self.custom_headers = result
                count = len(result)
                if count == 0:
                    self._update_output(
                        "[cyan]Headers cleared - using defaults[/cyan]\n\n"
                        "[dim]This will apply to the next expression execution.[/dim]"
                    )
                else:
                    headers_preview = json.dumps(result, indent=2)
                    self._update_output(
                        f"[cyan]Custom headers saved ({count} headers)[/cyan]\n\n"
                        f"[green]{headers_preview}[/green]\n\n"
                        "[dim]These will apply to the next expression execution.[/dim]"
                    )
        
        self.push_screen(HeadersScreen(dict(self.custom_headers)), handle_headers_result)
        self._debug("Opened headers configuration screen")

    def action_edit_settings(self) -> None:
        """Open the persistent settings screen (CONCURRENCY, PER_HOST, RESPECT_ROBOTS)."""
        def handle_settings_result(result: dict[str, Any] | None) -> None:
            if result is not None:
                self.tui_settings = result
                self._update_output(
                    "[cyan]Persistent settings saved[/cyan]\n\n"
                    f"CONCURRENCY: {result.get('concurrency', 16)} | "
                    f"PER_HOST: {result.get('per_host', 8)} | "
                    f"RESPECT_ROBOTS: {result.get('respect_robots', True)}\n\n"
                    "[dim]These apply to the next expression execution.[/dim]"
                )
                self._debug("Persistent settings saved and applied")

        self.push_screen(SettingsScreen(dict(self.tui_settings)), handle_settings_result)
        self._debug("Opened persistent settings screen")

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
    
    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Validate expression as user types."""
        if event.text_area.id != "expression-editor":
            return
        
        expression = event.text_area.text.strip()
        
        if not expression:
            self._update_output("[dim]Waiting - Enter an expression and press Ctrl+R "
                                "or F5 to execute[/dim]")
            return
        
        # Show validation status
        if not self._validate_expression(expression):
            self._update_output("[yellow]Waiting - Expression incomplete (check parentheses,"
                                " braces, brackets, quotes)[/yellow]")
        else:
            self._update_output("[green]Expression appears valid - Press Ctrl+R or F5 to execute"
                                "[/green]")
    
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
            row.append("" if value is None else str(value))
        return row

    @work(exclusive=True)
    async def collect_results(self, expression: str) -> None:
        """Collect results from the expression."""
        count = 0
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
            engine = WXPathEngine(crawler=crawler)
            
            # Streaming approach
            panel = self.query_one("#output-panel", OutputPanel)
            panel.clear()

            # data_table = None
            data_table = DataTable(show_header=True, zebra_stripes=True)
            panel.mount(data_table)
            columns_initialized = False
            column_keys: list[str] = []

            async for result in engine.run(expression, max_depth=1, progress=False):
                count += 1
                if count % 100 == 0:
                    self._debug(f"Received result {count} of type {type(result).__name__}")

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
                panel.append(f"[yellow]Crawl cancelled — {count} partial result(s) shown.[/yellow]")
            else:
                panel.append("[yellow]Crawl cancelled.[/yellow]")
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
            # Handle execution errors separately
            self._update_output(f"[red]Execution Error:[/red] {type(e).__name__}: {e}")
            self._executing = False
            return
        finally:
            self._executing = False
            self._debug(f"Processed {count} results.")
        

    async def action_execute(self) -> None:
        """Execute the current expression."""
        if self._executing:
            return
        
        editor = self.query_one("#expression-editor", TextArea)
        expression = editor.text.strip()
        
        if not expression:
            self._update_output("[yellow]Waiting - No expression to execute[/yellow]")
            return
        
        self._executing = True
        self._update_output("[cyan]Executing...[/cyan]")
        self._debug(f"Executing expression: {expression!r}")

        try:
            # Validate expression first
            if not self._validate_expression(expression):
                self._update_output("[yellow]Waiting - Expression incomplete or invalid[/yellow]")
                self._executing = False
                return
            
            # # Parse the expression - useful for deducing if to display table
            # parsed = parser.parse(expression)
            self._crawl_worker = self.collect_results(expression)
        except SyntaxError as e:
            self._update_output(f"[yellow]Waiting - Syntax Error:[/yellow] {e}")
            self._executing = False
        except ValueError as e:
            self._update_output(f"[yellow]Waiting - Validation Error:[/yellow] {e}")
            self._executing = False
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
        """Show or hide the debug panel when toggled."""
        container = self.query_one("#debug-container", Container)
        container.display = visible

    def action_toggle_debug(self) -> None:
        """Toggle the debug panel visibility."""
        self.debug_panel_visible = not self.debug_panel_visible
        state = "shown" if self.debug_panel_visible else "hidden"
        self._debug(f"Debug panel {state}")

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
