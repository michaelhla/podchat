"""
Speech transcription module using Google Speech Recognition.
Records audio from microphone and converts it to text.
"""

import speech_recognition as sr
from typing import Optional
import time


class SpeechTranscriber:
    """Handles recording and transcribing speech from microphone."""

    def __init__(self):
        """Initialize the speech recognizer."""
        self.recognizer = sr.Recognizer()

        # Adjust these for better recognition
        self.recognizer.energy_threshold = 300  # Minimum audio energy to consider for recording
        self.recognizer.dynamic_energy_threshold = True  # Automatically adjust energy threshold
        self.recognizer.pause_threshold = 0.8  # Seconds of silence to consider end of phrase

        # Store last recorded audio file path for voice-to-voice
        self.last_audio_file = None

    def list_microphones(self):
        """List available microphone devices."""
        print("Available microphones:")
        for index, name in enumerate(sr.Microphone.list_microphone_names()):
            print(f"  [{index}] {name}")

    def transcribe_from_microphone(self, timeout: int = 10, phrase_time_limit: Optional[int] = None) -> Optional[str]:
        """
        Record audio from microphone and transcribe it to text.

        Args:
            timeout: Maximum seconds to wait for speech to start
            phrase_time_limit: Maximum seconds for the phrase (None = no limit)

        Returns:
            Transcribed text or None if transcription failed
        """
        try:
            with sr.Microphone() as source:
                print("🔴 Listening... speak now!")

                # Listen for audio
                try:
                    audio = self.recognizer.listen(
                        source,
                        timeout=timeout,
                        phrase_time_limit=phrase_time_limit
                    )
                    print("⏸  Processing...")
                except sr.WaitTimeoutError:
                    print("⚠️  No speech detected (timeout)")
                    return None

                # Save audio to file for voice-to-voice conversion
                from pathlib import Path
                import tempfile
                temp_dir = Path(tempfile.gettempdir()) / "podchat"
                temp_dir.mkdir(exist_ok=True)

                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                audio_file = temp_dir / f"recording_{timestamp}.wav"

                with open(audio_file, "wb") as f:
                    f.write(audio.get_wav_data())

                self.last_audio_file = audio_file

                # Transcribe using Google Speech Recognition
                try:
                    text = self.recognizer.recognize_google(audio)
                    return text
                except sr.UnknownValueError:
                    print("⚠️  Could not understand audio")
                    return None
                except sr.RequestError as e:
                    print(f"⚠️  Could not request results from Google Speech Recognition; {e}")
                    return None

        except OSError as e:
            print(f"⚠️  Microphone error: {e}")
            print("   Make sure your microphone is connected and you've granted permission.")
            return None
        except Exception as e:
            print(f"⚠️  Unexpected error: {e}")
            return None

    def transcribe_quick(self) -> Optional[str]:
        """
        Quick transcription with shorter timeout (5 seconds).
        Good for short commands or phrases.

        Returns:
            Transcribed text or None if transcription failed
        """
        return self.transcribe_from_microphone(timeout=5, phrase_time_limit=10)

    def transcribe_long(self) -> Optional[str]:
        """
        Longer transcription session (30 seconds max).
        Good for longer messages or paragraphs.

        Returns:
            Transcribed text or None if transcription failed
        """
        return self.transcribe_from_microphone(timeout=10, phrase_time_limit=30)


# Example usage and testing
if __name__ == "__main__":
    print("Speech Transcription Test")
    print("=" * 50)

    transcriber = SpeechTranscriber()

    # List available microphones
    transcriber.list_microphones()
    print()

    # Test transcription
    print("Testing quick transcription...")
    print("Speak something short after the beep!")
    print()

    text = transcriber.transcribe_quick()

    if text:
        print(f"\n✅ Transcription: \"{text}\"")
    else:
        print("\n❌ Transcription failed")
