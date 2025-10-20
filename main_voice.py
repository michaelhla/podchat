#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spotify Podcast Controller - Voice-Activated Version
Automatically pauses Spotify when you speak, resumes when you stop.
"""

import sys
import time
from spotify_client import SpotifyClient
from voice_detector import VoiceActivityDetector
from config import Config


class VoiceActivatedController:
    """Controller that pauses Spotify when voice is detected."""

    def __init__(self):
        self.spotify = None
        self.voice_detector = None
        self.was_playing_before_speech = False

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
        print("Authentication successful!\n")

        return True

    def on_speech_start(self):
        """Called when user starts speaking."""
        print("\n[🎤 SPEAKING] Pausing Spotify...")

        # Check if something is currently playing
        status = self.spotify.get_playback_status()
        self.was_playing_before_speech = status.get("is_playing", False)

        if self.was_playing_before_speech:
            self.spotify.pause()
            print("✓ Paused")
        else:
            print("(Nothing was playing)")

    def on_speech_end(self):
        """Called when user stops speaking."""
        print("\n[🔇 SILENCE] Resuming Spotify...")

        # Only resume if we paused it
        if self.was_playing_before_speech:
            self.spotify.resume()
            print("✓ Resumed")
            self.was_playing_before_speech = False
        else:
            print("(Not resuming - wasn't playing before)")

    def run(self):
        """Start voice detection and run the controller."""
        print("""
╔═══════════════════════════════════════════════════════════════╗
║      Spotify Podcast Controller - Voice-Activated Mode        ║
╚═══════════════════════════════════════════════════════════════╝

How it works:
  • When you start speaking → Spotify pauses
  • When you stop speaking → Spotify resumes
  • Press Ctrl+C to exit

Settings:
  • Aggressiveness: 3 (high - only clear speech detected)
  • Silence duration before resume: 500ms

""")

        # Show what's currently playing
        status = self.spotify.get_playback_status()
        if status.get("is_playing"):
            if status.get("is_podcast"):
                print(f"Currently playing: {status['name']}")
                print(f"Show: {status['show']}\n")
            else:
                print(f"Currently playing: {status['name']}")
                if status.get("artist"):
                    print(f"Artist: {status['artist']}\n")
        else:
            print("Nothing is currently playing.\n")

        # Initialize voice detector
        self.voice_detector = VoiceActivityDetector(
            sample_rate=16000,
            aggressiveness=3,  # High aggressiveness = less sensitive, only clear speech
            padding_duration_ms=500,  # 500ms of silence before resuming (increased delay)
            speech_start_callback=self.on_speech_start,
            speech_end_callback=self.on_speech_end
        )

        try:
            # Start voice detection
            self.voice_detector.start()

            print("Ready! Start playing something on Spotify and try speaking.\n")

            # Keep running
            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            print("\n\nStopping...")
        finally:
            if self.voice_detector:
                self.voice_detector.cleanup()
            print("Goodbye!")


def main():
    """Main entry point."""
    controller = VoiceActivatedController()

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
