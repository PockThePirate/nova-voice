#!/usr/bin/env python3
"""
Nova Voice - Voice assistant with wake word detection and OpenClaw gateway integration.
Android-compatible version with foreground service for background mic access.
"""

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Optional
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.audio import SoundLoader
from kivy.logger import Logger
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivymd.app import MDApp
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.textfield import MDTextField
from kivymd.uix.toolbar import MDTopAppBar

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    Logger.warning("NovaVoice: websockets not available")

# Android-specific imports
try:
    from jnius import autoclass
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    AudioRecord = autoclass('android.media.AudioRecord')
    MediaRecorder = autoclass('android.media.MediaRecorder')
    AudioSource = autoclass('android.media.MediaRecorder$AudioSource')
    AudioFormat = autoclass('android.media.AudioFormat')
    Context = autoclass('android.content.Context')
    PowerManager = autoclass('android.os.PowerManager')
    ANDROID_AVAILABLE = True
except ImportError:
    ANDROID_AVAILABLE = False
    Logger.warning("NovaVoice: Android APIs not available (running on desktop?)")

# Vosk for wake word
try:
    from vosk import Model, KaldiRecognizer, SetLogLevel
    SetLogLevel(-1)  # Reduce Vosk logging
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    Logger.warning("NovaVoice: Vosk not available, wake word detection disabled")


