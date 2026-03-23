# Nova Voice ✨

A voice assistant app with wake word detection and OpenClaw gateway integration.

## Features

- **Wake Word Detection** - Say "Hey Nova" to activate (uses Vosk offline speech recognition)
- **Speech-to-Text** - Converts your voice to text
- **OpenClaw Gateway Integration** - Connects to your OpenClaw gateway via WebSocket
- **Text-to-Speech** - Responds with Natasha voice (Edge TTS)
- **Foreground Service** - Keeps listening even when the app is backgrounded (Android)
- **Modern UI** - Built with KivyMD Material Design

## Requirements

- Python 3.10+
- KivyMD
- Vosk (offline speech recognition)
- Kivymd
- Buildozer (for APK build)

## Quick Start (Development)

```bash
# Install dependencies
pip install -r requirements.txt

# Run on desktop
python main.py
```

## Building APK

### Local Build

```bash
# Install buildozer
pip install buildozer

# Build debug APK
buildozer android debug

# Build release APK
buildozer android release
```

### GitHub Actions Build

1. Push changes to GitHub
2. Go to Actions tab
3. Run the "Build Android APK" workflow
4. Download the APK artifact

## Configuration

Edit `config.json` to set your OpenClaw gateway settings:

```json
{
  "gateway_host": "192.168.1.100",
  "gateway_port": 18789,
  "wake_word": "nova"
}
```

## Usage

1. Launch the app
2. Grant microphone permissions
3. Say "Hey Nova" to activate
4. Speak your command
5. Nova will respond with voice

## Android Permissions

The app requires:
- Microphone access
- Foreground service (to keep listening)
- Wake lock (to prevent sleep while active)

## License

MIT