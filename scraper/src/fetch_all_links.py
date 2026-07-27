#!/usr/bin/env python3
"""
Fetch all page links from MetaKGP Wiki's Special:AllPages
Saves the complete list of page titles to a JSON file
Default output location: ./results/
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from typing import List, Optional


class AllPagesFetcher:
    """Fetches all page links from Special:AllPages"""
    
    def __init__(self, base_url: str = "https://wiki.metakgp.org"):
        self.base_url = base_url
        self.all_pages_url = f"{base_url}/w/Special:AllPages"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'MetaKGP Wiki Scraper Bot/1.0'
        })
    
    def extract_page_links(self, html: str) -> List[str]:
        """Extract page titles from the AllPages HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        page_titles = []
        
        # Find all page links in the mw-allpages-chunk list
        chunk_list = soup.find('ul', class_='mw-allpages-chunk')
        if chunk_list:
            for link in chunk_list.find_all('a'):
                title = link.get('title')
                if title:
                    page_titles.append(title)
        
        return page_titles
    
    def extract_next_page_link(self, html: str) -> Optional[str]:
        """Extract the 'Next page' link from the AllPages navigation"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find navigation div
        nav_div = soup.find('div', class_='mw-allpages-nav')
        if nav_div:
            next_link = nav_div.find('a', string=re.compile(r'Next page'))
            if next_link:
                href = next_link.get('href')
                if href:
                    return urljoin(self.base_url, href)
        
        return None
    
    def fetch_all_pages(self) -> List[str]:
        """
        Fetch all page titles by following 'Next page' links
        Returns a list of all page titles
        """
        all_titles = []
        current_url = self.all_pages_url
        page_count = 0
        
        print("Starting to fetch all page links from Special:AllPages...")
        print(f"Initial URL: {current_url}\n")
        
        while current_url:
            page_count += 1
            print(f"Fetching page {page_count}... ", end='', flush=True)
            
            try:
                response = self.session.get(current_url, timeout=30)
                response.raise_for_status()
                
                # Extract page titles from current page
                titles = self.extract_page_links(response.text)
                all_titles.extend(titles)
                print(f"Found {len(titles)} pages (Total: {len(all_titles)})")
                
                # Find next page link
                next_url = self.extract_next_page_link(response.text)
                
                if next_url:
                    # Extract the 'from' parameter to show progress
                    parsed = urlparse(next_url)
                    params = parse_qs(parsed.query)
                    from_param = params.get('from', [''])[0]
                    if from_param:
                        print(f"  → Next starting from: {from_param}")
                    current_url = next_url
                    time.sleep(0.5)  # Be nice to the server
                else:
                    print("\n✓ Reached the end of all pages!")
                    current_url = None
                    
            except requests.RequestException as e:
                print(f"\n✗ Error fetching {current_url}: {e}")
                break
        
        print(f"\n{'='*70}")
        print(f"Total pages fetched: {len(all_titles)}")
        print(f"Total AllPages pagination pages visited: {page_count}")
        print(f"{'='*70}")
        
        return all_titles
    
    def save_to_json(self, titles: List[str], filename: str = "all_pages.json", output_dir: str = "./results"):
        """Save page titles to JSON file
        
        Args:
            titles: List of page titles
            filename: Output filename
            output_dir: Output directory path (default: ./results)
        """
        # Create output directory if it doesn't exist
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        full_path = output_path / filename
        
        data = {
            "total_pages": len(titles),
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pages": titles
        }
        
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Saved {len(titles)} page titles to {full_path}")
    
    def save_to_text(self, titles: List[str], filename: str = "all_pages.txt", output_dir: str = "./results"):
        """Save page titles to text file (one per line)
        
        Args:
            titles: List of page titles
            filename: Output filename
            output_dir: Output directory path (default: ./results)
        """
        # Create output directory if it doesn't exist
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        full_path = output_path / filename
        
        with open(full_path, 'w', encoding='utf-8') as f:
            for title in titles:
                f.write(f"{title}\n")
        
        print(f"✓ Saved {len(titles)} page titles to {full_path}")


def main():
    """Main function - saves to ./results directory by default"""
    fetcher = AllPagesFetcher()
    
    # Fetch all page links
    all_titles = fetcher.fetch_all_pages()
    
    if all_titles:
        # Save to ./results directory
        fetcher.save_to_json(all_titles)
        fetcher.save_to_text(all_titles)
        
        # Show some sample titles
        print("\n" + "="*70)
        print("Sample page titles (first 10):")
        print("="*70)
        for i, title in enumerate(all_titles[:10], 1):
            print(f"{i}. {title}")
        
        if len(all_titles) > 10:
            print("\n...")
            print("\nLast 5 page titles:")
            for i, title in enumerate(all_titles[-5:], len(all_titles) - 4):
                print(f"{i}. {title}")


if __name__ == "__main__":
    main()
