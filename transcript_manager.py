"""
Transcript manager with caching for YouTube transcripts.
Stores transcripts locally to avoid repeated API calls.
"""

import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
from youtube_matcher import YouTubeMatcher


class TranscriptManager:
    """Manages transcript fetching and caching."""

    def __init__(self, cache_dir: Optional[Path] = None, youtube_api_key: Optional[str] = None):
        """
        Initialize transcript manager.

        Args:
            cache_dir: Directory to store cached transcripts
            youtube_api_key: YouTube Data API key (optional)
        """
        self.cache_dir = cache_dir or Path(__file__).parent / ".transcript_cache"
        self.cache_dir.mkdir(exist_ok=True)

        self.youtube_matcher = YouTubeMatcher(api_key=youtube_api_key)
        self.current_transcript = None
        self.current_episode_id = None
        self.current_video_id = None

    def _get_cache_key(self, episode_info: Dict[str, Any]) -> str:
        """
        Generate a cache key for an episode.

        Args:
            episode_info: Episode information

        Returns:
            Cache key (hash of show + title)
        """
        show = episode_info.get('show', '')
        title = episode_info.get('title', '')
        content = f"{show}|{title}".lower()
        return hashlib.md5(content.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cached transcript."""
        return self.cache_dir / f"{cache_key}.json"

    def _load_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Load transcript from cache.

        Args:
            cache_key: Cache key

        Returns:
            Cached data or None
        """
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load cache: {e}")
            return None

    def _save_to_cache(self, cache_key: str, data: Dict[str, Any]):
        """
        Save transcript to cache.

        Args:
            cache_key: Cache key
            data: Data to cache
        """
        cache_path = self._get_cache_path(cache_key)

        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save cache: {e}")

    def load_transcript_by_video_id(self, video_id: str, episode_info: Dict[str, Any] = None) -> bool:
        """
        Load transcript directly using a YouTube video ID (no search needed).

        Args:
            video_id: YouTube video ID
            episode_info: Optional episode info for caching

        Returns:
            True if transcript was loaded successfully
        """
        print(f"Fetching transcript for video ID: {video_id}...")

        # Fetch transcript
        transcript = self.youtube_matcher.get_transcript(video_id)

        if not transcript:
            return False

        self.current_transcript = transcript
        self.current_video_id = video_id

        # Cache if we have episode info
        if episode_info:
            cache_key = self._get_cache_key(episode_info)
            cache_data = {
                'video_id': video_id,
                'video_title': 'Manual entry',
                'video_channel': 'Unknown',
                'match_score': 100,
                'transcript': transcript,
                'episode_info': episode_info
            }
            self._save_to_cache(cache_key, cache_data)

        return True

    def load_transcript_for_episode(self, episode_info: Dict[str, Any]) -> bool:
        """
        Load transcript for a Spotify episode (from cache or YouTube).

        Args:
            episode_info: Episode information with 'title', 'show', 'duration_ms'

        Returns:
            True if transcript was loaded successfully
        """
        # Generate cache key
        cache_key = self._get_cache_key(episode_info)
        self.current_episode_id = cache_key

        # Try to load from cache first
        print(f"\nLooking for transcript...")
        cached_data = self._load_from_cache(cache_key)

        if cached_data:
            print(f"✓ Found cached transcript ({len(cached_data['transcript'])} segments)")
            self.current_transcript = cached_data['transcript']
            self.current_video_id = cached_data.get('video_id')
            return True

        # Not in cache, search YouTube
        print("Not in cache, searching YouTube...")
        match = self.youtube_matcher.match_episode_to_youtube(episode_info)

        if not match:
            print("✗ Could not find YouTube match")
            return False

        video_id = match['video_id']
        self.current_video_id = video_id

        # Fetch transcript
        transcript = self.youtube_matcher.get_transcript(video_id)

        if not transcript:
            print("✗ Could not fetch transcript")
            return False

        # Save to cache
        cache_data = {
            'video_id': video_id,
            'video_title': match['title'],
            'video_channel': match['channel'],
            'match_score': match.get('match_score', 0),
            'transcript': transcript,
            'episode_info': episode_info
        }
        self._save_to_cache(cache_key, cache_data)

        self.current_transcript = transcript
        return True

    def get_text_at_timestamp(self, timestamp_seconds: float, context_seconds: int = 30) -> Optional[str]:
        """
        Get transcript text at a specific timestamp.

        Args:
            timestamp_seconds: Timestamp in seconds
            context_seconds: Seconds of context before/after

        Returns:
            Transcript text or None
        """
        if not self.current_transcript:
            return None

        return self.youtube_matcher.find_transcript_at_timestamp(
            self.current_transcript,
            timestamp_seconds,
            context_seconds
        )

    def get_full_transcript(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get the full current transcript.

        Returns:
            Full transcript or None
        """
        return self.current_transcript

    def has_transcript(self) -> bool:
        """Check if a transcript is currently loaded."""
        return self.current_transcript is not None

    def clear_cache(self):
        """Clear all cached transcripts."""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(exist_ok=True)
            print("Cache cleared")


# Test function
def test_manager():
    """Test the transcript manager."""
    manager = TranscriptManager()

    # Sample episode
    episode_info = {
        'title': 'The Future of AI',
        'show': 'The Daily',
        'duration_ms': 1530000
    }

    # Load transcript
    if manager.load_transcript_for_episode(episode_info):
        # Test timestamp lookup
        text = manager.get_text_at_timestamp(60)  # 1 minute
        if text:
            print(f"\nText at 1:00:\n{text}")

        # Try again (should use cache)
        print("\n--- Testing cache ---")
        manager2 = TranscriptManager()
        if manager2.load_transcript_for_episode(episode_info):
            print("Cache is working!")


if __name__ == "__main__":
    test_manager()
