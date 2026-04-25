# pdf-report-generator

An MCP server that generates professional corporate PDF reports from structured JSON specs or raw LLM text output. Drop it into Claude Desktop (or any MCP client) and ask Claude to turn analysis, research, or meeting notes into a polished multi-page report complete with cover page, table of contents, executive summary, section headings, tables, and charts.

A sample output is at [`examples/sample_report.pdf`](examples/sample_report.pdf).

---

## Prerequisites

- **Node.js 18+**
- **Python 3.8+**

Install Python dependencies:

```bash
pip install reportlab matplotlib
```

---

## Claude Desktop configuration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pdf-report": {
      "command": "npx",
      "args": ["-y", "pdf-report-generator"]
    }
  }
}
```

---

## Available tools

### `generate_report`

Generates a PDF from a full structured spec.

**Minimal example input:**

```json
{
  "spec": {
    "metadata": {
      "title": "Q3 Performance Review",
      "author": "Engineering Team",
      "company": "Acme Corp",
      "classification": "INTERNAL"
    },
    "executive_summary": "Overall performance improved this quarter...",
    "sections": [
      {
        "heading": "Infrastructure",
        "body": "Uptime reached 99.94%...",
        "subsections": []
      }
    ],
    "tables": [],
    "charts": []
  }
}
```

---

### `generate_report_from_text`

Converts raw text into a structured PDF report. Sections are auto-detected from headings.

```json
{
  "text": "# Overview\nThis quarter...\n\n# Key Findings\n...",
  "title": "Q3 Summary",
  "author": "Data Team",
  "company": "Acme Corp",
  "classification": "INTERNAL",
  "theme_name": "navy"
}
```

---

### `list_themes`

Returns available color themes: `default`, `navy`, `charcoal`, `forest`, `burgundy`.

---

## JSON spec reference

```
metadata
  title*          string
  subtitle        string
  author          string
  date            string (YYYY-MM-DD; defaults to today)
  company         string
  department      string
  document_id     string  (e.g. RPT-2026-001)
  classification  string  (PUBLIC | INTERNAL | CONFIDENTIAL)
  logo_path       string  (absolute path to PNG/JPG)
  page_size       "letter" | "a4"

executive_summary  string

sections[]
  heading*        string
  body*           string  (\n\n = paragraph break)
  subsections[]
    heading*      string
    body*         string

tables[]
  title           string
  headers*        string[]
  rows*           string[][]
  after_section   int  (0-based section index; -1 = after exec summary)

charts[]
  title           string
  type            "bar" | "line" | "pie" | "horizontal_bar"
  labels*         string[]
  datasets*       [{label, values[]}]
  after_section   int

images[]
  path*           string  (absolute path)
  caption         string
  width_inches    number
  after_section   int

theme
  primary_color    [R, G, B]
  accent_color     [R, G, B]
  highlight_color  [R, G, B]
```

---

## Example prompts

- "Turn this analysis into a professional internal PDF report titled 'Q3 Infrastructure Review'"
- "Generate a corporate report from this research, add a bar chart for the monthly metrics"
- "Create a CONFIDENTIAL report called 'Security Audit Findings' from this text"
- "List the available report themes"

---

## Troubleshooting

**Python not found** — ensure `python` or `python3` is on your PATH and is version 3.8+.

**reportlab not installed** — run `pip install reportlab matplotlib`.

**Charts missing** — matplotlib is required for charts. Install it with `pip install matplotlib`.

**Large PDFs** — complex specs with many charts can take 5–15 seconds. This is normal.

---

## License

MIT
