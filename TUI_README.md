# wxpath TUI - Interactive Expression Testing

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    wxpath TUI - Interactive Testing                          ║
║                   Architected for Elegance & Precision                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
```


## ✨ Features

### 📝 **Top Panel** - Expression Editor
- Syntax-aware text editing
- Real-time validation feedback
- Smart bracket/quote matching
- Inline error detection

### 📊 **Bottom Panel** - Live Output Display
- **HTML Elements**: Formatted with partial content display (first 300 chars)
- **Dict/XPathMap**: Automatically rendered as elegant tables
- **Sortable columns**: Click a column header to sort by that column; click again to toggle ascending/descending
- **Export**: Export table data to CSV or JSON (Ctrl+E or Export button)
- **Error Messages**: Clear validation and execution feedback  
- **Waiting State**: Shows when expression is incomplete or invalid
- **Streaming Results**: Live updates as data arrives (max 10 items shown)

## 🚀 Installation

Install wxpath with TUI support:

```bash
pip install -e ".[tui]"
```

Enable Playwright and stealth crawler backends:

```bash
pip install -e ".[tui,playwright]"
```

Or install textual separately if wxpath is already installed:

```bash
pip install textual>=1.0.0
```

## 🎯 Usage

### Launch the TUI

```bash
# Using the installed command
wxpath-tui

# Or run as module
python -m wxpath.tui
```

### Keybindings

| Key | Action | Description |
|-----|--------|-------------|
| `Ctrl+R` or `F5` | Execute | Run the current expression |
| `Escape` | Cancel Crawl | Stop the currently running crawl |
| `Ctrl+E` | Export | Export table data (CSV or JSON) |
| `Ctrl+C` | Clear | Clear the output panel |
| `Ctrl+Shift+Backspace` | Clear Editor | Clear all text in the expression editor |
| `Cmd+Backspace` (macOS) | Full line clear | Clear the current line in the expression editor |
| `Ctrl+Shift+S` | Settings | Edit all persistent settings (crawler, cache, debug panel, HTTP headers) |
| `Ctrl+L` | Cache | Toggle HTTP caching on/off (saved to config; default: on) |
| `Ctrl+Shift+D` | Toggle Debug | Show or hide the debug panel (saved to config; default: off) |
| `Ctrl+P` | Progress bar | Toggle progress bar during execution (on by default) |
| `Ctrl+Q` | Quit | Exit the application |
| Click column header | Sort | Sort table by that column; click again to toggle ascending/descending |

## 📚 Example Expressions

### 1. Simple Text Extraction
```python
url('https://quotes.toscrape.com')//span[@class='text']/text()
```
**Output**: List of text strings

---

### 2. Map Extraction (Table View)
```python
url('https://quotes.toscrape.com')//div[@class='quote']/map {
  'quote': .//span[@class='text']/text(),
  'author': .//span[@class='author']/text(),
  'tags': .//div[@class='tags']//a/text()
}
```
**Output**: Formatted table with columns: quote, author, tags

---

### 3. Link Following (Crawling)
```python
url('https://quotes.toscrape.com')
  ///url(//a[contains(@href, '/author/')]/@href)
    //h3[@class='author-title']/text()
```
**Output**: Author names from linked pages

---

### 4. HTML Element Extraction
```python
url('https://quotes.toscrape.com')//div[@class='quote']
```
**Output**: Partial HTML of matching elements

## 🏗️ Architecture

The TUI embodies wxpath's architectural philosophy:

```
┌-------------------------------------┐
│   Textual Framework                 │  ← Modern TUI with Rich rendering
├-------------------------------------┤
│   Expression Editor (TextArea)      │  ← Real-time validation
├-------------------------------------┤
│   WXPath Engine                     │  ← Async concurrent execution
├-------------------------------------┤
│   Output Renderer                   │  ← Smart formatting (HTML/Table)
│   • HTML Elements                   │
│   • Dict -> Table                    │
│   • Error Messages                  │
└-------------------------------------┘
```

### Key Components

- **Textual**: Modern terminal UI framework with Rich rendering
- **WXPath Engine**: Async execution with concurrent crawling
- **Reactive Validation**: Live feedback as you type
- **Smart Formatting**: Automatic detection and formatting of result types
- **Hook System**: XPathMap serialization for clean dict output

## 🔍 How It Works

### Expression Validation

The TUI validates your expression in real-time:

1. **Balance Checking**: Parentheses `()`, brackets `[]`, braces `{}`
2. **Quote Matching**: Single `'` and double `"` quotes
3. **Syntax Validation**: Parser checks for valid wxpath syntax
4. **Feedback Display**: Shows "Waiting" until expression is complete

