#!/usr/bin/env python3
"""
Fast test script: Create a synthetic podcast using Scribe on a 20-min segment.

This script will:
1. Download an Acquired episode (or use existing)
2. Extract first 20 minutes for Scribe analysis
3. Use Scribe to diarize speakers on that segment
4. Extract 10 min of audio per speaker from the 20-min segment
5. Create IVC clones for both speakers
6. Generate a synthetic conversation
7. Combine into a final podcast
"""

from pathlib import Path
from config import Config
from rss_manager import RSSManager
from scribe_diarizer import ScribeDiarizer
from voice_cloner import VoiceCloner
from pydub import AudioSegment
import sys


def main():
    print("\n" + "=" * 70)
    print("🎙️  FAST SYNTHETIC PODCAST GENERATOR (20-min segment)")
    print("=" * 70)

    # Check API key
    if not Config.ELEVENLABS_API_KEY:
        print("\n❌ Error: ELEVENLABS_API_KEY not set in .env")
        print("Please add your ElevenLabs API key to continue")
        sys.exit(1)

    # Step 1: Download Acquired episode
    print("\n📥 STEP 1: Download Episode")
    print("-" * 70)

    rss = RSSManager()
    episode_title = "Alphabet Inc."
    show_name = "Acquired"

    audio_file = rss.find_and_download_episode(show_name, episode_title)

    if not audio_file:
        print("\n❌ Failed to download episode")
        sys.exit(1)

    print(f"\n✓ Audio file ready: {audio_file}")

    # Step 2: Extract first 20 minutes
    print("\n\n✂️  STEP 2: Extract First 20 Minutes")
    print("-" * 70)

    segment_file = Path(__file__).parent / "podcast_audio" / f"{show_name}_{episode_title}_20min.mp3"

    if segment_file.exists():
        print(f"✓ 20-minute segment already exists: {segment_file}")
    else:
        print("Loading full audio file...")
        full_audio = AudioSegment.from_mp3(str(audio_file))

        # Extract first 20 minutes (20 * 60 * 1000 ms)
        twenty_min_ms = 20 * 60 * 1000
        segment_audio = full_audio[:twenty_min_ms]

        print(f"Saving 20-minute segment...")
        segment_audio.export(str(segment_file), format="mp3", bitrate="192k")
        print(f"✓ Saved: {segment_file}")
        print(f"  Size: {segment_file.stat().st_size / (1024*1024):.1f} MB")

    # Step 3: Transcribe and diarize with Scribe (20 min only!)
    print("\n\n🎙️  STEP 3: Scribe Diarization (20-min segment)")
    print("-" * 70)

    cache_dir = Path(__file__).parent / ".scribe_cache"
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"{show_name}_{episode_title}_20min.json"

    diarizer = ScribeDiarizer(api_key=Config.ELEVENLABS_API_KEY)

    # Check cache first
    scribe_result = diarizer.load_scribe_result(cache_file)

    if scribe_result:
        print("✓ Loaded cached Scribe result")
    else:
        print("⚠️  Note: Transcribing 20 minutes")
        print("   Estimated cost: ~$0.05")
        print("   Auto-proceeding with transcription...")

        scribe_result = diarizer.transcribe_with_diarization(segment_file, num_speakers=2)

        if not scribe_result:
            print("\n❌ Scribe transcription failed")
            sys.exit(1)

        # Save to cache
        diarizer.save_scribe_result(scribe_result, cache_file)

    # Parse speakers
    speakers = diarizer.parse_speakers_from_scribe(scribe_result)
    stats = diarizer.get_speaker_statistics(speakers)

    print("\n📊 Speaker Statistics (from 20-min segment):")
    for speaker_id, speaker_stats in stats.items():
        print(f"\n  {speaker_id}:")
        print(f"    Words: {speaker_stats['words']}")
        print(f"    Total duration: {speaker_stats['total_duration_minutes']:.1f} min")
        print(f"    Speech blocks: {speaker_stats['num_blocks']}")
        print(f"    Longest block: {speaker_stats['longest_block_minutes']:.1f} min")

    # Step 4: Extract audio for each speaker
    print("\n\n🔊 STEP 4: Extract Speaker Audio")
    print("-" * 70)

    speaker_audio_dir = Path(__file__).parent / "speaker_audio_scribe"
    speaker_audio_dir.mkdir(exist_ok=True)

    speaker_audio_files = {}

    print("Loading 20-minute segment audio...")
    segment_audio = AudioSegment.from_mp3(str(segment_file))

    for speaker_id, words in speakers.items():
        print(f"\n  Processing {speaker_id}...")

        # Group into continuous blocks
        blocks = diarizer.group_speaker_segments(words, min_gap_seconds=2.0)

        # Sort blocks by duration (longest first)
        blocks_with_duration = [(b, b[-1]['end'] - b[0]['start']) for b in blocks]
        blocks_with_duration.sort(key=lambda x: x[1], reverse=True)

        print(f"    Found {len(blocks)} speech blocks")
        print(f"    Top 5 longest: {[f'{d/60:.1f}m' for b, d in blocks_with_duration[:5]]}")

        # Extract up to 5 minutes from longest blocks (to stay under 11MB file size limit)
        target_duration = 5 * 60  # 5 minutes
        combined_audio = AudioSegment.empty()
        total_extracted = 0

        for block, duration in blocks_with_duration:
            if total_extracted >= target_duration:
                break

            # Extract this block
            start_ms = int(block[0]['start'] * 1000)
            end_ms = int(block[-1]['end'] * 1000)

            chunk = segment_audio[start_ms:end_ms]
            combined_audio += chunk
            total_extracted += duration

            print(f"      ✓ Added {duration/60:.1f} min block (total: {total_extracted/60:.1f} min)")

        # Save speaker audio
        output_file = speaker_audio_dir / f"{speaker_id}.mp3"
        combined_audio.export(str(output_file), format="mp3", bitrate="192k")

        speaker_audio_files[speaker_id] = output_file
        print(f"    💾 Saved: {output_file}")

    # Step 5: Create voice clones
    print("\n\n🎤 STEP 5: Create Voice Clones")
    print("-" * 70)

    cloner = VoiceCloner(api_key=Config.ELEVENLABS_API_KEY)
    voice_ids = {}

    for speaker_id, audio_file_path in speaker_audio_files.items():
        print(f"\n  Creating voice clone for {speaker_id}...")

        voice_name = f"Acquired - {speaker_id}"
        description = f"Voice cloned from Acquired podcast - {episode_title}"

        voice_id = cloner.create_voice_clone(
            name=voice_name,
            audio_files=[audio_file_path],
            description=description,
            remove_background_noise=True
        )

        if voice_id:
            voice_ids[speaker_id] = voice_id
            print(f"    ✓ Voice clone created: {voice_id}")
        else:
            print(f"    ❌ Failed to create voice clone")

    if len(voice_ids) < 2:
        print("\n❌ Need at least 2 voice clones to continue")
        sys.exit(1)

    # Step 6: Generate synthetic podcast
    print("\n\n🎬 STEP 6: Generate Synthetic Podcast")
    print("-" * 70)

    # Define the dialogue
    dialogue = [
        {"speaker": list(voice_ids.keys())[0], "text": "Hey everyone, welcome back to Acquired!"},
        {"speaker": list(voice_ids.keys())[1], "text": "Today we're doing something a little different - we're testing AI voice cloning."},
        {"speaker": list(voice_ids.keys())[0], "text": "That's right! These voices you're hearing are actually synthetic, generated using ElevenLabs."},
        {"speaker": list(voice_ids.keys())[1], "text": "Pretty wild, right? The technology has come so far."},
        {"speaker": list(voice_ids.keys())[0], "text": "It's amazing what's possible with just ten minutes of training audio."},
        {"speaker": list(voice_ids.keys())[1], "text": "Absolutely. Thanks for listening to this experimental episode!"},
    ]

    synthetic_audio_dir = Path(__file__).parent / "synthetic_podcast"
    synthetic_audio_dir.mkdir(exist_ok=True)

    generated_segments = []

    for i, line in enumerate(dialogue):
        speaker_id = line["speaker"]
        text = line["text"]
        voice_id = voice_ids[speaker_id]

        print(f"\n  [{i+1}/{len(dialogue)}] {speaker_id}: \"{text[:50]}...\"")

        output_file = synthetic_audio_dir / f"line_{i+1}_{speaker_id}.mp3"

        result = cloner.generate_speech(
            text=text,
            voice_id=voice_id,
            output_path=output_file
        )

        if result:
            generated_segments.append(result)
            print(f"        ✓ Generated")
        else:
            print(f"        ❌ Failed")

    # Step 7: Combine into final podcast
    print("\n\n🎵 STEP 7: Combine Audio")
    print("-" * 70)

    if not generated_segments:
        print("❌ No audio segments to combine")
        sys.exit(1)

    final_audio = AudioSegment.empty()

    for segment_file in generated_segments:
        audio = AudioSegment.from_mp3(str(segment_file))
        final_audio += audio
        # Add 0.5 second pause between speakers
        final_audio += AudioSegment.silent(duration=500)

    final_output = Path(__file__).parent / "synthetic_acquired_test.mp3"
    final_audio.export(str(final_output), format="mp3", bitrate="192k")

    print(f"\n✓ Final podcast created: {final_output}")
    print(f"  Duration: {len(final_audio) / 1000:.1f} seconds")
    print(f"\n  Play with: open \"{final_output}\"")

    print("\n" + "=" * 70)
    print("✅ COMPLETE!")
    print("=" * 70)
    print("\nNote: For full content, use YouTube transcript with these voice clones")


if __name__ == "__main__":
    main()
