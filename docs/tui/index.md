# wxpath TUI - Interactive Expression Testing


> NOTE: I highly recommended you enable caching (Ctrl+L) for faster execution, and set **depth** (i.e., `url('...', depth=...)`) for capped crawls to be polite to the servers you are crawling.

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
- **Cancel Crawl**: Press **Escape** during a run to stop the crawl; results already received stay in the table

## 🚀 Installation

Install wxpath with TUI support:

```bash
pip install -e ".[tui]"
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
| `Escape` | Cancel Crawl | Stop the running crawl; partial results are kept |
| `Ctrl+E` | Export | Export table data (CSV or JSON) |
| `Ctrl+C` | Clear | Clear the output panel |
| `Ctrl+H` | Headers | Configure HTTP headers (JSON) |
| `Ctrl+Shift+S` | Settings | Edit persistent crawler settings (CONCURRENCY, PER_HOST, RESPECT_ROBOTS) |
| `Ctrl+L` | Cache | Toggle HTTP caching on/off (SQLite for now) |
| `Ctrl+Shift+D` | Toggle Debug | Show or hide the debug panel |
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
┌─────────────────────────────────────┐
│   Textual Framework                 │  ← Modern TUI with Rich rendering
├─────────────────────────────────────┤
│   Expression Editor (TextArea)      │  ← Real-time validation
├─────────────────────────────────────┤
│   WXPath Engine                     │  ← Async concurrent execution
├─────────────────────────────────────┤
│   Output Renderer                   │  ← Smart formatting (HTML/Table)
│   • HTML Elements                   │
│   • Dict → Table                    │
│   • Error Messages                  │
└─────────────────────────────────────┘
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
User Types → Validation → Press Execute → Parse → Run Engine → Format → Display
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

Crawler settings are saved to a config file and reused across sessions:

| Setting | Description | Default |
|---------|-------------|---------|
| **CONCURRENCY** | Maximum concurrent HTTP requests | 16 |
| **PER_HOST** | Maximum concurrent requests per host | 8 |
| **RESPECT_ROBOTS** | Whether to respect robots.txt | ON (true) |

- **Config file**: `~/.config/wxpath/tui_settings.json` (or `$XDG_CONFIG_HOME/wxpath/tui_settings.json` if set).
- **When applied**: Values are used for the next expression run after you save.
- **Extending**: New settings can be added by extending the schema in `src/wxpath/tui_settings.py` and using the value where the crawler/engine is created.