# Configuration
class Config:
    def __init__(self):
        self.config_path = self._get_config_path()
        self.defaults = {
            "gateway_host": "147.93.113.71",
            "gateway_port": 18789,
            "gateway_token": "",
            "wake_word": "nova",
            "voice": "en-US-AvaNeural",
            "setup_complete": False,
        }
        self.data = self.load()

    def _get_config_path(self) -> Path:
        """Get config path, handling Android storage."""
        try:
            # On Android, use app storage
            if ANDROID_AVAILABLE:
                activity = PythonActivity.mActivity
                files_dir = activity.getFilesDir().getAbsolutePath()
                return Path(files_dir) / "config.json"
        except:
            pass
        return Path(__file__).parent / "config.json"

    def load(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    loaded = json.load(f)
                    return {**self.defaults, **loaded}
            except Exception as e:
                Logger.error(f"NovaVoice: Failed to load config: {e}")
        return self.defaults.copy()

    def save(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            Logger.error(f"NovaVoice: Failed to save config: {e}")

    def get(self, key: str, default=None):
        return self.data.get(key, default if default else self.defaults.get(key))

    def is_configured(self) -> bool:
        return (
            self.data.get("setup_complete", False) and
            bool(self.data.get("gateway_host")) and
            bool(self.data.get("gateway_token"))
        )


config = Config()


class AndroidAudioCapture:
    """Audio capture using Android AudioRecord API."""

    def __init__(self, sample_rate: int = 16000, chunk_size: int = 4096):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.audio_record = None
        self.running = False
        self.audio_callback = None
        self._thread = None
        self._min_buffer_size = 0

    def initialize(self) -> bool:
        """Initialize audio capture."""
        if not ANDROID_AVAILABLE:
            Logger.error("NovaVoice: Android APIs not available")
            return False

        try:
            # Calculate buffer size
            channel_config = AudioFormat.CHANNEL_IN_MONO
            audio_format = AudioFormat.ENCODING_PCM_16BIT

            self._min_buffer_size = AudioRecord.getMinBufferSize(
                self.sample_rate, channel_config, audio_format
            )

            # Create AudioRecord
            self.audio_record = AudioRecord(
                AudioSource.MIC,
                self.sample_rate,
                channel_config,
                audio_format,
                max(self._min_buffer_size, self.chunk_size * 2)
            )

            if self.audio_record.getState() != AudioRecord.STATE_INITIALIZED:
                Logger.error("NovaVoice: AudioRecord not initialized")
                return False

            Logger.info("NovaVoice: Audio capture initialized")
            return True
        except Exception as e:
            Logger.error(f"NovaVoice: Failed to initialize audio: {e}")
            return False

    def start(self):
        """Start capturing audio."""
        if not self.audio_record:
            return

        self.running = True
        self.audio_record.startRecording()

        def capture_loop():
            buffer_size = self.chunk_size * 2  # 16-bit samples
            buffer = bytearray(buffer_size)

            while self.running:
                try:
                    bytes_read = self.audio_record.read(buffer, 0, buffer_size)
                    if bytes_read > 0 and self.audio_callback:
                        # Convert to bytes
                        audio_data = bytes(buffer[:bytes_read])
                        self.audio_callback(audio_data)
                except Exception as e:
                    Logger.error(f"NovaVoice: Audio capture error: {e}")
                    break

        self._thread = threading.Thread(target=capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop capturing audio."""
        self.running = False
        if self.audio_record:
            try:
                self.audio_record.stop()
            except:
                pass

    def close(self):
        """Close audio resources."""
        if self.audio_record:
            try:
                self.audio_record.release()
            except:
                pass
            self.audio_record = None


class DesktopAudioCapture:
    """Fallback audio capture for desktop testing."""

    def __init__(self, sample_rate: int = 16000, chunk_size: int = 4096):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.running = False
        self.audio_callback = None
        self._thread = None

    def initialize(self) -> bool:
        Logger.info("NovaVoice: Using desktop audio (no Android)")
        return True

    def start(self):
        self.running = True
        Logger.info("NovaVoice: Desktop audio capture started (simulated)")

    def stop(self):
        self.running = False

    def close(self):
        pass


class WakeWordDetector:
    """Wake word detection using Vosk offline speech recognition."""

    def __init__(self, wake_word: str = "nova"):
        self.wake_word = wake_word.lower()
        self.model: Optional[Model] = None
        self.recognizer: Optional[KaldiRecognizer] = None
        self.model_path = self._get_model_path()

    def _get_model_path(self) -> Path:
        """Get Vosk model path."""
        # Check for bundled model first
        bundled_model = Path(__file__).parent / "assets" / "vosk-model-small-en-us-0.15"
        if bundled_model.exists():
            return bundled_model

        # Then check app storage (Android)
        if ANDROID_AVAILABLE:
            try:
                activity = PythonActivity.mActivity
                files_dir = activity.getFilesDir().getAbsolutePath()
                app_model = Path(files_dir) / "vosk-model-small-en-us-0.15"
                if app_model.exists():
                    return app_model
            except:
                pass

        # Default location
        model_dir = Path(__file__).parent / "vosk-model-small-en-us-0.15"
        return model_dir

    def initialize(self) -> bool:
        """Initialize the wake word detector."""
        if not VOSK_AVAILABLE:
            Logger.warning("NovaVoice: Vosk not available")
            return False

        if not self.model_path.exists():
            Logger.warning(f"NovaVoice: Vosk model not found at {self.model_path}")
            Logger.info("NovaVoice: Wake word detection disabled")
            return False

        try:
            self.model = Model(str(self.model_path))
            self.recognizer = KaldiRecognizer(self.model, 16000)
            Logger.info("NovaVoice: Wake word detector initialized")
            return True
        except Exception as e:
            Logger.error(f"NovaVoice: Failed to initialize wake word detector: {e}")
            return False

    def process_audio(self, audio_data: bytes) -> bool:
        """Process audio data and check for wake word."""
        if not self.recognizer:
            return False

        try:
            if self.recognizer.AcceptWaveform(audio_data):
                result = json.loads(self.recognizer.Result())
                text = result.get("text", "").lower()
                Logger.debug(f"NovaVoice: Speech: '{text}'")

                if self.wake_word in text:
                    Logger.info(f"NovaVoice: Wake word '{self.wake_word}' detected!")
                    return True
        except Exception as e:
            Logger.error(f"NovaVoice: Wake word processing error: {e}")

        return False

    def reset(self):
        """Reset the recognizer state."""
        if self.model:
            self.recognizer = KaldiRecognizer(self.model, 16000)


class GatewayClient:
    """WebSocket client for OpenClaw gateway."""

    def __init__(self, host: str, port: int, token: str = None):
        self.host = host
        self.port = port
        self.token = token
        self.ws = None
        self.connected = False
        self.message_callback = None
        self._receive_task = None

    async def connect(self) -> bool:
        """Connect to the gateway."""
        if not WEBSOCKETS_AVAILABLE:
            Logger.error("NovaVoice: websockets library not available")
            return False

        try:
            uri = f"ws://{self.host}:{self.port}/ws"
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            self.ws = await websockets.connect(uri, extra_headers=headers, ping_interval=30)
            self.connected = True
            Logger.info(f"NovaVoice: Connected to gateway at {uri}")

            # Start message handler
            self._receive_task = asyncio.create_task(self._receive_loop())
            return True
        except Exception as e:
            Logger.error(f"NovaVoice: Failed to connect to gateway: {e}")
            self.connected = False
            return False

    async def _receive_loop(self):
        """Receive messages from gateway."""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    if self.message_callback:
                        self.message_callback(data)
                except json.JSONDecodeError:
                    Logger.warning(f"NovaVoice: Invalid JSON: {message[:100]}")
        except websockets.exceptions.ConnectionClosed:
            Logger.info("NovaVoice: Gateway connection closed")
            self.connected = False
        except Exception as e:
            Logger.error(f"NovaVoice: Receive error: {e}")
            self.connected = False

    async def send(self, text: str, session: str = "main") -> bool:
        """Send a message to the gateway."""
        if not self.connected or not self.ws:
            Logger.warning("NovaVoice: Not connected to gateway")
            return False

        try:
            # OpenClaw gateway message format
            message = json.dumps({
                "type": "session.send",
                "sessionKey": session,
                "message": text
            })
            await self.ws.send(message)
            return True
        except Exception as e:
            Logger.error(f"NovaVoice: Failed to send message: {e}")
            return False

    async def close(self):
        """Close the connection."""
        if self._receive_task:
            self._receive_task.cancel()
        if self.ws:
            await self.ws.close()
        self.connected = False


class TTSEngine:
    """Text-to-speech using Edge TTS."""

    def __init__(self, voice: str = "en-US-AvaNeural"):
        self.voice = voice
        self.speaking = False
        self._cache_dir = Path(__file__).parent / "tts_cache"

    async def speak(self, text: str) -> bool:
        """Speak text using Edge TTS."""
        if self.speaking or not text:
            return False

        self.speaking = True
        try:
            import edge_tts

            # Create cache directory
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            audio_path = self._cache_dir / "temp_audio.mp3"

            # Generate speech
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(str(audio_path))

            # Play audio
            sound = SoundLoader.load(str(audio_path))
            if sound:
                # Create event to wait for playback
                playback_done = threading.Event()

                def on_stop():
                    playback_done.set()

                sound.bind(on_stop=lambda instance: on_stop())

                sound.play()

                # Wait for playback (with timeout)
                import time
                start = time.time()
                while sound.state == 'play' and time.time() - start < 60:
                    await asyncio.sleep(0.1)

                sound.unload()

            # Cleanup
            if audio_path.exists():
                try:
                    audio_path.unlink()
                except:
                    pass

            self.speaking = False
            return True
        except Exception as e:
            Logger.error(f"NovaVoice: TTS error: {e}")
            self.speaking = False
            return False


class SetupScreen(MDScreen):
    """First-run setup screen."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build_ui()

    def _build_ui(self):
        """Build the setup UI."""
        layout = BoxLayout(orientation='vertical', padding='24dp', spacing='16dp')

        # Title
        layout.add_widget(MDLabel(
            text="Nova Voice Setup",
            font_style="H4",
            size_hint_y=None,
            height='60dp',
            halign="center",
        ))

        layout.add_widget(MDLabel(
            text="Enter your gateway settings to connect to Nova.",
            size_hint_y=None,
            height='40dp',
            halign="center",
            theme_text_color="Secondary",
        ))

        # Gateway Host
        self.host_field = MDTextField(
            hint_text="Gateway Host (e.g., 192.168.1.100)",
            text=config.get("gateway_host", ""),
            size_hint_y=None,
            height='60dp',
        )
        layout.add_widget(self.host_field)

        # Gateway Port
        self.port_field = MDTextField(
            hint_text="Gateway Port",
            text=str(config.get("gateway_port", 18789)),
            input_filter="int",
            size_hint_y=None,
            height='60dp',
        )
        layout.add_widget(self.port_field)

        # Gateway Token
        self.token_field = MDTextField(
            hint_text="Gateway Token",
            text=config.get("gateway_token", ""),
            password=True,
            size_hint_y=None,
            height='60dp',
        )
        layout.add_widget(self.token_field)

        # Save button
        save_btn = MDRaisedButton(
            text="Save & Connect",
            size_hint_y=None,
            height='50dp',
        )
        save_btn.bind(on_release=self._save_settings)
        layout.add_widget(save_btn)

        # Instructions
        layout.add_widget(BoxLayout(size_hint_y=None, height='20dp'))
        layout.add_widget(MDLabel(
            text="You can find your gateway token in ~/.openclaw/openclaw.json on your server.",
            size_hint_y=None,
            height='40dp',
            font_style="Caption",
            theme_text_color="Secondary",
        ))

        self.add_widget(layout)

    def _save_settings(self, instance):
        """Save settings and proceed to conversation."""
        host = self.host_field.text.strip()
        port_text = self.port_field.text.strip()
        token = self.token_field.text.strip()

        if not host:
            self._show_error("Please enter a gateway host")
            return

        if not token:
            self._show_error("Please enter a gateway token")
            return

        try:
            port = int(port_text) if port_text else 18789
        except ValueError:
            self._show_error("Invalid port number")
            return

        # Save config
        config.data["gateway_host"] = host
        config.data["gateway_port"] = port
        config.data["gateway_token"] = token
        config.data["setup_complete"] = True
        config.save()

        # Switch to conversation screen
        app = MDApp.get_running_app()
        app.root.current = "conversation"

    def _show_error(self, message: str):
        """Show error dialog."""
        dialog = MDDialog(
            title="Error",
            text=message,
            buttons=[MDRaisedButton(text="OK", on_release=lambda x: dialog.dismiss())],
        )
        dialog.open()


class ConversationScreen(MDScreen):
    """Main conversation screen."""

    status_text = StringProperty("Disconnected")
    is_listening = BooleanProperty(False)
    wake_word_status = StringProperty("Wake word: inactive")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.gateway = None
        self.wake_detector = None
        self.audio_capture = None
        self.tts = None
        self.loop = None
        self.event_loop_thread = None
        self._build_ui()

    def _build_ui(self):
        """Build the user interface."""
        # Top app bar
        self.toolbar = MDTopAppBar(
            title="Nova Voice",
            elevation=4,
        )
        self.add_widget(self.toolbar)

        # Main content
        content = BoxLayout(orientation='vertical', padding='16dp', spacing='16dp')

        # Status card
        status_card = MDCard(
            size_hint_y=None,
            height='100dp',
            padding='16dp',
            elevation=2,
        )
        status_content = BoxLayout(orientation='vertical', spacing='8dp')
        status_content.add_widget(MDLabel(
            text="Status",
            font_style="H6",
            size_hint_y=None,
            height='30dp',
        ))
        self.status_label = MDLabel(
            text=self.status_text,
            theme_text_color="Secondary",
        )
        status_content.add_widget(self.status_label)
        status_card.add_widget(status_content)
        content.add_widget(status_card)

        # Wake word status
        self.wake_label = MDLabel(
            text=self.wake_word_status,
            size_hint_y=None,
            height='40dp',
        )
        content.add_widget(self.wake_label)

        # Message display area
        self.message_label = MDLabel(
            text="Press 'Start Listening' to begin",
            halign="center",
            valign="middle",
            theme_text_color="Secondary",
        )
        content.add_widget(self.message_label)

        # Buttons
        button_layout = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height='60dp',
            spacing='8dp',
        )

        self.connect_btn = MDRaisedButton(
            text="Connect",
        )
        self.connect_btn.bind(on_release=self._on_connect)
        button_layout.add_widget(self.connect_btn)

        self.listen_btn = MDRaisedButton(
            text="Start Listening",
            disabled=True,
        )
        self.listen_btn.bind(on_release=self._toggle_listening)
        button_layout.add_widget(self.listen_btn)

        content.add_widget(button_layout)

        # Settings button
        settings_btn = MDRaisedButton(
            text="Settings",
        )
        settings_btn.bind(on_release=self._show_settings)
        content.add_widget(settings_btn)

        self.add_widget(content)

    def _initialize(self, dt):
        """Initialize components."""
        # Initialize TTS
        self.tts = TTSEngine(config.get("voice"))

        # Initialize wake word detector
        self.wake_detector = WakeWordDetector(config.get("wake_word"))
        if self.wake_detector.initialize():
            self.wake_word_status = f"Wake word: ready ({config.get('wake_word')})"
        else:
            self.wake_word_status = "Wake word: unavailable"

        # Initialize audio capture
        if ANDROID_AVAILABLE:
            self.audio_capture = AndroidAudioCapture()
        else:
            self.audio_capture = DesktopAudioCapture()

        # Start async event loop
        self._start_event_loop()

        self.status_text = "Ready - Press Connect"
        self._update_ui()

        # Auto-connect if configured
        if config.is_configured():
            Clock.schedule_once(lambda dt: self._on_connect(None), 1.0)

    def _start_event_loop(self):
        """Start the async event loop."""
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        self.event_loop_thread = threading.Thread(target=run_loop, daemon=True)
        self.event_loop_thread.start()

    def _on_connect(self, instance):
        """Connect to gateway."""
        if self.gateway and self.gateway.connected:
            # Disconnect
            if self.loop:
                asyncio.run_coroutine_threadsafe(self.gateway.close(), self.loop)
            self.status_text = "Disconnected"
            self.connect_btn.text = "Connect"
            self.listen_btn.disabled = True
        else:
            # Connect
            self.status_text = "Connecting..."
            self._update_ui()

            self.gateway = GatewayClient(
                config.get("gateway_host"),
                config.get("gateway_port"),
                config.get("gateway_token")
            )
            self.gateway.message_callback = self._on_gateway_message

            async def connect_async():
                if await self.gateway.connect():
                    Clock.schedule_once(lambda dt: self._on_connected())
                else:
                    Clock.schedule_once(lambda dt: self._on_connect_failed())

            if self.loop:
                asyncio.run_coroutine_threadsafe(connect_async(), self.loop)

    def _on_connected(self):
        """Called when connected to gateway."""
        self.status_text = f"Connected to {config.get('gateway_host')}:{config.get('gateway_port')}"
        self.connect_btn.text = "Disconnect"
        self.listen_btn.disabled = False
        self._update_ui()

        # Speak greeting
        if self.loop and self.tts:
            asyncio.run_coroutine_threadsafe(
                self.tts.speak("Nova online. How can I help you?"),
                self.loop
            )

    def _on_connect_failed(self):
        """Called when connection fails."""
        self.status_text = "Connection failed. Check settings."
        self._update_ui()

    def _on_gateway_message(self, data: dict):
        """Handle messages from the gateway."""
        try:
            msg_type = data.get("type", "")

            if msg_type == "chat.message" or msg_type == "session.message":
                text = data.get("message", "") or data.get("text", "")
                sender = data.get("sender", "assistant")
                role = data.get("role", "")

                if (sender == "assistant" or role == "assistant") and text:
                    Clock.schedule_once(lambda dt: self._on_assistant_message(text))

            elif msg_type == "error":
                error = data.get("message", "Unknown error")
                Logger.error(f"NovaVoice: Gateway error: {error}")

        except Exception as e:
            Logger.error(f"NovaVoice: Message handling error: {e}")

    def _on_assistant_message(self, text: str):
        """Handle assistant response."""
        self.message_label.text = f"Nova: {text[:200]}"

        # Speak the response
        if self.loop and self.tts:
            asyncio.run_coroutine_threadsafe(self.tts.speak(text), self.loop)

    def _toggle_listening(self, instance):
        """Toggle wake word listening."""
        if self.is_listening:
            self.is_listening = False
            self.listen_btn.text = "Start Listening"
            self.wake_word_status = "Wake word: inactive"

            if self.audio_capture:
                self.audio_capture.stop()
        else:
            self.is_listening = True
            self.listen_btn.text = "Stop Listening"
            self.wake_word_status = f"Listening for 'Hey {config.get('wake_word').title()}'..."

            # Initialize and start audio capture
            if not self.audio_capture:
                if ANDROID_AVAILABLE:
                    self.audio_capture = AndroidAudioCapture()
                else:
                    self.audio_capture = DesktopAudioCapture()

            if self.audio_capture.initialize():
                self.audio_capture.audio_callback = self._on_audio
                self.audio_capture.start()
            else:
                self.wake_word_status = "Audio capture failed"
                self.is_listening = False
                self.listen_btn.text = "Start Listening"

        self._update_ui()

    def _on_audio(self, audio_data: bytes):
        """Process incoming audio."""
        if not self.is_listening:
            return

        # Check for wake word
        if self.wake_detector and self.wake_detector.process_audio(audio_data):
            Clock.schedule_once(lambda dt: self._on_wake_word())

    def _on_wake_word(self):
        """Called when wake word is detected."""
        self.message_label.text = "Wake word detected! Listening..."

        # Reset wake word detector
        if self.wake_detector:
            self.wake_detector.reset()

        # Announce
        if self.loop and self.tts:
            asyncio.run_coroutine_threadsafe(self.tts.speak("Yes?"), self.loop)

    def _update_ui(self):
        """Update UI elements."""
        self.status_label.text = self.status_text
        self.wake_label.text = self.wake_word_status

    def _show_settings(self, instance):
        """Show settings dialog."""
        app = MDApp.get_running_app()
        app.root.current = "setup"

    def on_enter(self):
        """Called when screen becomes active."""
        if not hasattr(self, 'loop'):
            Clock.schedule_once(self._initialize, 0.5)


class NovaVoiceApp(MDApp):
    """Nova Voice Application."""

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "DeepPurple"
        self.theme_cls.accent_palette = "Teal"

        # Create screen manager
        sm = MDScreenManager()

        # Add screens
        sm.add_widget(SetupScreen(name="setup"))
        sm.add_widget(ConversationScreen(name="conversation"))

        # Show setup screen first if not configured
        if config.is_configured():
            sm.current = "conversation"
        else:
            sm.current = "setup"

        return sm

    def on_start(self):
        """Called when app starts."""
        Logger.info("NovaVoice: Application started")

    def on_stop(self):
        """Called when app stops."""
        Logger.info("NovaVoice: Application stopped")


def main():
    """Main entry point."""
    NovaVoiceApp().run()


if __name__ == "__main__":
    main()
