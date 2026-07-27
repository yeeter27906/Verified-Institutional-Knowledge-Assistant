#!/usr/bin/env python3
"""
Wikitext Cleaner Module
Parses and cleans Wikitext content using mwparserfromhell library
Converts to clean, human-readable Markdown format
"""

import mwparserfromhell
import re
from typing import Dict, List, Tuple


class WikitextCleaner:
    """Cleans and converts Wikitext to readable Markdown format"""
    
    def __init__(self):
        """Initialize the cleaner"""
        pass
    
    def extract_infobox_summary(self, wikicode) -> Tuple[str, mwparserfromhell.wikicode.Wikicode]:
        """
        Extract Infobox templates and convert to human-readable summary paragraph
        
        Args:
            wikicode: Parsed wikicode object
            
        Returns:
            Tuple of (summary_text, wikicode_without_infobox)
        """
        summary_parts = []
        infoboxes_found = []
        
        # Find all Infobox templates
        for template in wikicode.filter_templates():
            template_name = str(template.name).strip().lower()
            
            # Check if it's an infobox (various naming conventions)
            if 'infobox' in template_name:
                infoboxes_found.append(template)
                
                # Extract key-value pairs from the infobox
                infobox_data = []
                for param in template.params:
                    param_name = str(param.name).strip()
                    param_value = str(param.value).strip()
                    
                    # Skip empty values or common metadata fields
                    if not param_value or param_name.lower() in ['image', 'caption', 'alt', 'image_size']:
                        continue
                    
                    # Clean the value (remove nested templates, links, etc.)
                    cleaned_value = self._clean_text(param_value)
                    
                    if cleaned_value:
                        infobox_data.append(f"{param_name}: {cleaned_value}")
                
                # Create summary paragraph
                if infobox_data:
                    summary_parts.append("**Summary:** " + "; ".join(infobox_data) + ".")
        
        # Remove infoboxes from wikicode
        for infobox in infoboxes_found:
            wikicode.remove(infobox)
        
        summary_text = "\n\n".join(summary_parts)
        return summary_text, wikicode
    
    def convert_headers_to_markdown(self, text: str) -> str:
        """
        Convert Wikitext headers to Markdown headers
        
        Examples:
            ==Introduction== -> ## Introduction
            ===Subsection=== -> ### Subsection
            
        Args:
            text: Text with Wikitext headers
            
        Returns:
            Text with Markdown headers
        """
        # Match headers: ==Header== or ===Header=== etc.
        # Count the number of = signs and convert to # signs
        def replace_header(match):
            equals_count = len(match.group(1))
            header_text = match.group(2).strip()
            markdown_level = '#' * equals_count
            return f"{markdown_level} {header_text}"
        
        # Pattern: (==+)(.+?)\1
        # Matches symmetric equals signs around text
        text = re.sub(r'^(={2,})(.*?)\1\s*$', replace_header, text, flags=re.MULTILINE)
        
        return text
    
    def clean_internal_links(self, wikicode) -> mwparserfromhell.wikicode.Wikicode:
        """
        Clean internal wiki links
        
        Examples:
            [[Target|Display]] -> Display
            [[Target]] -> Target
            
        Args:
            wikicode: Parsed wikicode object
            
        Returns:
            Cleaned wikicode
        """
        for wikilink in wikicode.filter_wikilinks():
            # Get the display text if available, otherwise use the target
            if wikilink.text:
                display_text = str(wikilink.text)
            else:
                display_text = str(wikilink.title)
            
            # Replace the wikilink with plain text
            wikicode.replace(wikilink, display_text)
        
        return wikicode
    
    def _clean_text(self, text: str) -> str:
        """
        Helper method to clean nested wiki markup from text
        
        Args:
            text: Text to clean
            
        Returns:
            Cleaned text
        """
        try:
            # Parse the text
            wikicode = mwparserfromhell.parse(text)
            
            # Remove templates
            for template in wikicode.filter_templates():
                wikicode.remove(template)
            
            # Clean links
            for wikilink in wikicode.filter_wikilinks():
                if wikilink.text:
                    wikicode.replace(wikilink, str(wikilink.text))
                else:
                    wikicode.replace(wikilink, str(wikilink.title))
            
            # Get plain text
            cleaned = wikicode.strip_code()
            
            # Remove extra whitespace
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            
            return cleaned
        except:
            # Fallback: basic cleaning
            cleaned = re.sub(r'\{\{[^}]+\}\}', '', text)  # Remove templates
            cleaned = re.sub(r'\[\[([^|\]]+\|)?([^\]]+)\]\]', r'\2', cleaned)  # Clean links
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            return cleaned
    
    def remove_templates(self, wikicode, keep_content: bool = True) -> mwparserfromhell.wikicode.Wikicode:
        """
        Remove wiki templates (except infoboxes which are handled separately)
        
        Args:
            wikicode: Parsed wikicode object
            keep_content: If True, try to preserve readable content from templates
            
        Returns:
            Cleaned wikicode
        """
        templates_to_remove = []
        
        for template in wikicode.filter_templates():
            template_name = str(template.name).strip().lower()
            
            # Skip infoboxes (handled separately)
            if 'infobox' in template_name:
                continue
            
            templates_to_remove.append(template)
        
        # Remove templates
        for template in templates_to_remove:
            if keep_content:
                # Try to extract readable content from template
                try:
                    # For cite templates, extract the title or content
                    if 'cite' in str(template.name).lower():
                        for param in template.params:
                            if 'title' in str(param.name).lower():
                                content = str(param.value).strip()
                                if content:
                                    wikicode.replace(template, content)
                                    continue
                    wikicode.remove(template)
                except:
                    wikicode.remove(template)
            else:
                wikicode.remove(template)
        
        return wikicode
    
    def clean_wikitext(self, wikitext: str) -> str:
        """
        Main cleaning function - converts Wikitext to clean Markdown
        
        Process:
        1. Parse Wikitext using mwparserfromhell
        2. Extract and convert Infoboxes to summary paragraph
        3. Clean internal links
        4. Remove other templates
        5. Convert headers to Markdown
        6. Final text cleanup
        
        Args:
            wikitext: Raw Wikitext content
            
        Returns:
            Cleaned Markdown text
        """
        if not wikitext or not wikitext.strip():
            return ""
        
        try:
            # Parse the wikitext
            wikicode = mwparserfromhell.parse(wikitext)
            
            # Step 1: Extract infobox and create summary
            infobox_summary, wikicode = self.extract_infobox_summary(wikicode)
            
            # Step 2: Clean internal links
            wikicode = self.clean_internal_links(wikicode)
            
            # Step 3: Remove other templates
            wikicode = self.remove_templates(wikicode, keep_content=True)
            
            # Convert to string
            text = str(wikicode)
            
            # Step 4: Convert headers to Markdown
            text = self.convert_headers_to_markdown(text)
            
            # Step 5: Clean up external links (keep URL)
            text = re.sub(r'\[([^\s\]]+)\s+([^\]]+)\]', r'[\2](\1)', text)
            
            # Step 6: Remove HTML comments
            text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
            
            # Step 7: Clean up references/citations markup
            text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL)
            text = re.sub(r'<ref[^>]*/?>', '', text)
            
            # Step 8: Clean up excessive whitespace
            text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 newlines
            text = re.sub(r' +', ' ', text)  # Multiple spaces to single space
            text = text.strip()
            
            # Step 9: Add infobox summary at the beginning if it exists
            if infobox_summary:
                text = infobox_summary + "\n\n" + text
            
            return text
            
        except Exception as e:
            # If parsing fails, return original text with basic cleaning
            print(f"Warning: Failed to parse wikitext: {e}")
            text = wikitext
            text = self.convert_headers_to_markdown(text)
            text = re.sub(r'\[\[([^|\]]+\|)?([^\]]+)\]\]', r'\2', text)
            return text
    
    def clean_page_data(self, page_data: Dict) -> Dict:
        """
        Clean page data dictionary - adds cleaned_text field
        
        Args:
            page_data: Dictionary containing page data with 'text' field
            
        Returns:
            Updated dictionary with 'cleaned_text' field added
        """
        if 'text' in page_data:
            page_data['cleaned_text'] = self.clean_wikitext(page_data['text'])
        else:
            page_data['cleaned_text'] = ""
        
        return page_data


