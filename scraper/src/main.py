#!/usr/bin/env python3
"""
Concurrent Wiki Page Scraper
Reads page links from JSON file and fetches multiple pages in parallel using 4 threads
"""

import json
import argparse
import mwclient
import time
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import sys
from wikitext_cleaner import WikitextCleaner
from database_uploader import DatabaseUploader


class ConcurrentWikiScraper:
    """Scrapes multiple wiki pages concurrently using thread pool"""
    
    def __init__(self, max_workers: int = 4, output_dir: str = "results/scraped_data"):
        """
        Initialize concurrent scraper
        
        Args:
            max_workers: Number of parallel threads (default: 4)
            output_dir: Directory to save scraped data (relative to current working directory)
        """
        self.max_workers = max_workers
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Thread-safe counter and lock for progress tracking
        self.completed = 0
        self.failed = 0
        self.lock = Lock()
        
        # Initialize wiki connection (thread-safe)
        self.site = mwclient.Site('wiki.metakgp.org', path='/')
        
        # Initialize wikitext cleaner
        self.cleaner = WikitextCleaner()
    
    def fetch_page(self, page_name: str, index: int, total: int) -> Optional[Dict]:
        """
        Fetch a single page (thread-safe)
        
        Args:
            page_name: Name of the wiki page
            index: Current page index
            total: Total pages to fetch
            
        Returns:
            Dictionary containing page data or None if failed
        """
        try:
            page = self.site.pages[page_name]
            
            if not page.exists:
                with self.lock:
                    self.failed += 1
                    print(f"[{index}/{total}] ✗ Page '{page_name}' does not exist")
                return None
            
            # Fetch raw wikitext
            raw_text = page.text()
            
            # Clean the wikitext to readable Markdown
            cleaned_text = self.cleaner.clean_wikitext(raw_text)
            
            page_data = {
                'name': page.name,
                'title': page.page_title,
                'text': raw_text,  # Keep original for reference
                'cleaned_text': cleaned_text,  # Add cleaned version
                'exists': page.exists,
                'redirect': page.redirect,
                'revision': page.revision,
                'categories': [cat.name for cat in page.categories()],
                'links': [link.name for link in page.links()],
            }
            
            with self.lock:
                self.completed += 1
                print(f"[{index}/{total}] ✓ Scraped: {page_name} (Thread {id(page) % 10000})")
            
            return page_data
            
        except Exception as e:
            with self.lock:
                self.failed += 1
                print(f"[{index}/{total}] ✗ Error fetching '{page_name}': {e}")
            return None
    
    def scrape_pages_concurrent(self, page_names: List[str]) -> List[Dict]:
        """
        Scrape multiple pages concurrently using thread pool
        
        Args:
            page_names: List of page names to scrape
            
        Returns:
            List of successfully scraped page data
        """
        total = len(page_names)
        results = []
        
        print(f"\n{'='*70}")
        print(f"Starting concurrent scrape of {total} pages using {self.max_workers} threads")
        print(f"{'='*70}\n")
        
        start_time = time.time()
        
        # Create thread pool and submit all tasks
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all fetch tasks
            future_to_page = {
                executor.submit(self.fetch_page, page_name, idx + 1, total): page_name
                for idx, page_name in enumerate(page_names)
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_page):
                page_name = future_to_page[future]
                try:
                    page_data = future.result()
                    if page_data:
                        results.append(page_data)
                except Exception as e:
                    with self.lock:
                        self.failed += 1
                        print(f"✗ Exception for '{page_name}': {e}")
        
        elapsed = time.time() - start_time
        
        print(f"\n{'='*70}")
        print(f"Scraping Complete!")
        print(f"{'='*70}")
        print(f"Total pages requested: {total}")
        print(f"Successfully scraped: {self.completed}")
        print(f"Failed: {self.failed}")
        print(f"Time taken: {elapsed:.2f} seconds")
        print(f"Average: {elapsed/total:.2f} seconds per page")
        print(f"{'='*70}\n")
        
        return results
    
    def save_to_json(self, data: List[Dict], filename: str):
        """Save scraped data to JSON file"""
        filepath = self.output_dir / filename
        
        output = {
            'total_scraped': len(data),
            'scraped_at': time.strftime("%Y-%m-%d %H:%M:%S"),
            'pages': data
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Saved {len(data)} pages to {filepath}")
    
    def save_to_text(self, data: List[Dict], filename: str):
        """Save scraped data to text file"""
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for page in data:
                f.write(f"{'='*80}\n")
                f.write(f"Page: {page['name']}\n")
                f.write(f"{'='*80}\n\n")
                f.write(page['text'])
                f.write(f"\n\n")
        
        print(f"✓ Saved {len(data)} pages to {filepath}")
    
    def save_cleaned_to_text(self, data: List[Dict], filename: str):
        """Save cleaned text to markdown file"""
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for page in data:
                f.write(f"{'='*80}\n")
                f.write(f"# {page['name']}\n")
                f.write(f"{'='*80}\n\n")
                if 'cleaned_text' in page:
                    f.write(page['cleaned_text'])
                else:
                    f.write(page['text'])
                f.write(f"\n\n")
        
        print(f"✓ Saved {len(data)} cleaned pages to {filepath}")


def load_page_list(json_file: str) -> List[str]:
    """Load page list from JSON file"""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Support different JSON structures
        if isinstance(data, dict):
            pages = data.get('pages', [])
        elif isinstance(data, list):
            pages = data
        else:
            raise ValueError("Invalid JSON format")
        
        return pages
    
    except FileNotFoundError:
        print(f"✗ Error: File '{json_file}' not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON in '{json_file}': {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error loading '{json_file}': {e}")
        sys.exit(1)


def main():
    """Main function with argument parsing"""
    parser = argparse.ArgumentParser(
        description="Concurrent Wiki Page Scraper - Fetch multiple pages in parallel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape first 10 pages (total) using 4 threads (default)
  python src/main.py results/all_pages.json --limit 10
  
  # Scrape 100 pages (total) in batches of 20, using 8 threads per batch
  python src/main.py results/all_pages.json --limit 100 --pages 20 --threads 8
  
  # Scrape all pages from the JSON file with default settings
  python src/main.py results/all_pages.json
  
  # Scrape all 3583 pages in batches of 50, using 4 threads per batch
  python src/main.py results/all_pages.json --pages 50 --threads 4
  
  # Save output with custom filename and also as text
  python src/main.py results/all_pages.json --limit 20 --output my_pages.json --text
  
  # Scrape 200 pages starting from index 100
  python src/main.py results/all_pages.json --limit 200 --start 100
        """
    )
    
    parser.add_argument(
        'json_file',
        help='JSON file containing list of page titles'
    )
    
    parser.add_argument(
        '--pages',
        type=int,
        default=None,
        help='Batch size for parallel processing (default: process all at once)'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Total number of pages to scrape (default: all pages in file)'
    )
    
    parser.add_argument(
        '--threads',
        type=int,
        default=4,
        help='Number of parallel threads (default: 4)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='scraped_pages.json',
        help='Output JSON filename (default: scraped_pages.json)'
    )
    
    parser.add_argument(
        '--text',
        action='store_true',
        help='Also save as text file (raw wikitext)'
    )
    
    parser.add_argument(
        '--database',
        action='store_true',
        help='Upload scraped pages to PostgreSQL database'
    )
    
    parser.add_argument(
        '--start',
        type=int,
        default=0,
        help='Start index in the page list (default: 0)'
    )
    
    args = parser.parse_args()
    
    # Validate threads
    if args.threads < 1 or args.threads > 20:
        print("✗ Error: Number of threads must be between 1 and 20")
        sys.exit(1)
    
    # Load page list from JSON file
    print(f"Loading page list from {args.json_file}...")
    all_pages = load_page_list(args.json_file)
    print(f"✓ Loaded {len(all_pages)} page titles")
    
    # Determine which pages to scrape based on --limit and --start
    start_idx = args.start
    
    if args.limit:
        end_idx = min(start_idx + args.limit, len(all_pages))
        pages_to_scrape = all_pages[start_idx:end_idx]
        print(f"✓ Will scrape pages {start_idx + 1} to {end_idx} ({len(pages_to_scrape)} pages total)")
    else:
        pages_to_scrape = all_pages[start_idx:]
        print(f"✓ Will scrape all pages starting from index {start_idx} ({len(pages_to_scrape)} pages total)")
    
    if not pages_to_scrape:
        print("✗ No pages to scrape!")
        sys.exit(1)
    
    # Initialize scraper with specified number of threads
    scraper = ConcurrentWikiScraper(max_workers=args.threads)
    
    # If --pages is specified, process in batches; otherwise process all at once
    if args.pages and args.pages < len(pages_to_scrape):
        print(f"✓ Processing in batches of {args.pages} pages with {args.threads} threads per batch")
        print(f"✓ Each batch will be saved to a separate file\n")
        
        all_results = []
        total_pages = len(pages_to_scrape)
        batch_number = 1
        saved_files = []
        
        for batch_start in range(0, total_pages, args.pages):
            batch_end = min(batch_start + args.pages, total_pages)
            batch = pages_to_scrape[batch_start:batch_end]
            
            print(f"\n{'='*70}")
            print(f"Batch {batch_number}: Processing pages {batch_start + 1} to {batch_end} of {total_pages}")
            print(f"{'='*70}")
            
            # Reset counters for this batch
            scraper.completed = 0
            scraper.failed = 0
            
            batch_results = scraper.scrape_pages_concurrent(batch)
            all_results.extend(batch_results)
            
            print(f"✓ Batch complete: {len(batch_results)} pages scraped")
            
            # Save this batch to a separate file
            if batch_results:
                # Generate filename for this batch
                base_name = args.output.replace('.json', '')
                batch_filename = f"{base_name}_batch{batch_number}.json"
                scraper.save_to_json(batch_results, batch_filename)
                saved_files.append(batch_filename)
                
                # Save raw text file if requested
                if args.text:
                    text_filename = f"{base_name}_batch{batch_number}.txt"
                    scraper.save_to_text(batch_results, text_filename)
                    saved_files.append(text_filename)
            
            batch_number += 1
            
            # Small delay between batches to be nice to the server
            if batch_end < total_pages:
                time.sleep(1)
        
        results = all_results
        print(f"\n{'='*70}")
        print(f"All Batches Complete!")
        print(f"Total pages scraped: {len(results)} out of {total_pages}")
        print(f"Total files created: {len(saved_files)}")
        print(f"{'='*70}\n")
        
        # Print list of saved files
        print("Saved files:")
        for filename in saved_files:
            print(f"  - scraped_data/{filename}")
        print()
        
        # Upload to database if requested
        if args.database and results:
            try:
                uploader = DatabaseUploader()
                successful, failed = uploader.upload_pages(results)
                
                # Delete JSON files after successful upload
                if successful > 0 and failed == 0:
                    print("\n✓ All pages uploaded successfully. Cleaning up JSON files...")
                    deleted_count = 0
                    for filename in saved_files:
                        filepath = scraper.output_dir / filename
                        try:
                            if filepath.exists():
                                filepath.unlink()
                                deleted_count += 1
                                print(f"  ✓ Deleted: {filename}")
                        except Exception as e:
                            print(f"  ✗ Failed to delete {filename}: {e}")
                    print(f"✓ Cleaned up {deleted_count} file(s)")
                else:
                    print(f"\n⚠ Keeping JSON files due to upload errors (failed: {failed})")
            except Exception as e:
                print(f"✗ Database upload failed: {e}")
                print("⚠ Keeping JSON files due to upload failure")
    else:
        # Process all pages at once (no batching)
        results = scraper.scrape_pages_concurrent(pages_to_scrape)
        
        # Save results to single file
        if results:
            scraper.save_to_json(results, args.output)
            saved_json_files = [args.output]
            
            # Save raw text file if requested
            if args.text:
                text_file = args.output.replace('.json', '.txt')
                scraper.save_to_text(results, text_file)
            
            # Upload to database if requested
            if args.database:
                try:
                    uploader = DatabaseUploader()
                    successful, failed = uploader.upload_pages(results)
                    
                    # Delete JSON files after successful upload
                    if successful > 0 and failed == 0:
                        print("\n✓ All pages uploaded successfully. Cleaning up JSON files...")
                        deleted_count = 0
                        for filename in saved_json_files:
                            filepath = scraper.output_dir / filename
                            try:
                                if filepath.exists():
                                    filepath.unlink()
                                    deleted_count += 1
                                    print(f"  ✓ Deleted: {filename}")
                            except Exception as e:
                                print(f"  ✗ Failed to delete {filename}: {e}")
                        print(f"✓ Cleaned up {deleted_count} file(s)")
                    else:
                        print(f"\n⚠ Keeping JSON files due to upload errors (failed: {failed})")
                except Exception as e:
                    print(f"✗ Database upload failed: {e}")
                    print("⚠ Keeping JSON files due to upload failure")
    
    if results:
        # Show sample of scraped data
        print("\nSample scraped pages (first 3):")
        print("="*70)
        for i, page in enumerate(results[:3], 1):
            print(f"{i}. {page['name']}")
            print(f"   Categories: {len(page['categories'])}, Links: {len(page['links'])}")
            print(f"   Content length: {len(page['text'])} characters")
    else:
        print("\n✗ No pages were successfully scraped!")
        sys.exit(1)


if __name__ == "__main__":
    main()
