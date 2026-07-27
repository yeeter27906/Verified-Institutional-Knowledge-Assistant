#!/usr/bin/env python3
"""
Database Uploader Module
Handles uploading scraped wiki pages to PostgreSQL database
"""

import psycopg2
from psycopg2.extras import execute_batch
from typing import List, Dict, Optional
import os
from pathlib import Path
from dotenv import load_dotenv


class DatabaseUploader:
    """Handles database operations for wiki pages"""
    
    def __init__(self, env_path: Optional[str] = None):
        """
        Initialize database connection
        
        Args:
            env_path: Path to .env file (default: looks in team_2 root)
        """
        # Load environment variables
        if env_path:
            load_dotenv(env_path)
        else:
            # Try to find .env in team_2 root directory
            current_dir = Path(__file__).resolve().parent
            team_2_root = current_dir.parent.parent
            env_file = team_2_root / '.env'
            if env_file.exists():
                load_dotenv(env_file)
            else:
                raise FileNotFoundError(
                    f"No .env file found at {env_file}. "
                    "Please create one with database credentials."
                )
        
        # Get database credentials from environment
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD')
        }
        
        # Validate required fields
        if not all([self.db_config['database'], self.db_config['user'], self.db_config['password']]):
            raise ValueError(
                "Missing required database credentials in .env file. "
                "Required: DB_NAME, DB_USER, DB_PASSWORD"
            )
        
        self.conn = None
        self.cursor = None
    
    def connect(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(**self.db_config)
            self.cursor = self.conn.cursor()
            print(f"✓ Connected to database: {self.db_config['database']}")
        except psycopg2.Error as e:
            print(f"✗ Database connection failed: {e}")
            raise
    
    def disconnect(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
            print("✓ Database connection closed")
    
    def upsert_page(self, page_data: Dict) -> bool:
        """
        Insert or update a single page
        
        Args:
            page_data: Dictionary containing page data
            
        Returns:
            True if successful, False otherwise
        """
        upsert_sql = """
        INSERT INTO metakgp_pages (
            name, title, text, cleaned_text, exists, redirect, 
            revision, categories, links
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (name) 
        DO UPDATE SET
            title = EXCLUDED.title,
            text = EXCLUDED.text,
            cleaned_text = EXCLUDED.cleaned_text,
            exists = EXCLUDED.exists,
            redirect = EXCLUDED.redirect,
            revision = EXCLUDED.revision,
            categories = EXCLUDED.categories,
            links = EXCLUDED.links,
            updated_at = CURRENT_TIMESTAMP
        """
        
        try:
            self.cursor.execute(upsert_sql, (
                page_data['name'],
                page_data['title'],
                page_data['text'],
                page_data.get('cleaned_text', ''),
                page_data.get('exists', True),
                page_data.get('redirect', False),
                page_data.get('revision'),
                page_data.get('categories', []),
                page_data.get('links', [])
            ))
            return True
        except psycopg2.Error as e:
            print(f"✗ Error upserting page '{page_data.get('name', 'unknown')}': {e}")
            return False
    
    def upsert_pages_batch(self, pages: List[Dict], batch_size: int = 500) -> tuple:
        """
        Insert or update multiple pages in batches
        
        Args:
            pages: List of page data dictionaries
            batch_size: Number of records to insert per batch (default: 500)
            
        Returns:
            Tuple of (successful_count, failed_count)
        """
        upsert_sql = """
        INSERT INTO metakgp_pages (
            name, title, text, cleaned_text, exists, redirect, 
            revision, categories, links
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (name) 
        DO UPDATE SET
            title = EXCLUDED.title,
            text = EXCLUDED.text,
            cleaned_text = EXCLUDED.cleaned_text,
            exists = EXCLUDED.exists,
            redirect = EXCLUDED.redirect,
            revision = EXCLUDED.revision,
            categories = EXCLUDED.categories,
            links = EXCLUDED.links,
            updated_at = CURRENT_TIMESTAMP
        """
        
        successful = 0
        failed = 0
        total = len(pages)
        
        print(f"\nUploading {total} pages to database...")
        
        # Process in batches
        for i in range(0, total, batch_size):
            batch = pages[i:i + batch_size]
            batch_data = []
            
            for page in batch:
                batch_data.append((
                    page['name'],
                    page['title'],
                    page['text'],
                    page.get('cleaned_text', ''),
                    page.get('exists', True),
                    page.get('redirect', False),
                    page.get('revision'),
                    page.get('categories', []),
                    page.get('links', [])
                ))
            
            try:
                execute_batch(self.cursor, upsert_sql, batch_data)
                self.conn.commit()
                successful += len(batch)
                print(f"  [{successful}/{total}] Uploaded batch {i//batch_size + 1}")
            except psycopg2.Error as e:
                self.conn.rollback()
                print(f"  ✗ Batch {i//batch_size + 1} failed: {e}")
                failed += len(batch)
        
        return successful, failed
    
    def upload_pages(self, pages: List[Dict]) -> tuple:
        """
        Main method to upload pages to database
        
        Args:
            pages: List of page data dictionaries
            
        Returns:
            Tuple of (successful_count, failed_count)
        """
        if not pages:
            print("No pages to upload")
            return 0, 0
        
        print(f"\n{'='*70}")
        print(f"Starting database upload")
        print(f"{'='*70}")
        
        try:
            self.connect()
            
            successful, failed = self.upsert_pages_batch(pages)
            
            print(f"\n{'='*70}")
            print(f"Database Upload Complete!")
            print(f"{'='*70}")
            print(f"Successfully uploaded: {successful}")
            print(f"Failed: {failed}")
            print(f"{'='*70}\n")
            
            return successful, failed
            
        except Exception as e:
            print(f"\n✗ Database upload error: {e}")
            return 0, len(pages)
        finally:
            self.disconnect()
    
    def get_page_count(self) -> int:
        """Get total number of pages in database"""
        try:
            self.cursor.execute("SELECT COUNT(*) FROM metakgp_pages")
            count = self.cursor.fetchone()[0]
            return count
        except psycopg2.Error as e:
            print(f"✗ Error getting page count: {e}")
            return 0
    
    def get_latest_revision(self, page_name: str) -> Optional[int]:
        """Get the latest revision number for a page"""
        try:
            self.cursor.execute(
                "SELECT revision FROM metakgp_pages WHERE name = %s",
                (page_name,)
            )
            result = self.cursor.fetchone()
            return result[0] if result else None
        except psycopg2.Error as e:
            print(f"✗ Error getting revision for '{page_name}': {e}")
            return None


def test_connection(env_path: Optional[str] = None):
    """Test database connection"""
    try:
        uploader = DatabaseUploader(env_path)
        uploader.connect()
        print("✓ Database connection test successful!")
        uploader.disconnect()
        return True
    except Exception as e:
        print(f"✗ Database connection test failed: {e}")
        return False


if __name__ == "__main__":
    # Test the database connection
    print("Testing database connection...")
    test_connection()
