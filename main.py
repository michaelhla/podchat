#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spotify Podcast Controller - Main Entry Point
Control Spotify podcast playback with keyboard shortcuts.
"""

import sys
from pynput import keyboard
from spotify_client import SpotifyClient
from config import Config


class PodcastController:
    """Main controller that integrates Spotify client with keyboard controls."""

    def __init__(self):
        self.spotify = None
        self.listener = None

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
        print("Authentication successful! Tokens saved.")

        return True

    def on_key_press(self, key):
        """
        Handle keyboard press events.

        Keyboard shortcuts:
        - F7: Pause
        - F8: Resume
        - F9: Show current playback status
        - Esc: Exit
        """
        try:
            # Debug: print all key presses
            print(f"\n[DEBUG] Key pressed: {key}")

            # Check for function keys
            if key == keyboard.Key.f7:
                print("[F7] Pausing playback...")
                result = self.spotify.pause()
                print(f"[DEBUG] Pause result: {result}")

            elif key == keyboard.Key.f8:
                print("[F8] Resuming playback...")
                result = self.spotify.resume()
                print(f"[DEBUG] Resume result: {result}")

            elif key == keyboard.Key.f9:
                print("[F9] Checking playback status...")
                self.show_status()

            elif key == keyboard.Key.esc:
                print("[ESC] Exiting...")
                return False  # Stop listener

        except AttributeError:
            # Key doesn't have a special name
            pass

    def show_status(self):
        """Display current playback status."""
        status = self.spotify.get_playback_status()

        if not status["is_playing"] and status["name"] is None:
            print("  �  Nothing is currently playing")
            return

        if status["is_podcast"]:
            playing_icon = "�" if status["is_playing"] else "�"
            print(f"  {playing_icon}  Podcast: {status['name']}")
            print(f"     Show: {status['show']}")

            if status.get("progress_ms") and status.get("duration_ms"):
                progress = status["progress_ms"] / 1000
                duration = status["duration_ms"] / 1000
                progress_str = f"{int(progress // 60)}:{int(progress % 60):02d}"
                duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}"
                print(f"     Time: {progress_str} / {duration_str}")
        else:
            playing_icon = "�" if status["is_playing"] else "�"
            print(f"  {playing_icon}  Track: {status['name']}")
            if status.get("artist"):
                print(f"     Artist: {status['artist']}")

    def run(self):
        """Start the keyboard listener and run the controller."""
        print("""
TPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPW
Q          Spotify Podcast Controller - Running                  Q
ZPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP]

Keyboard shortcuts:
  F7  - Pause playback
  F8  - Resume playback
  F9  - Show playback status
  ESC - Exit application

Listening for keyboard input...
""")

        # Show initial status
        self.show_status()

        # Start listening to keyboard
        with keyboard.Listener(on_press=self.on_key_press) as listener:
            self.listener = listener
            listener.join()

        print("\nGoodbye!")


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
