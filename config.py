"""
Configuration management for Spotify podcast controller.
Loads credentials from environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


class Config:
    """Configuration class for Spotify credentials and settings."""

    # Spotify API credentials
    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

    # YouTube API credentials (optional)
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

    # ElevenLabs API credentials (optional)
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

    # Token storage
    TOKEN_FILE = Path(__file__).parent / ".spotify_tokens.json"

    @classmethod
    def validate(cls) -> bool:
        """
        Validate that required configuration is present.

        Returns:
            True if configuration is valid, False otherwise
        """
        if not cls.SPOTIFY_CLIENT_ID:
            print("Error: SPOTIFY_CLIENT_ID not set in environment")
            return False

        if not cls.SPOTIFY_CLIENT_SECRET:
            print("Error: SPOTIFY_CLIENT_SECRET not set in environment")
            return False

        return True

    @classmethod
    def print_setup_instructions(cls):
        """Print instructions for setting up credentials."""
        print("""
╔═══════════════════════════════════════════════════════════════╗
║          Spotify Podcast Controller - Setup Required          ║
╚═══════════════════════════════════════════════════════════════╝

To use this application, you need to:

1. Create a Spotify App:
   • Go to https://developer.spotify.com/dashboard
   • Log in with your Spotify account
   • Click "Create app"
   • Fill in the details:
     - App name: "Podcast Controller" (or any name)
     - App description: "Control podcast playback"
     - Redirect URI: http://localhost:8888/callback
     - API: Select "Web API"
   • Save the app

2. Get your credentials:
   • Click on your app in the dashboard
   • Click "Settings"
   • Copy your Client ID and Client Secret

3. Create a .env file:
   • Copy .env.example to .env
   • Add your credentials:
     SPOTIFY_CLIENT_ID=your_client_id_here
     SPOTIFY_CLIENT_SECRET=your_client_secret_here

4. Run the application again!

Note: You need Spotify Premium to control playback.
""")