def clean_scraped_results(scraped_data: List[Dict]) -> List[Dict]:
    """
    Clean a list of scraped page data
    
    Args:
        scraped_data: List of page data dictionaries
        
    Returns:
        List of cleaned page data dictionaries
    """
    cleaner = WikitextCleaner()
    cleaned_results = []
    
    for page_data in scraped_data:
        cleaned_page = cleaner.clean_page_data(page_data)
        cleaned_results.append(cleaned_page)
    
    return cleaned_results


# Example usage
if __name__ == "__main__":
    # Test the cleaner with sample wikitext
    sample_wikitext = """
{{Infobox university
| name = Indian Institute of Technology Kharagpur
| established = 1951
| type = Public
| location = Kharagpur, West Bengal, India
}}

==Introduction==
The '''Indian Institute of Technology Kharagpur''' ('''IIT Kharagpur''' or '''IIT KGP''') is a public technical university established by the government of India in [[Kharagpur]], [[West Bengal]], India.

===History===
It was established in 1951 and is the first of the [[IIT]]s to be established.

==Campus==
The campus is spread over {{convert|2100|acre|km2}}.

See also [[IIT Bombay]] and [[IIT Delhi|Delhi]] for more information.
"""
    
    cleaner = WikitextCleaner()
    cleaned = cleaner.clean_wikitext(sample_wikitext)
    
    print("Original Wikitext:")
    print("=" * 70)
    print(sample_wikitext)
    print("\n" + "=" * 70)
    print("\nCleaned Markdown:")
    print("=" * 70)
    print(cleaned)