### Execution Flow

```
User Types -> Validation -> Press Execute -> Parse -> Run Engine -> Format -> Display
     ↓           ↓             ↓            ↓         ↓          ↓         ↓
  TextArea   Balance?     Parser OK?   AST Built  HTTP Req  HTML/Table  Output
              ↓                          
          "Waiting" or "Valid"
```

### Output Formatting

| Input Type | Output Format | Details |
|------------|---------------|---------|
| `HtmlElement` | Partial HTML string | First 300 chars, escaped |
| `dict` (single) | Indented key-value | Pretty-printed |
| `[dict, dict, ...]` | Table | Columns auto-detected |
| `str` | Plain text | Truncated if >200 chars |
| Other | String repr | Generic fallback |

## ⚙️ Configuration

### Persistent Settings (Ctrl+Shift+S)

All TUI settings are in one config file and in the **Settings** modal: crawler options, debug panel, cache, and HTTP headers (JSON).

| Setting | Description | Default |
|---------|-------------|---------|
| **CRAWLER_TYPE** | HTTP backend (`aiohttp`, `playwright`, `flaresolverr`) | `aiohttp` |
| **CONCURRENCY** | Maximum concurrent HTTP requests | 16 |
| **PER_HOST** | Maximum concurrent requests per host | 8 |
| **RESPECT_ROBOTS** | Whether to respect robots.txt | ON (true) |
| **VERIFY_SSL** | Verify SSL certificates | ON (true) |
| **PLAYWRIGHT_STEALTH** | Enable stealth evasions when using Playwright crawler | OFF (false) |
| **FLARESOLVERR_URL** | FlareSolverr API endpoint for `flaresolverr` crawler | `http://localhost:8191/v1` |
| **DEBUG_PANEL** | Show the debug panel | OFF (false) |
| **CACHE** | Enable HTTP caching | ON (true) for TUI |
| **HTTP_HEADERS** | Custom HTTP headers (JSON) | `{}` |

- **Config file**: `~/.config/wxpath/tui_settings.json` (or `$XDG_CONFIG_HOME/wxpath/tui_settings.json` if set).
- **When applied**: Used for the next run after save. Toggling cache (Ctrl+L) or debug panel (Ctrl+Shift+D) also persists.
- **Headers**: Configure in the Settings modal as a JSON object (e.g. `{"User-Agent": "MyBot/1.0"}`).

### Customization

TODO


## 🎨 Design Philosophy

Following wxpath's mandate to embody 1930s architectural elegance:

- **Clean Lines**: Minimal, purposeful UI elements
- **Functional Beauty**: Every widget serves a clear purpose  
- **Professional Precision**: Exact spacing, alignment, typography
- **Intuitive Flow**: Natural top-to-bottom workflow
- **Robust Construction**: Solid error handling and validation

> *"Form follows function - that has been misunderstood. Form and function should be one, joined in a spiritual union."*  
> — Frank Lloyd Wright (adapted for terminal interfaces)

## 📋 Requirements

- Python 3.10+
- textual >= 1.0.0
- wxpath with all dependencies
- lxml (for HTML parsing)
- rich (via textual)

## 🐛 Troubleshooting

### "Waiting - Expression incomplete"
- Check for unclosed quotes, brackets, or parentheses
- Ensure all `{...}` blocks are closed
- Verify string literals are properly quoted

### "No results returned"
- Expression parsed successfully but found no matches
- Check XPath syntax and element selectors
- Verify the URL is accessible

### "Timeout after 30s"
- Site may be slow or unresponsive
- Partial results shown if any were collected
- Consider testing with a faster/local site

### Import errors
```bash
# Install textual
pip install textual

# Or reinstall wxpath with TUI
pip install -e ".[tui]"
```

## 📖 See Also

- [examples_tui.md](examples_tui.md) - More example expressions
- [wxpath Documentation](https://rodricios.github.io/wxpath/)
- [Textual Documentation](https://textual.textualize.io/)

## 🤝 Contributing

The TUI follows wxpath's contribution guidelines. When making changes:

1. Maintain the architectural aesthetic
2. Add docstrings in Google style
3. Test with `python test_tui_structure.py`
4. Update examples if adding features

---

**Status**: ⚠️ Pre-1.0.0 - APIs and contracts may change  
**Documentation**: Generated by LLM - requires human review
