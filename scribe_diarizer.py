"""
ElevenLabs Scribe Speaker Diarization
Uses ElevenLabs Scribe API for accurate speaker diarization from audio files.
"""

from typing import Optional, Dict, Any, List
from pathlib import Path
from elevenlabs.client import ElevenLabs
import json


class ScribeDiarizer:
    """Uses ElevenLabs Scribe to transcribe and diarize speakers in audio."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Scribe diarizer.

        Args:
            api_key: ElevenLabs API key
        """
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("ElevenLabs API key required for Scribe diarization")

        self.client = ElevenLabs(api_key=self.api_key)

    def transcribe_with_diarization(self, audio_file: Path, num_speakers: int = 2) -> Optional[Dict[str, Any]]:
        """
        Transcribe audio file with speaker diarization using Scribe.

        Args:
            audio_file: Path to audio file
            num_speakers: Expected number of speakers (default 2 for podcasts)

        Returns:
            Transcription result with speaker_id for each word, or None on failure
        """
        if not audio_file.exists():
            print(f"⚠️  Audio file not found: {audio_file}")
            return None

        try:
            print(f"\n🎙️  Transcribing with ElevenLabs Scribe...")
            print(f"   File: {audio_file.name}")
            print(f"   Expected speakers: {num_speakers}")
            print(f"   (This may take a few minutes for long audio files)")

            with open(audio_file, 'rb') as f:
                # Call Scribe API with diarization enabled
                result = self.client.speech_to_text.convert(
                    file=f,
                    model_id="scribe_v1",
                    diarize=True,
                    num_speakers=num_speakers,
                    timestamps_granularity="word"
                )

            print(f"✓ Transcription complete!")

            # Convert to dict if needed
            if hasattr(result, 'dict'):
                result = result.dict()
            elif hasattr(result, 'model_dump'):
                result = result.model_dump()

            return result

        except Exception as e:
            print(f"✗ Scribe transcription failed: {e}")
            return None

    def parse_speakers_from_scribe(self, scribe_result: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Parse Scribe results and group words by speaker.

        Args:
            scribe_result: Result from Scribe API

        Returns:
            Dictionary mapping speaker_id to list of word segments
        """
        speakers = {}

        # Get words array with speaker_id and timestamps
        words = scribe_result.get('words', [])

        if not words:
            print("⚠️  No word-level data in Scribe result")
            return speakers

        for word_data in words:
            speaker_id = word_data.get('speaker_id', 'unknown')

            if speaker_id not in speakers:
                speakers[speaker_id] = []

            speakers[speaker_id].append({
                'text': word_data.get('text', ''),
                'start': word_data.get('start', 0),
                'end': word_data.get('end', 0),
                'duration': word_data.get('end', 0) - word_data.get('start', 0)
            })

        return speakers

    def group_speaker_segments(self, speaker_words: List[Dict[str, Any]],
                              min_gap_seconds: float = 2.0) -> List[List[Dict[str, Any]]]:
        """
        Group word-level segments into continuous speech blocks.

        Args:
            speaker_words: List of word segments for one speaker
            min_gap_seconds: Minimum gap to start a new block

        Returns:
            List of continuous speech blocks
        """
        if not speaker_words:
            return []

        blocks = []
        current_block = [speaker_words[0]]

        for i in range(1, len(speaker_words)):
            prev_end = speaker_words[i-1]['end']
            current_start = speaker_words[i]['start']
            gap = current_start - prev_end

            if gap <= min_gap_seconds:
                current_block.append(speaker_words[i])
            else:
                blocks.append(current_block)
                current_block = [speaker_words[i]]

        if current_block:
            blocks.append(current_block)

        return blocks

    def get_speaker_statistics(self, speakers: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Calculate statistics for each speaker.

        Args:
            speakers: Dictionary of speaker word segments

        Returns:
            Statistics for each speaker
        """
        stats = {}

        for speaker_id, words in speakers.items():
            if not words:
                continue

            blocks = self.group_speaker_segments(words, min_gap_seconds=2.0)

            # Calculate block durations
            block_durations = []
            for block in blocks:
                duration = block[-1]['end'] - block[0]['start']
                block_durations.append(duration)

            total_duration = sum(word['duration'] for word in words)
            longest_block = max(block_durations) if block_durations else 0

            stats[speaker_id] = {
                'words': len(words),
                'total_duration_seconds': total_duration,
                'total_duration_minutes': total_duration / 60,
                'num_blocks': len(blocks),
                'longest_block_seconds': longest_block,
                'longest_block_minutes': longest_block / 60,
                'first_timestamp': words[0]['start'],
                'last_timestamp': words[-1]['end']
            }

        return stats

    def save_scribe_result(self, scribe_result: Dict[str, Any], output_file: Path):
        """Save Scribe result to JSON file for caching."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(scribe_result, f, indent=2)
        print(f"💾 Saved Scribe result to: {output_file}")

    def load_scribe_result(self, cache_file: Path) -> Optional[Dict[str, Any]]:
        """Load cached Scribe result from JSON file."""
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Could not load cached result: {e}")
            return None


# Test function
def test_scribe():
    """Test Scribe diarization."""
    import os
    from config import Config

    api_key = Config.ELEVENLABS_API_KEY

    if not api_key:
        print("⚠️  ELEVENLABS_API_KEY not set in .env")
        print("Cannot test without API key")
        return

    diarizer = ScribeDiarizer(api_key=api_key)

    # Check if we have a test audio file
    test_file = Path(__file__).parent / "podcast_audio" / "test.mp3"

    if not test_file.exists():
        print(f"⚠️  Test audio file not found: {test_file}")
        print("Download a podcast episode first using the RSS manager")
        return

    # Transcribe
    result = diarizer.transcribe_with_diarization(test_file, num_speakers=2)

    if result:
        # Parse speakers
        speakers = diarizer.parse_speakers_from_scribe(result)
        stats = diarizer.get_speaker_statistics(speakers)

        print("\n📊 Speaker Statistics:")
        for speaker_id, speaker_stats in stats.items():
            print(f"\n  {speaker_id}:")
            print(f"    Words: {speaker_stats['words']}")
            print(f"    Total duration: {speaker_stats['total_duration_minutes']:.1f} min")
            print(f"    Speech blocks: {speaker_stats['num_blocks']}")
            print(f"    Longest block: {speaker_stats['longest_block_minutes']:.1f} min")


if __name__ == "__main__":
    test_scribe()
