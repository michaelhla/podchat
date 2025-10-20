# Spotify Podcast Controller

Control Spotify podcast playback with keyboard shortcuts. Built with modularity in mind for future expansion to iOS and other platforms.

## Features

- **Pause/Resume**: Control podcast playback with function keys
- **Status Display**: See what's currently playing
- **Token Management**: Automatic OAuth token refresh
- **Modular Design**: SpotifyClient can be easily integrated into other applications

## Requirements

- Python 3.7+
- Spotify Premium account (required for playback control API)
- Spotify Developer App credentials

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Create a Spotify App

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Log in with your Spotify account
3. Click **"Create app"**
4. Fill in the details:
   - **App name**: "Podcast Controller" (or any name you like)
   - **App description**: "Control podcast playback"
   - **Redirect URI**: `http://127.0.0.1:8888/callback` ⚠️ **Important: Use 127.0.0.1, not localhost**
   - **API**: Select "Web API"
5. Click **Save**

### 3. Get Your Credentials

1. Click on your app in the dashboard
2. Click **"Settings"**
3. Copy your **Client ID** and **Client Secret**

### 4. Configure the Application

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your credentials:
   ```
   SPOTIFY_CLIENT_ID=your_client_id_here
   SPOTIFY_CLIENT_SECRET=your_client_secret_here
   ```

### 5. Run the Application

```bash
python main.py
```

On first run, a browser window will open for you to authorize the application. After authorization, your tokens will be saved locally for future use.

## Usage

### Voice-Activated Mode (Recommended!)

Automatically pauses Spotify when you speak:

```bash
python main_voice.py
```

The app listens to your microphone and:
- **When you start speaking** → Automatically pauses Spotify
- **When you stop speaking** → Automatically resumes playback

Perfect for:
- Taking phone calls
- Having conversations
- Recording audio/video
- Any time you need to interrupt your podcast

### CLI Mode

Manual control via typed commands:

```bash
python main_cli.py
```

Commands:
- `pause` or `p` - Pause playback
- `resume` or `r` - Resume playback
- `status` or `s` - Show what's playing
- `quit` or `q` - Exit

### Keyboard Shortcut Mode

Control with function keys (requires accessibility permissions):

```bash
python main.py
```

Shortcuts:
- **F7** - Pause playback
- **F8** - Resume playback
- **F9** - Show current playback status
- **ESC** - Exit application

## Architecture

The codebase is designed with modularity in mind:

### `spotify_client.py`
Core Spotify API client that handles:
- OAuth 2.0 authentication with automatic token refresh
- Playback control (pause, resume, status)
- Token persistence

This module can be easily imported into other projects (iOS app, web service, etc.)

### `config.py`
Configuration management:
- Loads credentials from environment variables
- Validates configuration
- Provides setup instructions

### `main.py`
Keyboard control layer:
- Listens for keyboard shortcuts
- Calls SpotifyClient methods
- **Easily replaceable** with HTTP endpoints, iOS integration, or other triggers

## Future Extensions

The modular architecture makes it easy to:

- **iOS App**: Import `spotify_client.py` logic into a Swift/Python backend
- **HTTP API**: Replace `main.py` with a Flask/FastAPI server
- **Automation**: Trigger pause/resume based on calendar events, locations, etc.
- **Voice Control**: Integrate with Siri shortcuts or voice assistants

## Notes

- Requires Spotify Premium for playback control
- Tokens are saved locally in `.spotify_tokens.json` (automatically refreshed)
- Works with both podcasts and music, but designed with podcasts in mind

## License

MIT License - Feel free to use and modify for your needs!
