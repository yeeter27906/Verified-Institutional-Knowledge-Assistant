# MetaKGP Wiki Scraper

A robust, concurrent wiki scraper for MetaKGP (https://wiki.metakgp.org) with batch processing, multi-threading, Wikitext cleaning, and organized output.

## Features

- **Concurrent scraping** with 4-20 threads for parallel processing
- **Wikitext cleaning** - automatic conversion to clean Markdown format
- **Infobox extraction** - converts infoboxes to readable summaries
- **Link cleaning** - converts wiki links to plain text
- **Database upload** - PostgreSQL integration with --database flag
- **Batch file storage** - save pages in separate files for better organization
- **Flexible control** - scrape specific ranges, limits, or the entire wiki
- **Multiple formats** - JSON (structured), text (raw), and Markdown (cleaned)
- **Complete page list** - all pages already fetched
- **Easy to use** - simple Python commands
- **Clean structure** - organized src/ and results/ folders

## Project Structure

```
testing/
├── src/                        # Source code
│   ├── main.py                # Main parallel scraper
│   ├── fetch_all_links.py     # Fetch all page links
│   └── wikitext_cleaner.py    # Clean wikitext to Markdown
├── results/                    # All data outputs
│   ├── all_pages.json         # List of all pages
│   ├── all_pages.txt          # Text version
│   └── scraped_data/          # Scraped page content
│       ├── scraped_pages.json # JSON with both raw & cleaned text
│       └── ...
├── venv/                       # Python virtual environment
└── README.md                   # This file
```

## Quick Start

### 1. Activate Environment

```bash
# Activate virtual environment (from project root)
source venv/bin/activate
```

### 2. Get All Pages
```bash
# Fetch All Pages
python src/fetch_all_links.py
```

### 3. Scrape Pages

```bash
# Quick sample (10 pages - creates JSON with both raw and cleaned text)
python src/main.py results/all_pages.json --limit 10

# Medium batch (100 pages in batches of 25)
python src/main.py results/all_pages.json --limit 100 --pages 25 --threads 8

# Full wiki (all 3,583 pages in batches of 50)
python src/main.py results/all_pages.json --pages 50 --threads 4

# With database upload (requires .env file at submissions/team_2/.env)
python src/main.py results/all_pages.json --limit 10 --database

# Optional: Also export raw wikitext to separate text file
python src/main.py results/all_pages.json --limit 10 --text
```

**Note:** The `--database` flag requires database credentials in the unified `.env` file at `submissions/team_2/.env` (see main README for setup).

### 4. Check Results

```bash
# View JSON structure with both raw and cleaned text
cat results/scraped_data/scraped_pages.json | jq '.pages[0]'

# View just the cleaned text from JSON
python -c "import json; print(json.load(open('results/scraped_data/scraped_pages.json'))['pages'][0]['cleaned_text'])"
```

## Wikitext Cleaning Features

The scraper automatically cleans Wikitext into human-readable Markdown format:

### Features

1. **Infobox Extraction**
   - Converts `{{Infobox ...}}` templates to readable summary paragraphs
   - Places summary at the start of the document
   - Example: `**Summary:** name: IIT Kharagpur; established: 1951; type: Public`

2. **Header Conversion**
   - `==Introduction==` → `## Introduction`
   - `===Subsection===` → `### Subsection`
   - Maintains proper Markdown header hierarchy

3. **Link Cleaning**
   - `[[Target|Display]]` → `Display`
   - `[[Target]]` → `Target`
   - Removes wiki markup while preserving text

4. **Template Removal**
   - Removes citation templates
   - Cleans up navigation boxes
   - Preserves important content

5. **Additional Cleanup**
   - Removes HTML comments
   - Cleans up references
   - Normalizes whitespace

### Example Transformation

**Before (Wikitext):**
```wikitext
{{Infobox university
| name = IIT Kharagpur
| established = 1951
}}

==Introduction==
The [[Indian Institute of Technology Kharagpur|IIT Kharagpur]] is located in [[Kharagpur]].

===History===
It was established in 1951.
```

**After (Cleaned Markdown):**
```markdown
**Summary:** name: IIT Kharagpur; established: 1951.

## Introduction
The IIT Kharagpur is located in Kharagpur.

### History
It was established in 1951.
```

## Usage Examples

### Basic Usage

```bash
# Scrape 10 pages (creates JSON with both raw and cleaned text)
python src/main.py results/all_pages.json --limit 10

# Also export raw wikitext to separate .txt file
python src/main.py results/all_pages.json --limit 10 --text
```

### Batch Processing

```bash
# Scrape 100 pages in batches of 20 (creates 5 files)
python src/main.py results/all_pages.json --limit 100 --pages 20

# Each batch file contains max 20 pages:
# - results/scraped_data/scraped_pages_batch1.json
# - results/scraped_data/scraped_pages_batch2.json
# - results/scraped_data/scraped_pages_batch3.json
# - results/scraped_data/scraped_pages_batch4.json
# - results/scraped_data/scraped_pages_batch5.json
```

### Advanced Options

```bash
# Increase threads for faster scraping
python src/main.py results/all_pages.json --limit 100 --threads 8

# Skip first 50 pages, scrape next 50
python src/main.py results/all_pages.json --start 50 --limit 50

# Scrape ALL pages in batches of 100 with text output
python src/main.py results/all_pages.json --pages 100 --threads 8 --text
```

## Command-Line Options

### main.py

```
Required:
  input_file              JSON file with list of pages (use results/all_pages.json)

Optional:
  --limit N               Total number of pages to scrape (default: all)
  --pages N               Batch size - max pages per output file (default: all in one file)
  --threads N             Number of concurrent threads (default: 4, max: 20)
  --start N               Starting index in page list (default: 0)
  --text                  Export raw wikitext to separate .txt file
  --database              Upload scraped pages to PostgreSQL database
```

**Note:** The scraper automatically cleans all pages. By default, it creates only a JSON file containing both `text` (raw wikitext) and `cleaned_text` (cleaned markdown) fields. Use `--text` flag to also export a separate raw wikitext file. Use `--database` flag to upload to PostgreSQL (requires `.env` file in team_2 folder).

### fetch_all_links.py

```
Optional:
  --output FILE           Output filename (default: all_pages)
  --no-text              Don't save text version
```

## Performance

- **Speed:** ~0.36-0.40 seconds per page with 4 threads
- **Full wiki:** ~20-30 minutes for all 3,583 pages
- **Memory:** Minimal - each batch saved immediately

## Common Workflows

### 1. First Time Setup

```bash
source venv/bin/activate
python src/fetch_all_links.py  # Fetches all page titles
```

### 2. Sample Testing

```bash
# Test with 10 pages first
python src/main.py results/all_pages.json --limit 10

# Check output
cat results/scraped_data/scraped_pages.json | jq '.pages | length'
```

### 3. Production Scraping

```bash
# Scrape entire wiki in manageable batches
python src/main.py results/all_pages.json --pages 50 --threads 8 --text

# Both JSON and text formats for easy viewing
```

### 4. Specific Range

```bash
# Scrape pages 1000-1100 in batches of 25
python src/main.py results/all_pages.json --start 1000 --limit 100 --pages 25
```

## All Available Scripts

### Concurrent Scraper (Main Tool)

```bash
python src/main.py results/all_pages.json [OPTIONS]
```

### Fetch All Page Links

```bash
python src/fetch_all_links.py [OPTIONS]
```

## Output Format

### JSON Structure

Each scraped page now includes both raw wikitext and cleaned Markdown:

```json
{
  "total_scraped": 10,
  "scraped_at": "2026-01-13 10:30:00",
  "pages": [
    {
      "name": "Page Title",
      "title": "Page Title",
      "text": "{{Infobox...}}\n==Introduction==\nRaw wikitext...",
      "cleaned_text": "**Summary:** ...\n\n## Introduction\nCleaned markdown...",
      "exists": true,
      "redirect": false,
      "revision": 12345,
      "categories": ["Category1", "Category2"],
      "links": ["Link1", "Link2"]
    }
  ]
}
```

### Cleaned Markdown File Format

```markdown
================================================================================
# Page Title
================================================================================

**Summary:** key1: value1; key2: value2.

## Introduction
The page content in clean Markdown format...

### Subsection
More content with proper links and formatting.
```

### Text Format (Raw Wikitext)

```
================================================================================
Page: Page Title
================================================================================

{{Infobox university
| name = Page Title
}}

==Introduction==
The '''Page''' with [[links]] and templates.
```

## Dependencies

- Python 3.13+
- mwclient 0.11.0 - MediaWiki API client
- mwparserfromhell 0.7.2 - Wikitext parser
- beautifulsoup4 4.14.3 - HTML parsing
- requests 2.32.5 - HTTP library
- psycopg2-binary 2.9.11 - PostgreSQL adapter
- python-dotenv 1.2.1 - Environment variables

All dependencies are installed via:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

## Additional Documentation

- `DATABASE_UPLOAD.md` - Database integration guide
- `WIKITEXT_CLEANING.md` - Wikitext cleaning documentation
- `QUICK_START.md` - Quick reference guide
- `SCRAPER_README.md` - Detailed technical documentation
- `UPDATE_NOTES.md` - Flag system changes
- `BATCH_FILES_FEATURE.md` - Batch processing details

## Current Status

- All 3,583 page links fetched and saved
- Concurrent scraper tested and working
- Batch processing tested with 5, 10, 25 pages per batch
- Performance validated: ~0.36-0.40 seconds/page
- Full project structure organized

## Next Steps

1. **Activate environment:**
   ```bash
   source venv/bin/activate
   ```

2. **Run a quick test:**
   ```bash
   python src/main.py results/all_pages.json --limit 10
   ```

3. **Check the output:**
   ```bash
   cat results/scraped_data/scraped_pages.json
   ```

4. **Run full scrape:**
   ```bash
   python src/main.py results/all_pages.json --pages 50 --threads 8
   ```

## License

This is a scraper tool for MetaKGP Wiki. Please respect the wiki's terms of service and rate limits.
