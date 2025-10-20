"""
ElevenLabs Voice Cloning Integration
Handles voice cloning from podcast audio files.
"""

from typing import Optional, List
from pathlib import Path
from elevenlabs.client import ElevenLabs
import os


class VoiceCloner:
    """Manages ElevenLabs voice cloning operations."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize ElevenLabs client.

        Args:
            api_key: ElevenLabs API key (optional, can use env var)
        """
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")

        if not self.api_key:
            print("⚠️  Warning: No ElevenLabs API key found")
            print("   Set ELEVENLABS_API_KEY in .env to use voice cloning")
            self.client = None
        else:
            try:
                self.client = ElevenLabs(api_key=self.api_key)
                print("✓ ElevenLabs client initialized")
            except Exception as e:
                print(f"⚠️  Could not initialize ElevenLabs client: {e}")
                self.client = None

    def create_voice_clone(self, name: str, audio_files: List[Path],
                          description: Optional[str] = None,
                          remove_background_noise: bool = True) -> Optional[str]:
        """
        Create a voice clone from audio files using Instant Voice Cloning.

        Args:
            name: Name for the voice clone
            audio_files: List of audio file paths (MP3 recommended)
            description: Optional description of the voice
            remove_background_noise: Whether to remove background noise

        Returns:
            voice_id if successful, None otherwise
        """
        if not self.client:
            print("⚠️  ElevenLabs client not available")
            return None

        if not audio_files:
            print("⚠️  No audio files provided")
            return None

        # Validate files exist
        valid_files = []
        for file_path in audio_files:
            if not file_path.exists():
                print(f"⚠️  File not found: {file_path}")
            else:
                valid_files.append(str(file_path))

        if not valid_files:
            print("⚠️  No valid audio files found")
            return None

        try:
            print(f"\n🎙️  Creating voice clone: {name}")
            print(f"   Files: {len(valid_files)}")
            if description:
                print(f"   Description: {description}")

            # Open files as binary for upload
            file_handles = []
            for file_path in valid_files:
                file_handles.append(open(file_path, 'rb'))

            try:
                # Create voice clone using IVC
                voice = self.client.voices.ivc.create(
                    name=name,
                    description=description,
                    files=file_handles,
                    remove_background_noise=remove_background_noise
                )
            finally:
                # Close all file handles
                for fh in file_handles:
                    fh.close()

            voice_id = voice.voice_id
            requires_verification = getattr(voice, 'requires_verification', False)

            print(f"✓ Voice clone created!")
            print(f"  Voice ID: {voice_id}")

            if requires_verification:
                print(f"  ⚠️  Note: Voice requires verification before use")

            return voice_id

        except Exception as e:
            print(f"✗ Failed to create voice clone: {e}")
            return None

    def list_voices(self):
        """List all available voices including clones."""
        if not self.client:
            print("⚠️  ElevenLabs client not available")
            return

        try:
            voices = self.client.voices.get_all()

            print("\n🎙️  Available Voices:")
            for voice in voices.voices:
                voice_type = "Clone" if hasattr(voice, 'category') and voice.category == 'cloned' else "Preset"
                print(f"  - {voice.name} ({voice_type})")
                print(f"    ID: {voice.voice_id}")

        except Exception as e:
            print(f"✗ Failed to list voices: {e}")

    def delete_voice(self, voice_id: str) -> bool:
        """
        Delete a voice clone.

        Args:
            voice_id: ID of the voice to delete

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            print("⚠️  ElevenLabs client not available")
            return False

        try:
            self.client.voices.delete(voice_id)
            print(f"✓ Voice {voice_id} deleted")
            return True
        except Exception as e:
            print(f"✗ Failed to delete voice: {e}")
            return False

    def generate_speech(self, text: str, voice_id: str, output_path: Optional[Path] = None) -> Optional[Path]:
        """
        Generate speech using a cloned voice.

        Args:
            text: Text to convert to speech
            voice_id: ID of the voice to use
            output_path: Where to save the audio (optional)

        Returns:
            Path to generated audio file or None
        """
        if not self.client:
            print("⚠️  ElevenLabs client not available")
            return None

        try:
            print(f"\n🔊 Generating speech with voice {voice_id}...")

            # Generate audio using text_to_speech
            audio = self.client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id="eleven_multilingual_v2"
            )

            # Save to file if path provided
            if output_path:
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, 'wb') as f:
                    for chunk in audio:
                        f.write(chunk)

                print(f"✓ Audio saved to: {output_path}")
                return output_path
            else:
                # Return generator for streaming
                return audio

        except Exception as e:
            print(f"✗ Failed to generate speech: {e}")
            return None


# Test function
def test_voice_cloner():
    """Test the voice cloner."""
    cloner = VoiceCloner()

    if cloner.client:
        # List existing voices
        cloner.list_voices()

        # Test would require actual audio files
        print("\nTo test voice cloning:")
        print("1. Download a podcast episode using the RSS manager")
        print("2. Call create_voice_clone() with the audio file path")
    else:
        print("\nCannot test without API key")
        print("Set ELEVENLABS_API_KEY in your .env file")


if __name__ == "__main__":
    test_voice_cloner()
