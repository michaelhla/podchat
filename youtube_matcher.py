"""
YouTube video matcher for Spotify podcasts.
Searches YouTube for matching videos and fetches transcripts.
"""

from typing import Optional, Dict, Any, List
from fuzzywuzzy import fuzz
from youtube_transcript_api import YouTubeTranscriptApi
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
from pathlib import Path


class YouTubeMatcher:
    """Matches Spotify podcast episodes to YouTube videos and fetches transcripts."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize YouTube matcher.

        Args:
            api_key: YouTube Data API key (optional, can work without for transcripts)
        """
        self.api_key = api_key
        self.youtube = None

        if api_key:
            try:
                self.youtube = build('youtube', 'v3', developerKey=api_key)
            except Exception as e:
                print(f"Warning: Could not initialize YouTube API: {e}")
                print("Will try to work without YouTube search API")

    def search_youtube(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search YouTube for videos matching the query.

        Args:
            query: Search query
            max_results: Maximum number of results to return

        Returns:
            List of video information dictionaries
        """
        if not self.youtube:
            print("YouTube API not available. Cannot search.")
            return []

        try:
            search_response = self.youtube.search().list(
                q=query,
                part='id,snippet',
                maxResults=max_results,
                type='video'
            ).execute()

            videos = []
            for item in search_response.get('items', []):
                if item['id']['kind'] == 'youtube#video':
                    video_id = item['id']['videoId']

                    # Get video details including duration
                    video_response = self.youtube.videos().list(
                        part='contentDetails,snippet',
                        id=video_id
                    ).execute()

                    if video_response['items']:
                        video_data = video_response['items'][0]
                        videos.append({
                            'video_id': video_id,
                            'title': video_data['snippet']['title'],
                            'channel': video_data['snippet']['channelTitle'],
                            'duration_iso': video_data['contentDetails']['duration'],
                            'duration_seconds': self._parse_duration(video_data['contentDetails']['duration'])
                        })

            return videos

        except HttpError as e:
            print(f"YouTube API error: {e}")
            return []

    def _parse_duration(self, iso_duration: str) -> int:
        """
        Parse ISO 8601 duration to seconds.

        Args:
            iso_duration: Duration in ISO 8601 format (e.g., 'PT1H30M15S')

        Returns:
            Duration in seconds
        """
        import re

        pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
        match = pattern.match(iso_duration)

        if not match:
            return 0

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        return hours * 3600 + minutes * 60 + seconds

    def match_episode_to_youtube(self, episode_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find the best matching YouTube video for a Spotify episode.

        Args:
            episode_info: Dictionary with 'title', 'show', 'duration_ms'

        Returns:
            Best matching video info or None
        """
        episode_title = episode_info.get('title', '')
        show_name = episode_info.get('show', '')
        episode_duration_seconds = episode_info.get('duration_ms', 0) / 1000

        # Build search query
        query = f"{show_name} {episode_title}"

        print(f"Searching YouTube for: {query[:80]}...")

        # Search YouTube
        videos = self.search_youtube(query, max_results=10)

        if not videos:
            print("No YouTube results found")
            return None

        # Score each video
        best_match = None
        best_score = 0
        all_scores = []

        for video in videos:
            score = 0

            # Title similarity (0-50 points)
            title_similarity = fuzz.token_sort_ratio(
                episode_title.lower(),
                video['title'].lower()
            ) / 100
            score += title_similarity * 50

            # Channel/Show name match (0-30 points)
            channel_similarity = fuzz.partial_ratio(
                show_name.lower(),
                video['channel'].lower()
            ) / 100
            score += channel_similarity * 30

            # Duration match (0-20 points)
            if episode_duration_seconds > 0 and video['duration_seconds'] > 0:
                duration_diff = abs(video['duration_seconds'] - episode_duration_seconds)
                # Within 2 minutes = full points, linearly decrease
                duration_score = max(0, 1 - (duration_diff / 120))
                score += duration_score * 20

            # Store score for debug output
            all_scores.append({
                'title': video['title'],
                'channel': video['channel'],
                'score': score,
                'title_sim': title_similarity * 50,
                'channel_sim': channel_similarity * 30,
                'duration': video['duration_seconds']
            })

            # Update best match
            if score > best_score:
                best_score = score
                best_match = video
                best_match['match_score'] = score

        # Show all candidates sorted by score
        print("\n🔍 All candidates (sorted by match score):")
        all_scores.sort(key=lambda x: x['score'], reverse=True)
        for i, candidate in enumerate(all_scores[:5], 1):
            print(f"   {i}. [{candidate['score']:.1f}] {candidate['title'][:50]}")
            print(f"      Channel: {candidate['channel'][:40]} | Duration: {candidate['duration']:.0f}s")
            print(f"      (title: {candidate['title_sim']:.1f}, channel: {candidate['channel_sim']:.1f})")
        print()

        # Show what we found regardless of confidence
        if best_match:
            if best_score > 70:
                print(f"✓ Found match: {best_match['title'][:60]}... (score: {best_score:.1f})")
            else:
                print(f"⚠ Low confidence match: {best_match['title'][:60]}... (score: {best_score:.1f})")
                print(f"   Channel: {best_match['channel']}")
                print(f"   Duration: {best_match['duration_seconds']}s vs episode {episode_duration_seconds:.0f}s")

            # Return the best match even if low confidence (let user decide)
            return best_match
        else:
            print("✗ No videos found in search results")
            return None

    def get_transcript(self, video_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch transcript for a YouTube video.

        Args:
            video_id: YouTube video ID

        Returns:
            List of transcript segments with 'start', 'duration', 'text'
        """
        try:
            print(f"Fetching transcript for video {video_id}...")
            # Create instance and fetch transcript
            api = YouTubeTranscriptApi()
            fetched_transcript = api.fetch(video_id)
            # Convert each snippet to plain dict
            transcript = []
            for snippet in fetched_transcript:
                transcript.append({
                    'text': snippet.text,
                    'start': snippet.start,
                    'duration': snippet.duration
                })
            print(f"✓ Got transcript with {len(transcript)} segments")
            return transcript
        except Exception as e:
            print(f"✗ Could not fetch transcript: {e}")
            return None

    def find_transcript_at_timestamp(self, transcript: List[Dict[str, Any]],
                                    timestamp_seconds: float,
                                    context_seconds: int = 30) -> Optional[str]:
        """
        Find transcript text at a specific timestamp with context.

        Args:
            transcript: List of transcript segments
            timestamp_seconds: Timestamp to look up
            context_seconds: How many seconds of context before/after

        Returns:
            Transcript text around the timestamp
        """
        if not transcript:
            return None

        # Find segments within the time range
        start_time = max(0, timestamp_seconds - context_seconds)
        end_time = timestamp_seconds + context_seconds

        mins = int(timestamp_seconds // 60)
        secs = int(timestamp_seconds % 60)
        print(f"\n🔍 Looking for transcript at {mins}:{secs:02d} (±{context_seconds}s range)")
        print(f"   Time range: {start_time:.1f}s - {end_time:.1f}s")

        relevant_segments = []
        for segment in transcript:
            seg_start = segment['start']
            seg_end = seg_start + segment['duration']

            # Check if segment overlaps with our time range
            if seg_start <= end_time and seg_end >= start_time:
                relevant_segments.append(segment)

        if not relevant_segments:
            print(f"   ⚠ No transcript segments found in this time range!")
            print(f"   First segment starts at: {transcript[0]['start']:.1f}s" if transcript else "   (empty transcript)")
            print(f"   Last segment ends at: {transcript[-1]['start'] + transcript[-1]['duration']:.1f}s" if transcript else "")
            return None

        print(f"   ✓ Found {len(relevant_segments)} segments")
        first_seg_time = relevant_segments[0]['start']
        last_seg_time = relevant_segments[-1]['start'] + relevant_segments[-1]['duration']
        print(f"   Segment range: {first_seg_time:.1f}s - {last_seg_time:.1f}s")

        # Combine text from relevant segments
        text = ' '.join(seg['text'] for seg in relevant_segments)
        return text.strip()


# Standalone function for easy testing
def test_matcher():
    """Test the YouTube matcher with a sample episode."""
    matcher = YouTubeMatcher()

    # Sample Spotify episode info
    episode_info = {
        'title': 'The Future of AI',
        'show': 'The Daily',
        'duration_ms': 1530000  # ~25 minutes
    }

    # Try to find match
    match = matcher.match_episode_to_youtube(episode_info)

    if match:
        print(f"\nMatch found!")
        print(f"Video ID: {match['video_id']}")
        print(f"Title: {match['title']}")
        print(f"Channel: {match['channel']}")

        # Try to get transcript
        transcript = matcher.get_transcript(match['video_id'])

        if transcript:
            # Test timestamp lookup
            text = matcher.find_transcript_at_timestamp(transcript, 60)  # 1 minute in
            print(f"\nText at 1:00: {text[:200]}...")
    else:
        print("No match found")


if __name__ == "__main__":
    test_matcher()
