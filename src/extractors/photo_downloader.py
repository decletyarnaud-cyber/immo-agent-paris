"""
Photo downloader for auction listings
Downloads and stores photos locally for offline viewing
"""
import os
import hashlib
import requests
from pathlib import Path
from typing import List, Optional, Dict
from urllib.parse import urlparse, urljoin
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed


class PhotoDownloader:
    """
    Downloads and manages photos for auction listings

    Features:
    - Downloads photos from URLs
    - Deduplicates by content hash
    - Organizes by auction ID
    - Supports multiple image formats
    - Concurrent downloads for speed
    """

    SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}

    def __init__(self, photos_dir: Optional[Path] = None):
        """
        Initialize photo downloader

        Args:
            photos_dir: Directory to store photos (defaults to data/photos)
        """
        self.photos_dir = photos_dir or Path(__file__).parent.parent.parent / "data" / "photos"
        self.photos_dir.mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    def _get_extension(self, url: str, content_type: Optional[str] = None) -> str:
        """Determine file extension from URL or content type"""
        # Try from URL
        parsed = urlparse(url)
        path = parsed.path.lower()
        for ext in self.SUPPORTED_EXTENSIONS:
            if path.endswith(ext):
                return ext

        # Try from content type
        if content_type:
            content_map = {
                'image/jpeg': '.jpg',
                'image/jpg': '.jpg',
                'image/png': '.png',
                'image/gif': '.gif',
                'image/webp': '.webp',
                'image/bmp': '.bmp',
            }
            for ct, ext in content_map.items():
                if ct in content_type.lower():
                    return ext

        return '.jpg'  # Default

    def _get_content_hash(self, content: bytes) -> str:
        """Generate hash of image content for deduplication"""
        return hashlib.md5(content).hexdigest()

    def _normalize_url(self, url: str, base_url: Optional[str] = None) -> str:
        """Normalize and complete URL"""
        if not url:
            return ""

        # Already absolute
        if url.startswith(('http://', 'https://')):
            return url

        # Protocol-relative
        if url.startswith('//'):
            return f"https:{url}"

        # Relative URL - need base
        if base_url:
            return urljoin(base_url, url)

        return url

    def download_photo(self, url: str, auction_id: int, base_url: Optional[str] = None) -> Optional[str]:
        """
        Download a single photo

        Args:
            url: Photo URL
            auction_id: Auction ID for organization
            base_url: Base URL for relative URLs

        Returns:
            Local file path if successful, None otherwise
        """
        url = self._normalize_url(url, base_url)
        if not url:
            return None

        try:
            response = self.session.get(url, timeout=30, stream=True)
            response.raise_for_status()

            content = response.content
            if len(content) < 1000:  # Skip tiny images (likely placeholders)
                logger.debug(f"[PhotoDownloader] Skipping small image: {url}")
                return None

            # Get extension and hash
            content_type = response.headers.get('Content-Type', '')
            ext = self._get_extension(url, content_type)
            content_hash = self._get_content_hash(content)

            # Create auction directory
            auction_dir = self.photos_dir / str(auction_id)
            auction_dir.mkdir(exist_ok=True)

            # Check for duplicates
            for existing in auction_dir.glob(f"*{ext}"):
                with open(existing, 'rb') as f:
                    if self._get_content_hash(f.read()) == content_hash:
                        logger.debug(f"[PhotoDownloader] Duplicate skipped: {url}")
                        return str(existing)

            # Save new photo
            filename = f"{content_hash[:12]}{ext}"
            filepath = auction_dir / filename

            with open(filepath, 'wb') as f:
                f.write(content)

            logger.debug(f"[PhotoDownloader] Downloaded: {filepath.name}")
            return str(filepath)

        except requests.RequestException as e:
            logger.warning(f"[PhotoDownloader] Download failed for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"[PhotoDownloader] Error downloading {url}: {e}")
            return None

    def download_photos(
        self,
        urls: List[str],
        auction_id: int,
        base_url: Optional[str] = None,
        max_photos: int = 20,
        max_workers: int = 4
    ) -> List[str]:
        """
        Download multiple photos concurrently

        Args:
            urls: List of photo URLs
            auction_id: Auction ID
            base_url: Base URL for relative URLs
            max_photos: Maximum number of photos to download
            max_workers: Number of concurrent downloads

        Returns:
            List of local file paths for successfully downloaded photos
        """
        if not urls:
            return []

        # Limit and deduplicate URLs
        unique_urls = list(dict.fromkeys(urls))[:max_photos]
        local_paths = []

        logger.info(f"[PhotoDownloader] Downloading {len(unique_urls)} photos for auction {auction_id}")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(self.download_photo, url, auction_id, base_url): url
                for url in unique_urls
            }

            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    if result:
                        local_paths.append(result)
                except Exception as e:
                    logger.warning(f"[PhotoDownloader] Failed to download {url}: {e}")

        logger.info(f"[PhotoDownloader] Downloaded {len(local_paths)}/{len(unique_urls)} photos")
        return local_paths

    def get_auction_photos(self, auction_id: int) -> List[str]:
        """
        Get list of local photo paths for an auction

        Args:
            auction_id: Auction ID

        Returns:
            List of local file paths
        """
        auction_dir = self.photos_dir / str(auction_id)
        if not auction_dir.exists():
            return []

        photos = []
        for ext in self.SUPPORTED_EXTENSIONS:
            photos.extend(str(p) for p in auction_dir.glob(f"*{ext}"))

        return sorted(photos)

    def delete_auction_photos(self, auction_id: int) -> int:
        """
        Delete all photos for an auction

        Args:
            auction_id: Auction ID

        Returns:
            Number of photos deleted
        """
        auction_dir = self.photos_dir / str(auction_id)
        if not auction_dir.exists():
            return 0

        count = 0
        for photo in auction_dir.iterdir():
            photo.unlink()
            count += 1

        auction_dir.rmdir()
        logger.info(f"[PhotoDownloader] Deleted {count} photos for auction {auction_id}")
        return count

    def get_storage_stats(self) -> Dict[str, any]:
        """Get storage statistics"""
        total_size = 0
        total_photos = 0
        auctions_with_photos = 0

        for auction_dir in self.photos_dir.iterdir():
            if auction_dir.is_dir():
                photos = list(auction_dir.iterdir())
                if photos:
                    auctions_with_photos += 1
                    total_photos += len(photos)
                    total_size += sum(p.stat().st_size for p in photos)

        return {
            'total_photos': total_photos,
            'auctions_with_photos': auctions_with_photos,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'photos_dir': str(self.photos_dir)
        }


# Convenience function
def download_auction_photos(urls: List[str], auction_id: int, base_url: Optional[str] = None) -> List[str]:
    """Quick download of auction photos"""
    downloader = PhotoDownloader()
    return downloader.download_photos(urls, auction_id, base_url)
