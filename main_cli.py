#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spotify Podcast Controller - CLI Version
Control Spotify podcast playback with simple commands.
"""

import sys
from typing import Optional, Dict
from pathlib import Path
from spotify_client import SpotifyClient
from transcriber import SpeechTranscriber
from transcript_manager import TranscriptManager
from rss_manager import RSSManager
from voice_cloner import VoiceCloner
from speaker_separator import SpeakerSeparator
from scribe_diarizer import ScribeDiarizer
from pydub import AudioSegment
from config import Config


class PodcastController:
    """Main controller that integrates Spotify client with CLI commands."""

    def __init__(self):
        self.spotify = None
        self.transcriber = SpeechTranscriber()
        self.transcript_manager = TranscriptManager(youtube_api_key=Config.YOUTUBE_API_KEY)
        self.rss_manager = RSSManager()
        self.voice_cloner = VoiceCloner(api_key=Config.ELEVENLABS_API_KEY)
        self.speaker_separator = SpeakerSeparator()
        self.scribe_diarizer = ScribeDiarizer(api_key=Config.ELEVENLABS_API_KEY)
        self.current_voice_ids = {}  # Map speaker_id -> voice_id
        self.current_audio_file = None
        self.speaker_audio_files = {}  # Map speaker_id -> audio_file

    def setup(self) -> bool:
        """
        Initialize the Spotify client and authenticate.

        Returns:
            True if setup successful, False otherwise
        """
        # Validate configuration
        if not Config.validate():
            Config.print_setup_instructions()
            return False

        # Initialize Spotify client
        self.spotify = SpotifyClient(
            client_id=Config.SPOTIFY_CLIENT_ID,
            client_secret=Config.SPOTIFY_CLIENT_SECRET
        )

        # Try to load existing tokens
        if Config.TOKEN_FILE.exists():
            print("Loading saved tokens...")
            self.spotify.load_tokens(str(Config.TOKEN_FILE))

        # Authenticate (will use existing tokens if valid)
        print("Authenticating with Spotify...")
        if not self.spotify.authenticate():
            print("Authentication failed!")
            return False

        # Save tokens for next time
        self.spotify.save_tokens(str(Config.TOKEN_FILE))
        print("Authentication successful! Tokens saved.\n")

        return True

    def load_current_transcript(self):
        """Try to load transcript for currently playing episode."""
        status = self.spotify.get_playback_status()

        if not status.get("is_podcast") or not status.get("name"):
            print("Not currently playing a podcast")
            return

        episode_info = {
            'title': status.get('name'),
            'show': status.get('show'),
            'duration_ms': status.get('duration_ms', 0)
        }

        self.transcript_manager.load_transcript_for_episode(episode_info)

    def setup_voice_clone(self):
        """Download episode audio, use Scribe to diarize, and create voice clones."""
        status = self.spotify.get_playback_status()

        if not status.get("is_podcast") or not status.get("name"):
            print("Not currently playing a podcast - skipping voice clone setup")
            return

        show_name = status.get("show", "")
        episode_title = status.get("name", "")

        print("\n" + "=" * 60)
        print("🎙️  VOICE CLONING SETUP WITH SCRIBE DIARIZATION")
        print("=" * 60)

        # Step 1: Download episode audio
        print(f"\n📥 Step 1: Downloading episode audio...")
        print(f"   Show: {show_name}")
        print(f"   Episode: {episode_title}\n")

        audio_file = self.rss_manager.find_and_download_episode(show_name, episode_title)

        if not audio_file:
            print("\n⚠️  Could not download episode audio")
            print("   Voice cloning will not be available for this episode\n")
            return

        self.current_audio_file = audio_file
        print(f"\n✓ Audio downloaded: {audio_file}")

        # Step 2: Extract first 20 minutes for Scribe
        print(f"\n✂️  Step 2: Extracting first 20 minutes for analysis...")

        segment_file = audio_file.parent / f"{audio_file.stem}_20min.mp3"

        if segment_file.exists():
            print(f"✓ 20-minute segment already exists")
        else:
            print("Loading full audio file...")
            full_audio = AudioSegment.from_mp3(str(audio_file))
            twenty_min_ms = 20 * 60 * 1000
            segment_audio = full_audio[:twenty_min_ms]
            segment_audio.export(str(segment_file), format="mp3", bitrate="192k")
            print(f"✓ Saved 20-minute segment")

        # Step 3: Use Scribe to diarize speakers
        print(f"\n🎙️  Step 3: Analyzing speakers with Scribe...")

        cache_dir = Path(__file__).parent / ".scribe_cache"
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / f"{show_name}_{episode_title}_20min.json"

        scribe_result = self.scribe_diarizer.load_scribe_result(cache_file)

        if scribe_result:
            print("✓ Loaded cached Scribe result")
        else:
            print("⚠️  Transcribing with Scribe (cost: ~$0.05)...")
            scribe_result = self.scribe_diarizer.transcribe_with_diarization(segment_file, num_speakers=2)

            if not scribe_result:
                print("\n⚠️  Scribe diarization failed - skipping voice cloning\n")
                return

            self.scribe_diarizer.save_scribe_result(scribe_result, cache_file)

        # Parse speakers
        speakers = self.scribe_diarizer.parse_speakers_from_scribe(scribe_result)

        if not speakers:
            print("\n⚠️  No speakers found - skipping voice cloning\n")
            return

        print(f"✓ Found {len(speakers)} speakers")

        # Step 4: Extract audio for each speaker
        print(f"\n🔊 Step 4: Extracting speaker audio...")

        output_dir = Path(__file__).parent / "speaker_audio_scribe"
        output_dir.mkdir(exist_ok=True)

        segment_audio = AudioSegment.from_mp3(str(segment_file))

        for speaker_id, words in speakers.items():
            blocks = self.scribe_diarizer.group_speaker_segments(words, min_gap_seconds=2.0)
            blocks_with_duration = [(b, b[-1]['end'] - b[0]['start']) for b in blocks]
            blocks_with_duration.sort(key=lambda x: x[1], reverse=True)

            # Extract up to 5 minutes (to stay under 11MB file limit)
            target_duration = 5 * 60
            combined_audio = AudioSegment.empty()
            total_extracted = 0

            for block, duration in blocks_with_duration:
                if total_extracted >= target_duration:
                    break

                start_ms = int(block[0]['start'] * 1000)
                end_ms = int(block[-1]['end'] * 1000)
                chunk = segment_audio[start_ms:end_ms]
                combined_audio += chunk
                total_extracted += duration

            output_file = output_dir / f"{speaker_id}.mp3"
            combined_audio.export(str(output_file), format="mp3", bitrate="192k")
            self.speaker_audio_files[speaker_id] = output_file
            print(f"  ✓ {speaker_id}: {total_extracted/60:.1f} min extracted")

        # Step 5: Create voice clones for each speaker (or find existing ones)
        if not self.voice_cloner.client:
            print("\n⚠️  ElevenLabs not configured - skipping voice clone")
            print("   Set ELEVENLABS_API_KEY in .env to enable voice cloning\n")
            return

        print(f"\n🎤 Step 5: Setting up voice clones...")

        # Get all existing voices
        try:
            all_voices = self.voice_cloner.client.voices.get_all()
            existing_voices = {v.name: v.voice_id for v in all_voices.voices}
        except Exception as e:
            print(f"⚠️  Could not fetch existing voices: {e}")
            existing_voices = {}

        for speaker_id, speaker_audio in self.speaker_audio_files.items():
            voice_name = f"{show_name} - {speaker_id}"

            # Check if voice already exists
            if voice_name in existing_voices:
                voice_id = existing_voices[voice_name]
                self.current_voice_ids[speaker_id] = voice_id
                print(f"\n  ✓ {speaker_id}: Using existing voice clone (ID: {voice_id})")
            else:
                # Create new voice clone
                description = f"Voice cloned from {show_name} - {episode_title} ({speaker_id})"
                print(f"\n  Creating voice clone for {speaker_id}...")

                voice_id = self.voice_cloner.create_voice_clone(
                    name=voice_name,
                    audio_files=[speaker_audio],
                    description=description,
                    remove_background_noise=True
                )

                if voice_id:
                    self.current_voice_ids[speaker_id] = voice_id
                    print(f"  ✓ {speaker_id} voice clone created!")

        if self.current_voice_ids:
            print(f"\n✓ Voice clones ready: {len(self.current_voice_ids)} speakers")
            print(f"  Speakers: {', '.join(self.current_voice_ids.keys())}")
            print(f"  Hosts will respond when you talk!")
        else:
            print(f"\n⚠️  Voice cloning failed for all speakers")

        print("=" * 60 + "\n")

    def show_status(self):
        """Display current playback status."""
        status = self.spotify.get_playback_status()

        if not status["is_playing"] and status["name"] is None:
            print("  ⏸  Nothing is currently playing\n")
            return

        if status["is_podcast"]:
            playing_icon = "▶" if status["is_playing"] else "⏸"
            print(f"  {playing_icon}  Podcast: {status['name']}")
            print(f"     Show: {status['show']}")

            if status.get("progress_ms") and status.get("duration_ms"):
                progress = status["progress_ms"] / 1000
                duration = status["duration_ms"] / 1000
                progress_str = f"{int(progress // 60)}:{int(progress % 60):02d}"
                duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}"
                print(f"     Time: {progress_str} / {duration_str}\n")
        else:
            playing_icon = "▶" if status["is_playing"] else "⏸"
            print(f"  {playing_icon}  Track: {status['name']}")
            if status.get("artist"):
                print(f"     Artist: {status['artist']}\n")

    def handle_talk(self):
        """Handle the talk command - enters conversational mode with podcast hosts."""
        print("\n" + "=" * 60)
        print("💬 CONVERSATION MODE - Talk with the hosts")
        print("=" * 60)

        # Check if something is playing and get timestamp
        status = self.spotify.get_playback_status()
        was_playing = status.get("is_playing", False)
        device_id = status.get("device_id")  # Capture device ID for resume

        print(f"🔍 DEBUG: was_playing={was_playing}, device_id={device_id}")

        # Capture podcast info and timestamp
        podcast_context = None
        if status.get("is_podcast") and status.get("name"):
            progress_ms = status.get("progress_ms", 0)
            duration_ms = status.get("duration_ms", 0)

            # Format timestamp
            progress_sec = progress_ms / 1000
            duration_sec = duration_ms / 1000
            timestamp = f"{int(progress_sec // 60)}:{int(progress_sec % 60):02d}"
            total_time = f"{int(duration_sec // 60)}:{int(duration_sec % 60):02d}"

            podcast_context = {
                "episode": status.get("name"),
                "show": status.get("show"),
                "timestamp": timestamp,
                "timestamp_ms": progress_ms,
                "total_time": total_time,
                "duration_ms": duration_ms
            }

            print(f"📻 Podcast: {podcast_context['show']} - {podcast_context['episode']}")
            print(f"⏱️  Timestamp: {timestamp} / {total_time}")

        # Pause Spotify if playing
        if was_playing:
            print("⏸  Pausing Spotify...")
            self.spotify.pause()
            print()

        # Get podcast transcript context for conversation
        podcast_transcript = None
        extended_transcript_context = None
        interrupt_timestamp_seconds = None
        interrupt_sentence = None

        if podcast_context and self.transcript_manager.has_transcript():
            interrupt_timestamp_seconds = podcast_context['timestamp_ms'] / 1000

            # Get immediate context (30s) for conversation
            podcast_transcript = self.transcript_manager.get_text_at_timestamp(
                interrupt_timestamp_seconds,
                context_seconds=30
            )

            # Get extended context (60s) for rewind point detection
            extended_transcript_context = self.transcript_manager.get_text_at_timestamp(
                interrupt_timestamp_seconds,
                context_seconds=60
            )

            # Try to extract the sentence being spoken when interrupted
            # This is a rough approximation - get text within 5 seconds
            interrupt_sentence = self.transcript_manager.get_text_at_timestamp(
                interrupt_timestamp_seconds,
                context_seconds=5
            )

        # Enter conversation loop
        conversation_history = []
        turn_count = 0
        first_user_question = None  # Store first question for rewind analysis
        rewind_thread = None  # Background thread for rewind detection
        rewind_result = {"timestamp": None, "transition": None, "audio_file": None}  # Shared result

        print("🎙️  Listening... (will exit if you're silent or when conversation naturally ends)\n")

        while True:
            turn_count += 1

            # Record and transcribe user input with shorter timeout for conversation
            import time
            transcribe_start = time.time()
            text = self.transcriber.transcribe_from_microphone(timeout=3, phrase_time_limit=None)
            transcribe_time = time.time() - transcribe_start

            # Check if no speech detected (timeout/silence)
            if not text:
                print("\n⏸  No response detected - returning to podcast")
                break

            print(f"\n📝 You said: \"{text}\"")
            print(f"⏱️  Transcription: {transcribe_time:.2f}s")

            # Store first question and start background rewind detection
            if first_user_question is None:
                first_user_question = text

                # Start background thread for rewind detection (only if we have transcript)
                if interrupt_timestamp_seconds is not None and self.transcript_manager.has_transcript():
                    from threading import Thread

                    def background_rewind_and_audio():
                        """Background task: find rewind point and generate transition audio"""
                        try:
                            # Find rewind point with LLM
                            timestamp, transition = self.find_rewind_point(
                                first_user_question,
                                interrupt_sentence,
                                interrupt_timestamp_seconds
                            )
                            rewind_result["timestamp"] = timestamp
                            rewind_result["transition"] = transition

                            # Generate transition audio if we have a transition sentence
                            if transition and self.current_voice_ids:
                                from pathlib import Path
                                import tempfile
                                import datetime
                                import random

                                # Pick a random host voice
                                speaker_id = random.choice(list(self.current_voice_ids.keys()))
                                voice_id = self.current_voice_ids[speaker_id]

                                # Generate audio file
                                temp_dir = Path(tempfile.gettempdir()) / "podchat"
                                temp_dir.mkdir(exist_ok=True)
                                timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                audio_file = temp_dir / f"transition_{timestamp_str}.mp3"

                                # Generate TTS
                                audio_generator = self.voice_cloner.client.text_to_speech.convert(
                                    voice_id=voice_id,
                                    text=transition,
                                    model_id="eleven_turbo_v2_5"
                                )

                                with open(audio_file, 'wb') as f:
                                    for chunk in audio_generator:
                                        f.write(chunk)

                                rewind_result["audio_file"] = audio_file
                                print(f"\n   🎵 Transition audio ready")

                        except Exception as e:
                            print(f"\n   ⚠ Background rewind error: {e}")

                    rewind_thread = Thread(target=background_rewind_and_audio, daemon=True)
                    rewind_thread.start()
                    print(f"   🔄 Finding optimal rewind point in background...")

            # Add to conversation history
            conversation_history.append({"role": "user", "text": text})

            # Save to log file with timestamp and podcast context
            if podcast_context:
                self.save_transcription_log(text, podcast_context, podcast_transcript)

            # Generate intelligent response from podcast hosts if voice clones available
            if self.current_voice_ids:
                # Pass conversation history for multi-turn context
                # Returns True if should exit ([RETURN] token detected)
                should_exit = self.generate_host_response(text, podcast_transcript, conversation_history)
                if should_exit:
                    print(f"\n👍 Returning to podcast...")
                    break
            else:
                print("\n⚠️  No voice clones available")
                break

            # Continue loop - wait for next user input
            print(f"\n🎙️  Your turn...\n")

        # Resume Spotify if it was playing
        if was_playing:
            print(f"\n🔍 DEBUG: About to resume (was_playing={was_playing}, device_id={device_id})")

            # Wait for background rewind detection to complete (if running)
            if rewind_thread and rewind_thread.is_alive():
                print(f"⏳ Waiting for rewind analysis to complete...")
                rewind_thread.join(timeout=10)  # Max 10s wait

            # Play transition audio if available
            if rewind_result.get("audio_file"):
                print(f"🎵 Playing transition: \"{rewind_result.get('transition', '')}\"")
                try:
                    import wave
                    import pyaudio
                    from pydub import AudioSegment
                    import io

                    # Convert MP3 to WAV in memory
                    audio = AudioSegment.from_mp3(str(rewind_result["audio_file"]))
                    wav_io = io.BytesIO()
                    audio.export(wav_io, format="wav")
                    wav_io.seek(0)

                    # Play with PyAudio
                    p = pyaudio.PyAudio()
                    with wave.open(wav_io, 'rb') as wf:
                        stream = p.open(
                            format=p.get_format_from_width(wf.getsampwidth()),
                            channels=wf.getnchannels(),
                            rate=wf.getframerate(),
                            output=True
                        )

                        data = wf.readframes(1024)
                        while data:
                            stream.write(data)
                            data = wf.readframes(1024)

                        # Drain the buffer to prevent popping
                        stream.stop_stream()
                        stream.close()
                    p.terminate()

                    # Delay to ensure audio device is fully released
                    import time
                    time.sleep(0.1)

                except Exception as e:
                    print(f"⚠ Could not play transition audio: {e}")

            # Seek to rewind point
            if rewind_result.get("timestamp"):
                rewind_ms = int(rewind_result["timestamp"] * 1000)
                print(f"⏪ Rewinding to optimal point...")
                self.spotify.seek_to_position(rewind_ms)

                # Small delay after seek to let Spotify process
                import time
                time.sleep(0.2)

            print("▶  Resuming Spotify...")
            success = self.spotify.resume(device_id=device_id)
            print(f"🔍 DEBUG: Resume returned {success}")

            if not success and device_id:
                print("\n💡 TIP: If Spotify doesn't resume, try manually clicking play in the Spotify app")
        else:
            print(f"\n🔍 DEBUG: Not resuming (was_playing={was_playing})")

        print("=" * 60)
        print()

    def generate_host_response(self, user_text: str, podcast_context: Optional[str] = None, conversation_history: Optional[list] = None):
        """Generate a response from the podcast hosts using their cloned voices with streaming."""
        import anthropic
        import os
        import time
        import re
        from queue import Queue
        from threading import Thread
        import tempfile

        print("\n" + "-" * 60)
        print("🎤 PODCAST HOSTS RESPONDING...")
        print("-" * 60)

        try:
            start_time = time.time()

            # Get all available speakers
            import random
            available_speakers = list(self.current_voice_ids.keys())
            num_speakers = len(available_speakers)

            if num_speakers > 1:
                print(f"🔊 Streaming conversational response from {num_speakers} hosts...")
            else:
                print(f"🔊 Streaming response from {available_speakers[0]}...")

            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

            # Get context from transcript with clear interrupt point
            status = self.spotify.get_playback_status()
            show_name = status.get("show", "Unknown Podcast")
            episode_name = status.get("name", "")

            context_before = None
            context_after = None
            interrupt_timestamp = None

            if self.transcript_manager.has_transcript() and status.get("progress_ms"):
                timestamp_seconds = status["progress_ms"] / 1000
                interrupt_timestamp = timestamp_seconds

                # Get 5 minutes before the interrupt point
                context_before = self.transcript_manager.get_text_at_timestamp(
                    timestamp_seconds - 150,  # 2.5 min before
                    context_seconds=300  # 5 minutes of content
                )

                # Get ~30 seconds right at the interrupt point
                context_after = self.transcript_manager.get_text_at_timestamp(
                    timestamp_seconds,
                    context_seconds=30
                )

            # Build speaker list for prompt
            speaker_list = ", ".join(available_speakers)

            if num_speakers > 1:
                system_prompt = f"""You are the hosts of the podcast "{show_name}". The hosts are: {speaker_list}.
