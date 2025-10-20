"""
Spotify API client for controlling podcast playback.
Handles authentication and playback control methods.
"""

import requests
import json
import time
from typing import Optional, Dict, Any
from urllib.parse import urlencode
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading


class SpotifyClient:
    """Client for interacting with Spotify Web API to control podcast playback."""

    AUTH_URL = "https://accounts.spotify.com/authorize"
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    API_BASE_URL = "https://api.spotify.com/v1"
    REDIRECT_URI = "http://127.0.0.1:8889/callback"
    SCOPES = "user-modify-playback-state user-read-playback-state user-read-currently-playing"

    def __init__(self, client_id: str, client_secret: str, access_token: Optional[str] = None,
                 refresh_token: Optional[str] = None):
        """
        Initialize Spotify client.

        Args:
            client_id: Spotify app client ID
            client_secret: Spotify app client secret
            access_token: Optional existing access token
            refresh_token: Optional existing refresh token
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expiry = 0

    def authenticate(self) -> bool:
        """
        Perform OAuth authentication flow to get access token.
        Opens browser for user authorization.

        Returns:
            True if authentication successful, False otherwise
        """
        # If we have a valid token, no need to re-authenticate
        if self.access_token and time.time() < self.token_expiry:
            return True

        # If we have a refresh token, try to refresh
        if self.refresh_token:
            if self._refresh_access_token():
                return True

        # Otherwise, start new OAuth flow
        auth_params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.REDIRECT_URI,
            "scope": self.SCOPES
        }

        auth_url = f"{self.AUTH_URL}?{urlencode(auth_params)}"
        print(f"Opening browser for authentication...")
        print(f"If browser doesn't open, visit: {auth_url}")
        webbrowser.open(auth_url)

        # Start local server to receive callback
        auth_code = self._wait_for_callback()

        if not auth_code:
            print("Failed to receive authorization code")
            return False

        # Exchange authorization code for access token
        return self._get_access_token(auth_code)

    def _wait_for_callback(self) -> Optional[str]:
        """Start a local server to receive the OAuth callback."""
        auth_code = [None]  # Use list to allow modification in nested function

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                # Extract code from query parameters
                if "code=" in self.path:
                    code = self.path.split("code=")[1].split("&")[0]
                    auth_code[0] = code

                    # Send response to browser
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<html><body><h1>Authentication successful!</h1><p>You can close this window.</p></body></html>")
                else:
                    self.send_response(400)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<html><body><h1>Authentication failed</h1></body></html>")

            def log_message(self, format, *args):
                pass  # Suppress server logs

        server = HTTPServer(("127.0.0.1", 8889), CallbackHandler)

        # Wait for callback (with timeout)
        timeout = 120  # 2 minutes
        start_time = time.time()

        while auth_code[0] is None and (time.time() - start_time) < timeout:
            server.handle_request()

        return auth_code[0]

    def _get_access_token(self, auth_code: str) -> bool:
        """Exchange authorization code for access token."""
        token_data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": self.REDIRECT_URI,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        response = requests.post(self.TOKEN_URL, data=token_data)

        if response.status_code == 200:
            token_info = response.json()
            self.access_token = token_info["access_token"]
            self.refresh_token = token_info.get("refresh_token")
            self.token_expiry = time.time() + token_info.get("expires_in", 3600)
            print("Authentication successful!")
            return True
        else:
            print(f"Failed to get access token: {response.status_code}")
            print(response.text)
            return False

    def _refresh_access_token(self) -> bool:
        """Refresh the access token using refresh token."""
        if not self.refresh_token:
            return False

        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        response = requests.post(self.TOKEN_URL, data=token_data)

        if response.status_code == 200:
            token_info = response.json()
            self.access_token = token_info["access_token"]
            self.token_expiry = time.time() + token_info.get("expires_in", 3600)
            # Refresh token may or may not be included
            if "refresh_token" in token_info:
                self.refresh_token = token_info["refresh_token"]
            return True
        else:
            return False

    def _ensure_authenticated(self):
        """Ensure we have a valid access token, refresh if needed."""
        if time.time() >= self.token_expiry - 60:  # Refresh if expiring in 1 minute
            if self.refresh_token:
                self._refresh_access_token()

    def _make_api_request(self, method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
        """
        Make an authenticated API request to Spotify.

        Args:
            method: HTTP method (GET, PUT, POST, etc.)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments to pass to requests

        Returns:
            Response object or None if request failed
        """
        self._ensure_authenticated()

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        url = f"{self.API_BASE_URL}{endpoint}"

        try:
            print(f"🔍 DEBUG: {method} {url}")
            response = requests.request(method, url, headers=headers, timeout=10, **kwargs)
            print(f"🔍 DEBUG: Status code: {response.status_code}")
            return response
        except requests.exceptions.Timeout as e:
            print(f"⚠ API request timed out: {e}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"⚠ API request failed: {e}")
            return None

    def get_current_playback(self) -> Optional[Dict[str, Any]]:
        """
        Get information about current playback.

        Returns:
            Dictionary with playback information or None
        """
        response = self._make_api_request("GET", "/me/player/currently-playing?type=episode,track")

        if response and response.status_code == 200:
            return response.json()
        elif response and response.status_code == 204:
            print("No playback currently active")
            return None
        else:
            print(f"Failed to get playback info: {response.status_code if response else 'No response'}")
            return None

    def pause(self) -> bool:
        """
        Pause current playback.

        Returns:
            True if successful, False otherwise
        """
        response = self._make_api_request("PUT", "/me/player/pause")

        if response and response.status_code in [200, 204]:
            print("Playback paused")
            return True
        elif response and response.status_code == 403:
            print("Error: Requires Spotify Premium")
            return False
        else:
            print(f"Failed to pause: {response.status_code if response else 'No response'}")
            if response:
                print(response.text)
            return False

    def resume(self, device_id: Optional[str] = None) -> bool:
        """
        Resume current playback.

        Args:
            device_id: Optional device ID to resume on (currently unused)

        Returns:
            True if successful, False otherwise
        """
        print(f"🔍 DEBUG: Making API request to /me/player/play")

        # Simple resume without device_id (let Spotify use default device)
        response = self._make_api_request("PUT", "/me/player/play")
        print(f"🔍 DEBUG: Response object: {response}")

        if response and response.status_code in [200, 204]:
            print("Playback resumed")
            return True
        elif response and response.status_code == 403:
            print("Error: Requires Spotify Premium")
            return False
        elif response and response.status_code == 404:
            print("⚠ No active device found - Spotify may have gone inactive")
            print("   Please manually resume playback on your Spotify app")
            return False
        else:
            print(f"Failed to resume: {response.status_code if response else 'No response'}")
            if response:
                print(f"Response text: {response.text}")
            else:
                print("⚠ API request returned None - possible network/auth issue")
            return False

    def is_podcast_playing(self) -> bool:
        """
        Check if currently playing media is a podcast episode.

        Returns:
            True if a podcast is playing, False otherwise
        """
        playback = self.get_current_playback()

        if not playback:
            return False

        currently_playing_type = playback.get("currently_playing_type")
        return currently_playing_type == "episode"

    def get_playback_status(self) -> Dict[str, Any]:
        """
        Get detailed playback status including what's playing and whether it's paused.

        Returns:
            Dictionary with status information
        """
        playback = self.get_current_playback()

        if not playback:
            return {
                "is_playing": False,
                "is_podcast": False,
                "name": None,
                "show": None
            }

        is_episode = playback.get("currently_playing_type") == "episode"
        is_playing = playback.get("is_playing", False)

        # Capture device ID for later resume
        device_id = None
        if playback.get("device"):
            device_id = playback["device"].get("id")

        if is_episode:
            item = playback.get("item", {})
            return {
                "is_playing": is_playing,
                "is_podcast": True,
                "name": item.get("name"),
                "show": item.get("show", {}).get("name"),
                "progress_ms": playback.get("progress_ms"),
                "duration_ms": item.get("duration_ms"),
                "device_id": device_id
            }
        else:
            item = playback.get("item", {})
            return {
                "is_playing": is_playing,
                "is_podcast": False,
                "name": item.get("name"),
                "artist": item.get("artists", [{}])[0].get("name") if item.get("artists") else None,
                "device_id": device_id
            }

    def save_tokens(self, filepath: str):
        """Save access and refresh tokens to a file."""
        tokens = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_expiry": self.token_expiry
        }
        with open(filepath, "w") as f:
            json.dump(tokens, f)

    def load_tokens(self, filepath: str) -> bool:
        """Load access and refresh tokens from a file."""
        try:
            with open(filepath, "r") as f:
                tokens = json.load(f)
                self.access_token = tokens.get("access_token")
                self.refresh_token = tokens.get("refresh_token")
                self.token_expiry = tokens.get("token_expiry", 0)
                return True
        except (FileNotFoundError, json.JSONDecodeError):
            return False
