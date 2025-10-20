"""
Speaker Separator using transcript markers and audio extraction.
Uses YouTube transcript >> markers to separate speakers and extract audio chunks.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
from pydub import AudioSegment
import json


class SpeakerSeparator:
    """Separates speakers using transcript markers and extracts audio chunks."""

    def __init__(self):
        """Initialize speaker separator."""
        pass

    def parse_speakers_from_transcript(self, transcript: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Parse transcript and group segments by speaker using >> markers.

        Args:
            transcript: List of transcript segments with 'text', 'start', 'duration'

        Returns:
            Dictionary mapping speaker IDs to their segments
        """
        speakers = {}
        current_speaker = "Speaker_0"
        speaker_count = 0

        for i, segment in enumerate(transcript):
            text = segment['text'].strip()

            # Check for speaker change marker
            if text.startswith('>>'):
                # New speaker
                speaker_count += 1
                current_speaker = f"Speaker_{speaker_count % 2}"  # Alternate between 0 and 1

                # Remove >> marker from text
                text = text[2:].strip()
                segment = {
                    'text': text,
                    'start': segment['start'],
                    'duration': segment['duration']
                }

            # Add segment to current speaker
            if current_speaker not in speakers:
                speakers[current_speaker] = []

            speakers[current_speaker].append(segment)

        return speakers

    def get_speaker_statistics(self, speakers: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Calculate statistics for each speaker.

        Args:
            speakers: Dictionary of speaker segments

        Returns:
            Statistics for each speaker
        """
        stats = {}

        for speaker_id, segments in speakers.items():
            total_duration = sum(seg['duration'] for seg in segments)
            total_segments = len(segments)
            total_words = sum(len(seg['text'].split()) for seg in segments)

            stats[speaker_id] = {
                'segments': total_segments,
                'duration_seconds': total_duration,
                'duration_minutes': total_duration / 60,
                'words': total_words,
                'first_timestamp': segments[0]['start'] if segments else 0,
                'last_timestamp': segments[-1]['start'] if segments else 0
            }

        return stats

    def group_continuous_segments(self, segments: List[Dict[str, Any]],
                                 max_gap_seconds: float = 5.0) -> List[List[Dict[str, Any]]]:
        """
        Group segments into continuous blocks where the speaker doesn't get interrupted.
        A block ends when there's a significant time gap (other speaker talking).

        Args:
            segments: List of segments for a speaker (already filtered by speaker)
            max_gap_seconds: Maximum gap to consider segments continuous

        Returns:
            List of segment groups, each group is a continuous uninterrupted block
        """
        if not segments:
            return []

        groups = []
        current_group = [segments[0]]

        for i in range(1, len(segments)):
            prev_end = segments[i-1]['start'] + segments[i-1]['duration']
            current_start = segments[i]['start']
            gap = current_start - prev_end

            # If gap is small (< 5 seconds), continue same block
            # If gap is large, it means the other speaker was talking
            if gap <= max_gap_seconds:
                current_group.append(segments[i])
            else:
                # Save current group and start new one
                groups.append(current_group)
                current_group = [segments[i]]

        # Add last group
        if current_group:
            groups.append(current_group)

        return groups

    def prioritize_segments_for_voice_cloning(self, segments: List[Dict[str, Any]],
                                             max_duration_minutes: float) -> List[Dict[str, Any]]:
        """
        Select best segments for voice cloning by prioritizing longer continuous blocks.

        Args:
            segments: All segments for a speaker
            max_duration_minutes: Maximum total duration to extract

        Returns:
            Prioritized list of segments
        """
        # Group into continuous blocks
        groups = self.group_continuous_segments(segments, max_gap_seconds=10.0)

        # Calculate duration for each group
        group_info = []
        for group in groups:
            # Use actual time span instead of summing durations (which may overlap)
            actual_duration = (group[-1]['start'] + group[-1]['duration']) - group[0]['start']
            group_info.append({
                'segments': group,
                'duration': actual_duration,
                'start': group[0]['start'],
                'word_count': sum(len(seg['text'].split()) for seg in group)
            })

        # Sort by duration (longest first)
        group_info.sort(key=lambda x: x['duration'], reverse=True)

        # Select groups until we hit the duration limit
        max_duration_seconds = max_duration_minutes * 60
        selected_segments = []
        total_duration = 0

        print(f"\n  Found {len(group_info)} continuous speech blocks")
        print(f"  Top 5 longest blocks:")

        for i, info in enumerate(group_info[:5]):
            print(f"    {i+1}. {info['duration']/60:.1f} min ({info['word_count']} words) at {info['start']/60:.1f} min")

        print(f"\n  Selecting longest blocks up to {max_duration_minutes} min...")

        for info in group_info:
            # Check if adding this block would exceed the limit
            if total_duration + info['duration'] > max_duration_seconds:
                # If we haven't added any blocks yet, add this one even if it exceeds
                if not selected_segments:
                    selected_segments.extend(info['segments'])
                    total_duration += info['duration']
                    print(f"    ✓ Added {info['duration']/60:.1f} min block (total: {total_duration/60:.1f} min)")
                    print(f"    (Exceeds limit but is the longest continuous block)")
                break

            # Add this group
            selected_segments.extend(info['segments'])
            total_duration += info['duration']

            print(f"    ✓ Added {info['duration']/60:.1f} min block (total: {total_duration/60:.1f} min)")

        # Sort selected segments by timestamp to maintain order
        selected_segments.sort(key=lambda x: x['start'])

        return selected_segments

    def extract_speaker_audio(self, audio_file: Path, segments: List[Dict[str, Any]],
                             output_file: Path, max_duration_minutes: Optional[int] = None) -> Optional[Path]:
        """
        Extract audio chunks for a specific speaker and combine them.
        Prioritizes longer continuous segments for better voice cloning quality.

        Args:
            audio_file: Path to source audio file
            segments: List of segments for this speaker
            output_file: Path to save extracted audio
            max_duration_minutes: Maximum duration to extract (for faster processing)

        Returns:
            Path to extracted audio file or None
        """
        if not audio_file.exists():
            print(f"⚠️  Audio file not found: {audio_file}")
            return None

        if not segments:
            print("⚠️  No segments provided")
            return None

        try:
            # Prioritize longer continuous segments
            if max_duration_minutes:
                segments = self.prioritize_segments_for_voice_cloning(segments, max_duration_minutes)

            print(f"\n📂 Loading audio file: {audio_file}")
            audio = AudioSegment.from_mp3(str(audio_file))

            print(f"🔪 Extracting {len(segments)} prioritized segments...")

            combined = AudioSegment.empty()
            total_extracted = 0

            for i, segment in enumerate(segments):
                start_ms = int(segment['start'] * 1000)
                duration_ms = int(segment['duration'] * 1000)
                end_ms = start_ms + duration_ms

                # Extract chunk
                chunk = audio[start_ms:end_ms]
                combined += chunk

                total_extracted += segment['duration']

                # Progress indicator
                if (i + 1) % 100 == 0:
                    print(f"  Processed {i + 1}/{len(segments)} segments ({total_extracted/60:.1f} min)")

            # Create output directory
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Export
            print(f"💾 Saving to: {output_file}")
            combined.export(str(output_file), format="mp3", bitrate="192k")  # Higher bitrate for better quality

            print(f"✓ Extracted {total_extracted/60:.1f} minutes of audio")
            return output_file

        except Exception as e:
            print(f"✗ Failed to extract audio: {e}")
            return None

    def separate_speakers(self, transcript: List[Dict[str, Any]], audio_file: Path,
                         output_dir: Path, max_duration_minutes: int = 3) -> Dict[str, Path]:
        """
        Complete speaker separation workflow.

        Args:
            transcript: Full transcript with segments
            audio_file: Source audio file
            output_dir: Directory to save separated audio files
            max_duration_minutes: Max audio per speaker (for voice cloning, 1-3 min recommended)

        Returns:
            Dictionary mapping speaker IDs to their audio file paths
        """
        print("\n" + "=" * 60)
        print("🎙️  SPEAKER SEPARATION")
        print("=" * 60)

        # Step 1: Parse speakers from transcript
        print("\n📝 Step 1: Parsing transcript for speakers...")
        speakers = self.parse_speakers_from_transcript(transcript)

        print(f"✓ Found {len(speakers)} speakers")

        # Step 2: Calculate statistics
        print("\n📊 Step 2: Calculating speaker statistics...")
        stats = self.get_speaker_statistics(speakers)

        for speaker_id, speaker_stats in stats.items():
            print(f"\n  {speaker_id}:")
            print(f"    Segments: {speaker_stats['segments']}")
            print(f"    Duration: {speaker_stats['duration_minutes']:.1f} minutes")
            print(f"    Words: {speaker_stats['words']}")

        # Step 3: Extract audio for each speaker
        print(f"\n🔊 Step 3: Extracting audio (max {max_duration_minutes} min per speaker)...")

        output_dir.mkdir(parents=True, exist_ok=True)
        speaker_audio_files = {}

        for speaker_id, segments in speakers.items():
            output_file = output_dir / f"{speaker_id}.mp3"

            print(f"\n  Extracting {speaker_id}...")
            result = self.extract_speaker_audio(
                audio_file=audio_file,
                segments=segments,
                output_file=output_file,
                max_duration_minutes=max_duration_minutes
            )

            if result:
                speaker_audio_files[speaker_id] = result

        print("\n" + "=" * 60)
        print(f"✓ Separation complete! Extracted {len(speaker_audio_files)} speaker audio files")
        print("=" * 60 + "\n")

        return speaker_audio_files


# Test function
def test_separator():
    """Test the speaker separator."""
    from transcript_manager import TranscriptManager
    from config import Config

    # Load transcript
    manager = TranscriptManager(youtube_api_key=Config.YOUTUBE_API_KEY)

    episode_info = {
        'title': 'Alphabet Inc.',
        'show': 'Acquired',
        'duration_ms': 15090000
    }

    print("Loading transcript...")
    if not manager.load_transcript_for_episode(episode_info):
        print("Failed to load transcript")
        return

    transcript = manager.get_full_transcript()

    # Test parsing
    separator = SpeakerSeparator()
    speakers = separator.parse_speakers_from_transcript(transcript)
    stats = separator.get_speaker_statistics(speakers)

    print("\nSpeaker Statistics:")
    for speaker_id, speaker_stats in stats.items():
        print(f"\n{speaker_id}:")
        print(f"  Segments: {speaker_stats['segments']}")
        print(f"  Duration: {speaker_stats['duration_minutes']:.1f} minutes")
        print(f"  Words: {speaker_stats['words']}")

    print("\nTo extract audio, you need to:")
    print("1. Download the episode audio first")
    print("2. Call separator.separate_speakers(transcript, audio_file, output_dir)")


if __name__ == "__main__":
    test_separator()