You are having a natural conversation with a listener who just paused the episode to ask you something.

FORMAT YOUR RESPONSE AS A CONVERSATION between the hosts using speaker tags. Use the format:
[{available_speakers[0]}:] First host says something brief
[{available_speakers[1] if num_speakers > 1 else available_speakers[0]}:] Second host adds to it or responds
[{available_speakers[0]}:] First host continues...

Your response style should be:
- Natural back-and-forth conversation between hosts (like you're riffing together)
- Each host speaks 1-2 sentences max per turn, then the other responds
- Conversational and warm, like talking to a friend
- Hosts can build on each other's points, disagree playfully, or add details
- Keep the TOTAL response brief (3-5 exchanges max)
- Match the tone and style of the actual podcast

The listener interrupted you mid-episode to ask their question. Pay special attention to what you were saying RIGHT when they paused - that's almost certainly what they're asking about.

IMPORTANT: If the listener's message is just an acknowledgment (like "ok", "thanks", "got it", "that makes sense", "sounds good") with no follow-up question, output ONLY the token [RETURN] to signal the conversation is over and they want to return to the podcast. Do not say anything else when outputting [RETURN]."""
            else:
                system_prompt = f"""You are {available_speakers[0]}, a host of the podcast "{show_name}".
You are having a natural conversation with a listener who just paused the episode to ask you something.

Your response style should be:
- Conversational and warm, like you're talking to a friend
- Knowledgeable but not condescending
- Brief (1-3 sentences max) - this is a quick back-and-forth, not a monologue
- Match the tone and style of the actual podcast

The listener interrupted you mid-episode to ask their question. Pay special attention to what you were saying RIGHT when they paused - that's almost certainly what they're asking about.

IMPORTANT: If the listener's message is just an acknowledgment (like "ok", "thanks", "got it", "that makes sense", "sounds good") with no follow-up question, output ONLY the token [RETURN] to signal the conversation is over and they want to return to the podcast. Do not say anything else when outputting [RETURN]."""

            user_prompt = ""

            # Add conversation history if this is a multi-turn conversation
            if conversation_history and len(conversation_history) > 1:
                user_prompt += "Conversation so far:\n"
                for turn in conversation_history[:-1]:  # All but current turn
                    user_prompt += f"Listener: \"{turn['text']}\"\n"
                user_prompt += "\n"

            user_prompt += f"Listener's question: \"{user_text}\"\n\n"

            if episode_name:
                user_prompt += f"Episode: {episode_name}\n"

            if interrupt_timestamp:
                mins = int(interrupt_timestamp // 60)
                secs = int(interrupt_timestamp % 60)
                user_prompt += f"Timestamp when interrupted: {mins}:{secs:02d}\n\n"

            if context_after:
                user_prompt += f"What you were JUST saying when the listener paused (most relevant):\n\"\"\"\n{context_after}\n\"\"\"\n\n"

            if context_before:
                user_prompt += f"Earlier context (what you discussed before):\n\"\"\"\n{context_before}\n\"\"\"\n\n"

            if conversation_history and len(conversation_history) > 1:
                user_prompt += "Continue the conversation naturally based on what you've discussed:"
            else:
                user_prompt += "The listener's question likely refers to what you were JUST saying when they interrupted. Respond naturally:"

            # Queue for audio chunks with seamless playback
            audio_queue = Queue()
            playback_started = False
            first_audio_time = None

            def play_audio_queue():
                """Play audio chunks with PyAudio for smooth streaming"""
                import wave
                import pyaudio
                from pydub import AudioSegment
                import io

                # Initialize PyAudio once
                p = pyaudio.PyAudio()
                stream = None

                try:
                    while True:
                        item = audio_queue.get()
                        if item is None:  # Sentinel to stop
                            break
                        audio_file, sentence = item

                        try:
                            # Convert MP3 to WAV in memory
                            audio = AudioSegment.from_mp3(str(audio_file))

                            # Export to WAV bytes
                            wav_io = io.BytesIO()
                            audio.export(wav_io, format="wav")
                            wav_io.seek(0)

                            # Open as wave file
                            with wave.open(wav_io, 'rb') as wf:
                                # Initialize stream if first chunk
                                if stream is None:
                                    stream = p.open(
                                        format=p.get_format_from_width(wf.getsampwidth()),
                                        channels=wf.getnchannels(),
                                        rate=wf.getframerate(),
                                        output=True
                                    )

                                # Play audio data
                                data = wf.readframes(1024)
                                while data:
                                    stream.write(data)
                                    data = wf.readframes(1024)

                        except Exception as e:
                            print(f"\n⚠️  Playback error: {e}")
                finally:
                    if stream:
                        stream.stop_stream()
                        stream.close()
                    p.terminate()

            # Start playback thread
            playback_thread = Thread(target=play_audio_queue, daemon=True)
            playback_thread.start()

            # Stream Claude response
            text_buffer = ""
            sentence_count = 0
            full_response = ""
            current_speaker = None  # Track current speaker from tags
            default_speaker = available_speakers[0] if available_speakers else None

            # Timing variables
            llm_start_time = time.time()
            first_token_time = None
            tts_times = []

            with client.messages.stream(
                model="claude-3-5-haiku-20241022",
                max_tokens=400,
                messages=[{"role": "user", "content": user_prompt}],
                system=system_prompt
            ) as stream:
                should_return = False
                for text in stream.text_stream:
                    # Record time to first token
                    if first_token_time is None:
                        first_token_time = time.time() - llm_start_time

                    text_buffer += text
                    full_response += text

                    # Check for [RETURN] token early
                    if "[RETURN]" in full_response or "[return]" in full_response.lower():
                        print(f"\n🔍 DEBUG: [RETURN] token detected - stopping generation")
                        should_return = True
                        break

                    # Process speaker-tagged chunks OR sentences
                    # Split on speaker tags first (e.g., [Speaker1:], [Speaker2:])
                    speaker_pattern = r'\[([^\]]+):\]'
                    parts = re.split(speaker_pattern, text_buffer)

                    # If we have speaker tags, process by speaker chunks
                    if len(parts) > 1 and num_speakers > 1:
                        # parts will be: ['prefix', 'Speaker1', 'text1', 'Speaker2', 'text2', ...]
                        i = 0
                        while i < len(parts):
                            if i == 0:
                                # Prefix text before first tag (usually empty)
                                i += 1
                                continue

                            if i + 1 < len(parts):
                                potential_speaker = parts[i].strip()
                                speaker_text = parts[i + 1]

                                # Check if this speaker exists in our voice IDs
                                if potential_speaker in self.current_voice_ids:
                                    current_speaker = potential_speaker
                                    voice_id = self.current_voice_ids[current_speaker]

                                    # Process sentences within this speaker's chunk
                                    sentences = re.split(r'([.!?]+)', speaker_text)

                                    # Only process complete sentences
                                    while len(sentences) >= 2:
                                        sentence = sentences[0] + (sentences[1] if len(sentences) > 1 else "")
                                        sentence = sentence.strip()

                                        if sentence and len(sentence) > 3:
                                            sentence_count += 1

                                            # Generate TTS for this sentence
                                            tts_start = time.time()
                                            temp_dir = Path(tempfile.gettempdir()) / "podchat"
                                            temp_dir.mkdir(exist_ok=True)
                                            import datetime
                                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                            audio_file = temp_dir / f"stream_{timestamp}_{sentence_count}.mp3"

                                            # Generate audio with correct voice
                                            audio_generator = self.voice_cloner.client.text_to_speech.convert(
                                                voice_id=voice_id,
                                                text=sentence,
                                                model_id="eleven_turbo_v2_5",
                                                optimize_streaming_latency=4
                                            )

                                            with open(audio_file, 'wb') as f:
                                                for chunk in audio_generator:
                                                    f.write(chunk)

                                            tts_time = time.time() - tts_start
                                            tts_times.append(tts_time)

                                            # Queue for playback
                                            audio_queue.put((audio_file, sentence))

                                            if not playback_started:
                                                playback_started = True
                                                first_audio_time = time.time() - start_time
                                                print(f"▶️  [{current_speaker}] Playing (first audio: {first_audio_time:.1f}s)")
                                            else:
                                                print(f"   [{current_speaker}] {sentence[:60]}...")

                                        # Remove processed sentence
                                        sentences = sentences[2:]

                                    # Update text_buffer with remaining incomplete text
                                    remaining_text = ''.join(sentences)
                                    if i + 2 < len(parts):
                                        # More speaker tags ahead, keep processing
                                        text_buffer = f"[{parts[i+2]}:]" + parts[i+3] if i + 3 < len(parts) else ""
                                        i += 2
                                    else:
                                        # This is the last chunk, keep remainder
                                        text_buffer = remaining_text
                                        break
                                else:
                                    # Unknown speaker, skip
                                    i += 2
                            else:
                                break
                    else:
                        # No speaker tags (single speaker mode or no tags yet) - use default behavior
                        if current_speaker is None and default_speaker:
                            current_speaker = default_speaker
                            voice_id = self.current_voice_ids[current_speaker]

                        sentences = re.split(r'([.!?]+)', text_buffer)

                        # Process complete sentences
                        while len(sentences) >= 2:
                            sentence = sentences[0] + (sentences[1] if len(sentences) > 1 else "")
                            sentence = sentence.strip()

                            if sentence and len(sentence) > 3:
                                sentence_count += 1

                                # Generate TTS for this sentence
                                tts_start = time.time()
                                temp_dir = Path(tempfile.gettempdir()) / "podchat"
                                temp_dir.mkdir(exist_ok=True)
                                import datetime
                                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                audio_file = temp_dir / f"stream_{timestamp}_{sentence_count}.mp3"

                                # Generate audio
                                audio_generator = self.voice_cloner.client.text_to_speech.convert(
                                    voice_id=voice_id,
                                    text=sentence,
                                    model_id="eleven_turbo_v2_5",
                                    optimize_streaming_latency=4
                                )

                                with open(audio_file, 'wb') as f:
                                    for chunk in audio_generator:
                                        f.write(chunk)

                                tts_time = time.time() - tts_start
                                tts_times.append(tts_time)

                                # Queue for playback
                                audio_queue.put((audio_file, sentence))

                                if not playback_started:
                                    playback_started = True
                                    first_audio_time = time.time() - start_time
                                    print(f"▶️  Playing (first audio: {first_audio_time:.1f}s)")

                            # Remove processed sentence
                            text_buffer = ''.join(sentences[2:])
                            sentences = re.split(r'([.!?]+)', text_buffer)

                # Check if [RETURN] was detected
                if should_return:
                    # Cancel any pending audio
                    audio_queue.put(None)
                    playback_thread.join()
                    print("-" * 60)
                    return True

                # Process any remaining text (only if not returning)
                if text_buffer.strip():
                    sentence_count += 1
                    temp_dir = Path(tempfile.gettempdir()) / "podchat"
                    temp_dir.mkdir(exist_ok=True)
                    import datetime
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    audio_file = temp_dir / f"stream_{timestamp}_{sentence_count}.mp3"

                    audio_generator = self.voice_cloner.client.text_to_speech.convert(
                        voice_id=voice_id,
                        text=text_buffer.strip(),
                        model_id="eleven_turbo_v2_5",
                        optimize_streaming_latency=4
                    )

                    with open(audio_file, 'wb') as f:
                        for chunk in audio_generator:
                            f.write(chunk)

                    audio_queue.put((audio_file, text_buffer.strip()))

            # Signal end of playback
            audio_queue.put(None)
            print(f"\n🔍 DEBUG: Waiting for playback thread to complete...")
            playback_thread.join()
            print(f"🔍 DEBUG: Playback thread completed")

            total_time = time.time() - start_time
            llm_total_time = time.time() - llm_start_time

            # Count approximate tokens (rough estimate: 1 token ≈ 4 characters)
            approx_tokens = len(full_response) / 4
            print(f"\n🔍 DEBUG: Generated {len(full_response)} characters (~{approx_tokens:.0f} tokens)")
            print(f"\n💬 Response: \"{full_response}\"")

            # Performance breakdown
            print(f"\n⏱️  Performance Breakdown:")
            if first_token_time:
                print(f"   • Time to first LLM token: {first_token_time:.2f}s")
            print(f"   • Total LLM generation: {llm_total_time:.2f}s")
            if tts_times:
                avg_tts = sum(tts_times) / len(tts_times)
                total_tts = sum(tts_times)
                print(f"   • TTS generation: {total_tts:.2f}s total ({avg_tts:.2f}s avg per sentence, {len(tts_times)} sentences)")
            if first_audio_time:
                print(f"   • Time to first audio playback: {first_audio_time:.2f}s")
            print(f"   • Total response time: {total_time:.2f}s")

            print("-" * 60)
            return False

        except Exception as e:
            print(f"\n⚠️  Could not generate response: {e}")
            import traceback
            traceback.print_exc()

        print("-" * 60)
        return False

    def get_transcript_with_timestamps(self, center_timestamp: float, context_seconds: int = 60) -> str:
        """
        Get transcript formatted with timestamps for LLM analysis.

        Args:
            center_timestamp: Center point in seconds
            context_seconds: Seconds of context around center

        Returns:
            Formatted transcript with timestamps
        """
        if not self.transcript_manager.has_transcript():
            return None

        transcript = self.transcript_manager.get_full_transcript()
        if not transcript:
            return None

        # Find segments within range
        start_time = max(0, center_timestamp - context_seconds)
        end_time = center_timestamp + context_seconds

        relevant_segments = []
        for segment in transcript:
            seg_start = segment['start']
            seg_end = seg_start + segment['duration']
            if seg_start <= end_time and seg_end >= start_time:
                relevant_segments.append(segment)

        if not relevant_segments:
            return None

        # Format with timestamps
        formatted = []
        for segment in relevant_segments:
            timestamp_sec = segment['start']
            mins = int(timestamp_sec // 60)
            secs = int(timestamp_sec % 60)
            formatted.append(f"[{mins}:{secs:02d}] {segment['text']}")

        return '\n'.join(formatted)

    def find_rewind_point(self, user_question: str, interrupt_sentence: Optional[str],
                          interrupt_timestamp: float) -> tuple[float, Optional[str]]:
        """
        Use LLM to intelligently find where to rewind to (start of current thought).

        Args:
            user_question: The user's first question in the conversation
            interrupt_sentence: The sentence being spoken when paused
            interrupt_timestamp: When the interrupt happened (in seconds)

        Returns:
            Tuple of (timestamp to rewind to in seconds, transition sentence)
        """
        import anthropic
        import os
        import re

        print("\n🔍 Finding optimal rewind point...")

        try:
            # Get transcript with timestamps
            transcript_context = self.get_transcript_with_timestamps(interrupt_timestamp, context_seconds=45)

            if not transcript_context:
                print(f"   ⚠ No transcript available, using 10s rewind")
                return (max(0, interrupt_timestamp - 10), None)

            # Debug: show first few lines of transcript
            lines = transcript_context.split('\n')
            print(f"   📝 Transcript has {len(lines)} lines")
            if len(lines) > 0:
                print(f"   First line: {lines[0][:80]}...")
                print(f"   Last line: {lines[-1][:80]}...")

            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

            # Calculate valid range
            min_allowed = max(0, interrupt_timestamp - 30)
            min_mins = int(min_allowed // 60)
            min_secs = int(min_allowed % 60)
            interrupt_mins = int(interrupt_timestamp // 60)
            interrupt_secs = int(interrupt_timestamp % 60)

            print(f"   Valid range: {min_mins}:{min_secs:02d} to {interrupt_mins}:{interrupt_secs:02d}")

            # Get show name for transition sentence
            status = self.spotify.get_playback_status()
            show_name = status.get("show", "the podcast")

            # Build prompt for LLM - with transition sentence generation
            prompt = f"""Find the best rewind point for a podcast and create a smooth transition.

INTERRUPT TIME: {interrupt_mins}:{interrupt_secs:02d}
VALID RANGE: Any timestamp between {min_mins}:{min_secs:02d} and {interrupt_mins}:{interrupt_secs:02d}

USER ASKED: "{user_question}"

TRANSCRIPT WITH TIMESTAMPS:
{transcript_context}

TASK 1 - Find Rewind Point:
Find where the current thought/topic started. Look for:
- Natural topic transitions: "Now...", "So...", "The key thing is...", "Let me explain..."
- Sentence boundaries - MUST be at the START of a sentence, never mid-sentence
- The beginning of a complete thought/idea

CRITICAL RULES:
1. Timestamp MUST be between {min_mins}:{min_secs:02d} and {interrupt_mins}:{interrupt_secs:02d}
2. MUST be at the START of a sentence (look for capital letters after periods/question marks)
3. IMPORTANT: Transcript segments may contain multiple sentences. You need to:
   - Identify where in the text the sentence/thought actually starts
   - Find the timestamp of that segment
   - Estimate how many seconds into that segment the sentence begins
   - Calculate: base_timestamp + estimated_offset
   - Example: [224:46] contains "maybe up to 50%. But this is going to be..."
     → Sentence "But this is..." starts ~2 seconds into this segment
     → Return timestamp: 224:48
4. If unsure, subtract 15 seconds from {interrupt_mins}:{interrupt_secs:02d}

TASK 2 - Create Transition Sentence:
Write a brief, natural transition sentence (1-2 sentences max) that the podcast host would say to smoothly return to the episode. Should sound like:
- "Alright, let's get back to where we were..."
- "Good question! Now, picking up where we left off..."
- "Thanks for asking! So, back to what we were discussing..."

OUTPUT FORMAT (exactly 3 lines):
Line 1: TIMESTAMP: M:SS or MM:SS
Line 2: TEXT_AT_POINT: [first few words at that timestamp]
Line 3: TRANSITION: [your transition sentence]

Example:
TIMESTAMP: 224:48
TEXT_AT_POINT: But this is going to be
TRANSITION: Great question! So as we were saying..."""

            # Debug: print prompt
            print(f"\n   📋 LLM Prompt Preview:")
            print(f"   " + "="*60)
            prompt_preview = prompt[:500] + "..." if len(prompt) > 500 else prompt
            for line in prompt_preview.split('\n'):
                print(f"   {line}")
            print(f"   " + "="*60)

            # Call Claude Sonnet 4.5 for better reasoning
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=150,  # Need space for timestamp + transition
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()
            print(f"   LLM response:\n{response_text}")

            # Parse the response - looking for TIMESTAMP, TEXT_AT_POINT, and TRANSITION lines
            timestamp_match = re.search(r'TIMESTAMP:\s*(\d+):(\d+)', response_text)
            text_at_point_match = re.search(r'TEXT_AT_POINT:\s*(.+)', response_text)
            transition_match = re.search(r'TRANSITION:\s*(.+)', response_text, re.DOTALL)

            transition_sentence = None
            text_at_point = None

            if text_at_point_match:
                text_at_point = text_at_point_match.group(1).strip()
                print(f"   📍 Text at rewind: \"{text_at_point}\"")

            if transition_match:
                transition_sentence = transition_match.group(1).strip()
                print(f"   💬 Transition: \"{transition_sentence}\"")

            if timestamp_match:
                minutes = int(timestamp_match.group(1))
                seconds = int(timestamp_match.group(2))
                suggested_timestamp = minutes * 60 + seconds

                # Debug the validation
                print(f"   🔍 Debug: suggested={suggested_timestamp}s, min_allowed={min_allowed}s, max_allowed={interrupt_timestamp}s")

                # Validate: must be within 30s before interrupt, and not after
                # Add 2-second tolerance for rounding/transcript boundaries
                max_allowed = interrupt_timestamp
                tolerance = 2

                if (min_allowed - tolerance) <= suggested_timestamp <= max_allowed:
                    rewind_seconds = interrupt_timestamp - suggested_timestamp
                    print(f"   ✓ Rewinding {rewind_seconds:.0f}s to {minutes}:{seconds:02d}")

                    # Show context around the rewind point
                    transcript = self.transcript_manager.get_full_transcript()
                    if transcript:
                        print(f"\n   📍 Context at rewind point:")
                        for segment in transcript:
                            seg_time = segment['start']
                            # Show segments within ±10 seconds of rewind point
                            if suggested_timestamp - 10 <= seg_time <= suggested_timestamp + 10:
                                seg_mins = int(seg_time // 60)
                                seg_secs = int(seg_time % 60)
                                marker = "👉" if abs(seg_time - suggested_timestamp) < 3 else "  "
                                print(f"   {marker} [{seg_mins}:{seg_secs:02d}] {segment['text'][:70]}")

                    return (suggested_timestamp, transition_sentence)
                else:
                    print(f"   ⚠ Timestamp {minutes}:{seconds:02d} out of valid range ({min_mins}:{min_secs:02d} to {interrupt_mins}:{interrupt_secs:02d}), using 10s rewind")
                    print(f"   🔍 Debug: Check failed: {min_allowed} <= {suggested_timestamp} <= {max_allowed} = {min_allowed <= suggested_timestamp <= max_allowed}")
                    return (max(0, interrupt_timestamp - 10), transition_sentence)
            else:
                print(f"   ⚠ Could not parse timestamp, using 10s rewind")
                return (max(0, interrupt_timestamp - 10), transition_sentence)

        except Exception as e:
            print(f"   ⚠ Error finding rewind point: {e}")
            import traceback
            traceback.print_exc()
            # Fallback: rewind 10 seconds
            return (max(0, interrupt_timestamp - 10), None)

    def generate_host_echo(self, audio_file: Path):
        """Use voice-to-voice to echo user's words in a host's voice (FAST)."""
        from pydub import AudioSegment
        from pydub.playback import play
        import time
        import random

        print("\n" + "-" * 60)
        print("🎤 HOST ECHOING YOUR WORDS...")
        print("-" * 60)

        try:
            start_time = time.time()

            # Pick a random speaker
            speaker_id = random.choice(list(self.current_voice_ids.keys()))
            voice_id = self.current_voice_ids[speaker_id]

            print(f"🔊 Transforming to {speaker_id}'s voice...")

            # Generate output file
            output_dir = Path(__file__).parent / "generated_speech"
            output_dir.mkdir(exist_ok=True)

            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = output_dir / f"echo_{timestamp}.mp3"

            # Use speech-to-speech for direct voice transformation
            with open(audio_file, 'rb') as f:
                audio_generator = self.voice_cloner.client.speech_to_speech.convert(
                    voice_id=voice_id,
                    audio=f,
                    model_id="eleven_multilingual_sts_v2",  # Speech-to-speech model
                    output_format="mp3_44100_128",
                    remove_background_noise=True
                )

                # Save audio
                with open(output_file, 'wb') as out:
                    for chunk in audio_generator:
                        out.write(chunk)

            transform_time = time.time() - start_time
            print(f"✓ Voice transformed ({transform_time:.1f}s)")

            # Play the audio
            print("▶️  Playing...")
            audio = AudioSegment.from_mp3(str(output_file))
            play(audio)

            total_time = time.time() - start_time
            print(f"✓ Complete (total: {total_time:.1f}s)")

        except Exception as e:
            print(f"\n⚠️  Voice transformation failed: {e}")
            print("   Falling back to text-based response...")
            # Could fallback to LLM-based response here if needed

        print("-" * 60)

    def handle_load_transcript(self, video_id: str):
        """Manually load transcript by YouTube video ID."""
        print(f"\nLoading transcript from YouTube video: {video_id}")

        # Get current episode info if available
        status = self.spotify.get_playback_status()
        episode_info = None
        if status.get("is_podcast") and status.get("name"):
            episode_info = {
                'title': status.get('name'),
                'show': status.get('show'),
                'duration_ms': status.get('duration_ms', 0)
            }

        # Load transcript
        if self.transcript_manager.load_transcript_by_video_id(video_id, episode_info):
            print("✓ Transcript loaded successfully!\n")
        else:
            print("✗ Failed to load transcript\n")

    def handle_transcript(self):
        """Show transcript at current playback position."""
        if not self.transcript_manager.has_transcript():
            print("\n⚠️  No transcript available for current episode")
            print("   Transcript may not exist on YouTube, or episode doesn't match")
            return

        # Get current position
        status = self.spotify.get_playback_status()
        if not status.get("progress_ms"):
            print("\n⚠️  Could not get current playback position")
            return

        timestamp_seconds = status["progress_ms"] / 1000

        # Get transcript text at this position
        text = self.transcript_manager.get_text_at_timestamp(timestamp_seconds, context_seconds=30)

        if text:
            progress_sec = timestamp_seconds
            timestamp_str = f"{int(progress_sec // 60)}:{int(progress_sec % 60):02d}"

            print(f"\n{'=' * 60}")
            print(f"Transcript at {timestamp_str}:")
            print(f"{'=' * 60}")
            print(f"\n{text}\n")
            print(f"{'=' * 60}\n")
        else:
            print(f"\n⚠️  No transcript found at current position")

    def handle_download(self, args: str = ""):
        """Download podcast episode audio from RSS feed."""
        status = self.spotify.get_playback_status()

        # If no args, download current episode
        if not args:
            if not status.get("is_podcast") or not status.get("name"):
                print("\n⚠️  Not currently playing a podcast")
                print("   Usage: download SHOW_NAME EPISODE_TITLE\n")
                return

            show_name = status.get("show", "")
            episode_title = status.get("name", "")

            print(f"\nDownloading current episode:")
            print(f"  Show: {show_name}")
            print(f"  Episode: {episode_title}\n")
        else:
            # Parse manual show/episode from args
            parts = args.split(maxsplit=1)
            if len(parts) < 2:
                print("\n⚠️  Usage: download SHOW_NAME EPISODE_TITLE\n")
                return
            show_name, episode_title = parts

        # Download
        filepath = self.rss_manager.find_and_download_episode(show_name, episode_title)

        if filepath:
            print(f"\n✓ Download complete!")
            print(f"  File: {filepath}\n")
        else:
            print(f"\n✗ Download failed\n")

    def handle_speak(self, text: str):
        """Generate speech using a cloned voice. Usage: speak [SPEAKER_ID] TEXT"""
        if not text:
            print("\n⚠️  Usage: speak [SPEAKER_ID] TEXT")
            print("   Example: speak Speaker_0 Hello world")
            print("   Or just: speak Hello world (uses first available speaker)\n")
            return

        if not self.current_voice_ids:
            print("\n⚠️  No voice clones available")
            print("   Voice cloning requires:")
            print("   1. A podcast to be playing")
            print("   2. ElevenLabs API key configured")
            print("   3. Successful audio download and voice clone creation\n")
            return

        # Check if first word is a speaker ID
        parts = text.split(maxsplit=1)
        speaker_id = None
        actual_text = text

        if len(parts) >= 2 and parts[0] in self.current_voice_ids:
            speaker_id = parts[0]
            actual_text = parts[1]
        else:
            # Use first available speaker
            speaker_id = list(self.current_voice_ids.keys())[0]

        voice_id = self.current_voice_ids[speaker_id]

        print(f"\n🔊 Generating speech with {speaker_id}...")

        # Generate filename
        output_dir = Path(__file__).parent / "generated_speech"
        output_dir.mkdir(exist_ok=True)

        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"speech_{speaker_id}_{timestamp}.mp3"

        # Generate speech
        result = self.voice_cloner.generate_speech(
            text=actual_text,
            voice_id=voice_id,
            output_path=output_file
        )

        if result:
            print(f"\n✓ Speech generated successfully!")
            print(f"  Speaker: {speaker_id}")
            print(f"  Play with: open \"{result}\"\n")
        else:
            print(f"\n✗ Speech generation failed\n")

    def save_transcription_log(self, text: str, podcast_context: dict, podcast_transcript: Optional[str] = None):
        """Save transcription with podcast context to a log file."""
        import datetime
        from pathlib import Path

        log_file = Path(__file__).parent / "transcriptions.log"

        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_entry = f"""
[{timestamp_str}]
Show: {podcast_context['show']}
Episode: {podcast_context['episode']}
Timestamp: {podcast_context['timestamp']} / {podcast_context['total_time']}
"""

        if podcast_transcript:
            log_entry += f"Podcast Context: {podcast_transcript}\n"

        log_entry += f"Your Speech: {text}\n"
        log_entry += f"{'=' * 60}\n"

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
            print(f"💾 Saved to {log_file.name}")
        except Exception as e:
            print(f"⚠️  Could not save to log: {e}")

    def run(self):
        """Run the interactive CLI."""
        print("""
===============================================================
          Spotify Podcast Controller - CLI Mode
===============================================================

Commands:
  pause, p          - Pause playback
  resume, r         - Resume playback
  status, s         - Show playback status
  talk, t           - Record and transcribe speech (pauses Spotify)
  transcript, tr    - Show transcript at current position
  load VIDEO_ID     - Manually load YouTube transcript by video ID
  download [ARGS]   - Download current/specified episode audio from RSS
  speak [SPEAKER] TEXT - Generate speech with cloned voice (e.g. speak Speaker_0 Hi)
  quit, q           - Exit application

""")

        # Show initial status
        self.show_status()

        # Try to load transcript for current episode
        print("\n" + "=" * 60)
        self.load_current_transcript()
        print("=" * 60 + "\n")

        # Setup voice cloning (download audio + create clone)
        self.setup_voice_clone()

        while True:
            try:
                command = input(">> ").strip().lower()

                if command in ['pause', 'p']:
                    print("Pausing playback...")
                    if self.spotify.pause():
                        print("✓ Paused\n")
                    else:
                        print("✗ Failed to pause\n")

                elif command in ['resume', 'r', 'play']:
                    print("Resuming playback...")
                    if self.spotify.resume():
                        print("✓ Playing\n")
                    else:
                        print("✗ Failed to resume\n")

                elif command in ['status', 's']:
                    self.show_status()

                elif command in ['talk', 't']:
                    self.handle_talk()

                elif command in ['transcript', 'tr']:
                    self.handle_transcript()

                elif command.startswith('load '):
                    video_id = command.split(' ', 1)[1].strip()
                    self.handle_load_transcript(video_id)

                elif command == 'download' or command.startswith('download '):
                    args = command[8:].strip() if len(command) > 8 else ""
                    self.handle_download(args)

                elif command.startswith('speak '):
                    text = command[6:].strip()
                    self.handle_speak(text)

                elif command in ['quit', 'q', 'exit']:
                    print("\nGoodbye!")
                    break

                elif command == '':
                    continue

                else:
                    print(f"Unknown command: '{command}'")
                    print("Try: pause, resume, status, talk, transcript, download, speak, or quit\n")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except EOFError:
                print("\n\nGoodbye!")
                break


def main():
    """Main entry point."""
    controller = PodcastController()

    # Setup and authenticate
    if not controller.setup():
        print("\nSetup failed. Please fix the issues above and try again.")
        sys.exit(1)

    try:
        # Run the controller
        controller.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main()
