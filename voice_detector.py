"""
Voice Activity Detector using WebRTC VAD and PyAudio.
Detects when the user is speaking through the microphone.
"""

import collections
import pyaudio
import webrtcvad
import time
from typing import Callable, Optional
import threading


class VoiceActivityDetector:
    """Real-time voice activity detector using microphone input."""

    def __init__(self,
                 sample_rate: int = 16000,
                 frame_duration_ms: int = 30,
                 aggressiveness: int = 2,
                 speech_start_callback: Optional[Callable] = None,
                 speech_end_callback: Optional[Callable] = None,
                 padding_duration_ms: int = 300):
        """
        Initialize Voice Activity Detector.

        Args:
            sample_rate: Audio sample rate (8000, 16000, or 32000 Hz)
            frame_duration_ms: Frame duration in ms (10, 20, or 30)
            aggressiveness: VAD aggressiveness (0-3, higher = more aggressive)
            speech_start_callback: Function to call when speech starts
            speech_end_callback: Function to call when speech ends
            padding_duration_ms: Duration of silence before triggering speech_end
        """
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.aggressiveness = aggressiveness
        self.speech_start_callback = speech_start_callback
        self.speech_end_callback = speech_end_callback

        # Calculate frame size in bytes
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        self.frame_bytes = self.frame_size * 2  # 16-bit = 2 bytes per sample

        # Padding: Number of frames to keep before/after speech
        self.padding_frames = int(padding_duration_ms / frame_duration_ms)

        # Initialize WebRTC VAD
        self.vad = webrtcvad.Vad(aggressiveness)

        # Initialize PyAudio
        self.audio = pyaudio.PyAudio()
        self.stream = None

        # State tracking
        self.is_speaking = False
        self.ring_buffer = collections.deque(maxlen=self.padding_frames)
        self.triggered = False

        # Threading
        self.running = False
        self.thread = None

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for audio stream (not used in blocking mode)."""
        return (in_data, pyaudio.paContinue)

    def start(self):
        """Start listening for voice activity."""
        if self.running:
            print("Voice detector already running")
            return

        try:
            # Open audio stream
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.frame_size,
            )

            self.running = True
            self.thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.thread.start()
            print(f"Voice detector started (sample_rate={self.sample_rate}Hz, aggressiveness={self.aggressiveness})")

        except Exception as e:
            print(f"Error starting voice detector: {e}")
            self.running = False

    def _listen_loop(self):
        """Main listening loop that processes audio frames."""
        print("Listening for voice activity...")

        while self.running:
            try:
                # Read audio frame
                frame = self.stream.read(self.frame_size, exception_on_overflow=False)

                # Check if frame contains speech
                is_speech = self.vad.is_speech(frame, self.sample_rate)

                if not self.triggered:
                    # Not currently in speech segment
                    self.ring_buffer.append((frame, is_speech))
                    num_voiced = len([f for f, speech in self.ring_buffer if speech])

                    # If more than 90% of frames in buffer are speech, trigger
                    if num_voiced > 0.9 * self.ring_buffer.maxlen:
                        self.triggered = True
                        self.is_speaking = True
                        print("[VOICE] Speech started")
                        if self.speech_start_callback:
                            self.speech_start_callback()
                        self.ring_buffer.clear()
                else:
                    # Currently in speech segment
                    self.ring_buffer.append((frame, is_speech))
                    num_unvoiced = len([f for f, speech in self.ring_buffer if not speech])

                    # If more than 90% of frames in buffer are silence, end speech
                    if num_unvoiced > 0.9 * self.ring_buffer.maxlen:
                        self.triggered = False
                        self.is_speaking = False
                        print("[VOICE] Speech ended")
                        if self.speech_end_callback:
                            self.speech_end_callback()
                        self.ring_buffer.clear()

            except Exception as e:
                print(f"Error in voice detection loop: {e}")
                time.sleep(0.1)

    def stop(self):
        """Stop listening for voice activity."""
        if not self.running:
            return

        print("Stopping voice detector...")
        self.running = False

        if self.thread:
            self.thread.join(timeout=2.0)

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()

        print("Voice detector stopped")

    def cleanup(self):
        """Clean up resources."""
        self.stop()
        if self.audio:
            self.audio.terminate()

    def is_currently_speaking(self) -> bool:
        """
        Check if currently detecting speech.

        Returns:
            True if speech is currently detected, False otherwise
        """
        return self.is_speaking


# Example usage
if __name__ == "__main__":
    def on_speech_start():
        print(">>> User started speaking!")

    def on_speech_end():
        print(">>> User stopped speaking!")

    detector = VoiceActivityDetector(
        speech_start_callback=on_speech_start,
        speech_end_callback=on_speech_end
    )

    try:
        detector.start()
        print("Speak into your microphone. Press Ctrl+C to exit.")

        # Keep running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        detector.cleanup()
