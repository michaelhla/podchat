# PodChat Integration - Voice Cloned Podcast Hosts

## What We Built

An interactive podcast chat system where you can talk to podcast hosts and they respond using their cloned voices!

## How It Works

### 1. Setup (Automatic on startup)
When you run `python3 main_cli.py` while listening to a podcast:

1. **Downloads the episode** from RSS feed
2. **Extracts first 20 minutes** for speaker analysis
3. **Uses ElevenLabs Scribe** to identify speakers with 96.7% accuracy
4. **Extracts 5 minutes of audio** per speaker from longest continuous blocks
5. **Creates voice clones** for both podcast hosts
6. **Ready for interaction!**

### 2. Talk Command (`talk` or `t`)
When you press the talk button:

1. **Pauses Spotify** automatically
2. **Records your voice** and transcribes it
3. **Generates a response** from the podcast hosts using Claude
4. **Synthesizes speech** using the cloned voices
5. **Plays the response** automatically
6. **Resumes Spotify**

## New Features Added

### Scribe Diarization
- Replaces unreliable YouTube >> markers
- Word-level speaker identification
- 96.7% accuracy for English
- Cost: ~$0.05 per 20-minute segment

### Voice Clone Response System
- Uses Claude 3.5 Sonnet to generate contextual responses
- Picks a random host to respond
- Considers what the podcast was saying at that moment
- Plays audio automatically through speakers

## Requirements

### API Keys (in .env)
```bash
ELEVENLABS_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
SPOTIFY_CLIENT_ID=your_id_here
SPOTIFY_CLIENT_SECRET=your_secret_here
YOUTUBE_API_KEY=your_key_here  # Optional, for transcripts
```

### ElevenLabs Subscription
- **Minimum**: Starter plan ($5/month) for Instant Voice Cloning
- Includes 30,000 credits/month

### Python Dependencies
```bash
pip3 install -r requirements.txt
```

New dependencies:
- `anthropic>=0.18.0` - Claude API for response generation
- `pydub>=0.25.1` - Audio manipulation and playback

## Usage

### Start the system:
```bash
python3 main_cli.py
```

### Commands:
- `talk` or `t` - Talk to the podcast hosts (they respond!)
- `pause` or `p` - Pause playback
- `resume` or `r` - Resume playback
- `status` or `s` - Show current status
- `transcript` - Show transcript at current position
- `speak SPEAKER_ID TEXT` - Make a specific host say something
- `quit` or `q` - Exit

## Example Flow

```
>> t
[Records your voice]
📝 You said: "Wait, can you explain that Google acquisition again?"

🎤 PODCAST HOSTS RESPONDING...
💬 Hosts: "Sure! So back in 2004, Google bought this little startup
         called Keyhole, which became Google Earth. It was a pivotal
         moment in their mapping strategy."

🔊 Generating speech with speaker_0...
✓ Response generated! Playing audio...
[Audio plays through speakers]
✓ Playback complete
```

## Technical Details

### Voice Clone Quality
- 5 minutes of audio per speaker
- Prioritizes longest continuous speech blocks
- 192 kbps bitrate for best quality
- Under 11MB file size limit

### Response Generation
- Claude 3.5 Sonnet for natural language
- Context-aware (uses podcast transcript)
- Brief responses (2-3 sentences)
- Conversational podcast tone

### Caching
- Scribe results cached in `.scribe_cache/`
- Voice clones persist in ElevenLabs account
- Downloaded audio in `podcast_audio/`
- Generated responses in `generated_speech/`

## Cost Breakdown

Per episode:
- Scribe diarization: ~$0.05 (one-time, cached)
- Voice clone creation: Free (stays in account)
- Each response: ~$0.01-0.02 (Claude + TTS)

Typical session (10 responses): ~$0.15-0.25 total

## Files Modified

- `main_cli.py` - Main flow with Scribe integration and response system
- `scribe_diarizer.py` - ElevenLabs Scribe API wrapper
- `voice_cloner.py` - Fixed TTS API calls
- `requirements.txt` - Added anthropic SDK
- `test_synthetic_podcast_fast.py` - Test script for 20-min pipeline

## Next Steps

Potential improvements:
- Multi-turn conversations with conversation history
- Automatically detect which host should respond based on context
- Add personality profiles for each host
- Support for more than 2 speakers
- Background noise reduction in recording
- Voice activity detection for automatic talk triggering
