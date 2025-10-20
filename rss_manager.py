"""
RSS Feed Manager for podcast downloads.
Handles parsing RSS feeds and downloading podcast audio files.
"""

import feedparser
import requests
from typing import Optional, Dict, Any, List
from pathlib import Path
from fuzzywuzzy import fuzz
import json


class RSSManager:
    """Manages podcast RSS feeds and audio downloads."""

    # Common podcast RSS feeds database
    # Users can add more via config or manual entry
    KNOWN_RSS_FEEDS = {
        'Acquired': 'https://feeds.transistor.fm/acquired',
        'The Daily': 'https://feeds.simplecast.com/54nAGcIl',
        'Lex Fridman Podcast': 'https://lexfridman.com/feed/podcast/',
        'All-In Podcast': 'https://feeds.megaphone.fm/ESP8188164312',
        'My First Million': 'https://feeds.megaphone.fm/mfm',
        'How I Built This': 'https://feeds.npr.org/510313/podcast.xml',
        'The Tim Ferriss Show': 'https://tim.blog/category/podcast/feed/',
        'Huberman Lab': 'https://feeds.megaphone.fm/hubermanlab',
    }

    def __init__(self, download_dir: Optional[Path] = None, custom_feeds_file: Optional[Path] = None):
        """
        Initialize RSS manager.

        Args:
            download_dir: Directory to save downloaded audio files
            custom_feeds_file: Path to JSON file with custom RSS feeds
        """
        self.download_dir = download_dir or Path(__file__).parent / "podcast_audio"
        self.download_dir.mkdir(exist_ok=True)

        # Load custom feeds if provided
        self.rss_feeds = dict(self.KNOWN_RSS_FEEDS)
        if custom_feeds_file and custom_feeds_file.exists():
            self._load_custom_feeds(custom_feeds_file)

    def _load_custom_feeds(self, filepath: Path):
        """Load custom RSS feeds from JSON file."""
        try:
            with open(filepath, 'r') as f:
                custom_feeds = json.load(f)
                self.rss_feeds.update(custom_feeds)
                print(f"Loaded {len(custom_feeds)} custom RSS feeds")
        except Exception as e:
            print(f"Warning: Could not load custom feeds: {e}")

    def find_rss_feed(self, show_name: str) -> Optional[str]:
        """
        Find RSS feed URL for a podcast show.

        Args:
            show_name: Name of the podcast show

        Returns:
            RSS feed URL or None
        """
        # Try exact match first
        if show_name in self.rss_feeds:
            return self.rss_feeds[show_name]

        # Try fuzzy match
        best_match = None
        best_score = 0

        for known_show, rss_url in self.rss_feeds.items():
            score = fuzz.ratio(show_name.lower(), known_show.lower())
            if score > best_score:
                best_score = score
                best_match = rss_url

        # Return if confidence is high enough
        if best_score > 80:
            return best_match

        return None

    def parse_feed(self, rss_url: str) -> Optional[feedparser.FeedParserDict]:
        """
        Parse an RSS feed.

        Args:
            rss_url: URL of the RSS feed

        Returns:
            Parsed feed or None
        """
        try:
            print(f"Parsing RSS feed: {rss_url}")
            feed = feedparser.parse(rss_url)

            if feed.bozo:  # Feed has errors
                print(f"Warning: Feed may have parsing errors")

            return feed
        except Exception as e:
            print(f"Error parsing feed: {e}")
            return None

    def find_episode_in_feed(self, feed: feedparser.FeedParserDict,
                            episode_title: str) -> Optional[Dict[str, Any]]:
        """
        Find a specific episode in the feed by title.

        Args:
            feed: Parsed RSS feed
            episode_title: Title of the episode to find

        Returns:
            Episode info or None
        """
        if not feed or not feed.entries:
            return None

        best_match = None
        best_score = 0

        for entry in feed.entries:
            entry_title = entry.get('title', '')
            score = fuzz.ratio(episode_title.lower(), entry_title.lower())

            if score > best_score:
                best_score = score
                best_match = entry

        # Return if confidence is high enough
        if best_score > 70:
            return {
                'title': best_match.get('title'),
                'audio_url': self._get_audio_url(best_match),
                'published': best_match.get('published'),
                'description': best_match.get('summary', ''),
                'match_score': best_score
            }

        return None

    def _get_audio_url(self, entry) -> Optional[str]:
        """Extract audio URL from RSS entry."""
        # Try enclosures first (most common)
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enclosure in entry.enclosures:
                if enclosure.get('type', '').startswith('audio/'):
                    return enclosure.get('href') or enclosure.get('url')

        # Try links
        if hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('type', '').startswith('audio/'):
                    return link.get('href')

        return None

    def download_episode(self, audio_url: str, filename: Optional[str] = None) -> Optional[Path]:
        """
        Download podcast episode audio file.

        Args:
            audio_url: URL of the audio file
            filename: Optional custom filename (will sanitize)

        Returns:
            Path to downloaded file or None
        """
        if not audio_url:
            print("No audio URL provided")
            return None

        try:
            # Generate filename
            if not filename:
                filename = audio_url.split('/')[-1].split('?')[0]

            # Sanitize filename
            filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip()
            if not filename.endswith('.mp3'):
                filename += '.mp3'

            filepath = self.download_dir / filename

            # Check if already downloaded
            if filepath.exists():
                print(f"File already exists: {filepath}")
                return filepath

            # Download
            print(f"Downloading: {audio_url}")
            response = requests.get(audio_url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Progress indicator
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"Progress: {percent:.1f}%", end='\r')

            print(f"\n✓ Downloaded: {filepath}")
            return filepath

        except Exception as e:
            print(f"Error downloading episode: {e}")
            return None

    def find_and_download_episode(self, show_name: str, episode_title: str) -> Optional[Path]:
        """
        Find and download a podcast episode.

        Args:
            show_name: Name of the podcast show
            episode_title: Title of the episode

        Returns:
            Path to downloaded file or None
        """
        # Find RSS feed
        rss_url = self.find_rss_feed(show_name)
        if not rss_url:
            print(f"Could not find RSS feed for: {show_name}")
            print("Available shows:", ", ".join(self.rss_feeds.keys()))
            return None

        print(f"Found RSS feed for {show_name}")

        # Parse feed
        feed = self.parse_feed(rss_url)
        if not feed:
            return None

        # Find episode
        episode = self.find_episode_in_feed(feed, episode_title)
        if not episode:
            print(f"Could not find episode: {episode_title}")
            print(f"Recent episodes:")
            for i, entry in enumerate(feed.entries[:5]):
                print(f"  {i+1}. {entry.get('title', 'Unknown')}")
            return None

        print(f"Found episode: {episode['title']} (match: {episode['match_score']}%)")

        # Download
        return self.download_episode(episode['audio_url'], f"{show_name}_{episode_title}.mp3")

    def add_custom_feed(self, show_name: str, rss_url: str):
        """Add a custom RSS feed to the database."""
        self.rss_feeds[show_name] = rss_url
        print(f"Added RSS feed for: {show_name}")


# Test function
def test_rss_manager():
    """Test the RSS manager."""
    manager = RSSManager()

    # Test finding feed
    rss_url = manager.find_rss_feed("Acquired")
    print(f"RSS URL: {rss_url}")

    # Test parsing feed
    feed = manager.parse_feed(rss_url)
    if feed:
        print(f"\nPodcast: {feed.feed.get('title')}")
        print(f"Episodes found: {len(feed.entries)}")
        if feed.entries:
            print(f"\nLatest episode: {feed.entries[0].get('title')}")

    # Test download (commented out to avoid actual download during testing)
    # filepath = manager.find_and_download_episode("Acquired", "Alphabet Inc.")


if __name__ == "__main__":
    test_rss_manager()
