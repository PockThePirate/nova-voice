#!/usr/bin/env python3
"""
Nova Voice - Voice assistant with wake word detection and OpenClaw gateway integration.
"""

import asyncio
import json
import os
import queue
import threading
from pathlib import Path
from typing import Optional

import websockets
from kivy.app import App
from kivy.clock import Clock
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
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    Logger.warning("NovaVoice: Vosk not available, wake word detection disabled")

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    Logger.warning("NovaVoice: PyAudio not available")


# Configuration
class Config:
    def __init__(self):
        self.config_path = Path(__file__).parent / "config.json"
        self.defaults = {
            "gateway_host": "127.0.0.1",
            "gateway_port": 18789,
            "wake_word": "nova",
            "wake_word_timeout": 10,
            "voice": "en-US-JennyNeural",  # Fallback voice
            "edge_voice": "en-US-AvaNeural",  # Edge TTS voice
        }
        self.data = self.load()

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
            with open(self.config_path, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            Logger.error(f"NovaVoice: Failed to save config: {e}")

    def get(self, key: str, default=None):
        return self.data.get(key, default if default else self.defaults.get(key))


# Global config instance
config = Config()


class WakeWordDetector:
    """Wake word detection using Vosk offline speech recognition."""
    
    def __init__(self, wake_word: str = "nova"):
        self.wake_word = wake_word.lower()
        self.model: Optional[Model] = None
        self.recognizer: Optional[KaldiRecognizer] = None
        self.running = False
        self.detected_callback = None
        
        # Download model if needed
        self.model_path = self._get_model_path()
        
    def _get_model_path(self) -> Path:
        """Get or download Vosk model."""
        model_dir = Path(__file__).parent / "vosk-model"
        small_model = model_dir / "vosk-model-small-en-us-0.15"
        
        if small_model.exists():
            return small_model
        
        # Create model directory
        model_dir.mkdir(exist_ok=True)
        
        # Return path where model should be extracted
        return small_model
    
    def initialize(self) -> bool:
        """Initialize the wake word detector."""
        if not VOSK_AVAILABLE:
            Logger.warning("NovaVoice: Vosk not available")
            return False
            
        if not self.model_path.exists():
            Logger.error(f"NovaVoice: Vosk model not found at {self.model_path}")
            Logger.info("NovaVoice: Download model from https://alphacephei.com/vosk/models")
            Logger.info("NovaVoice: Extract to vosk-model/vosk-model-small-en-us-0.15/")
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
                Logger.debug(f"NovaVoice: Wake word check: '{text}'")
                
                if self.wake_word in text:
                    Logger.info(f"NovaVoice: Wake word '{self.wake_word}' detected!")
                    return True
        except Exception as e:
            Logger.error(f"NovaVoice: Wake word processing error: {e}")
            
        return False
    
    def reset(self):
        """Reset the recognizer state."""
        if self.recognizer:
            self.recognizer = KaldiRecognizer(self.model, 16000)


class AudioCapture:
    """Audio capture using PyAudio."""
    
    def __init__(self, sample_rate: int = 16000, chunk_size: int = 4096):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.audio: Optional[pyaudio.PyAudio] = None
        self.stream = None
        self.running = False
        
    def initialize(self) -> bool:
        """Initialize audio capture."""
        if not PYAUDIO_AVAILABLE:
            Logger.error("NovaVoice: PyAudio not available")
            return False
            
        try:
            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._audio_callback
            )
            Logger.info("NovaVoice: Audio capture initialized")
            return True
        except Exception as e:
            Logger.error(f"NovaVoice: Failed to initialize audio: {e}")
            return False
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Audio stream callback."""
        if self.audio_callback:
            self.audio_callback(in_data)
        return (in_data, pyaudio.paContinue)
    
    audio_callback = None
    
    def start(self):
        """Start capturing audio."""
        if self.stream:
            self.stream.start_stream()
            self.running = True
            
    def stop(self):
        """Stop capturing audio."""
        if self.stream:
            self.stream.stop_stream()
            self.running = False
    
    def close(self):
        """Close audio resources."""
        if self.stream:
            self.stream.close()
        if self.audio:
            self.audio.terminate()


class GatewayClient:
    """WebSocket client for OpenClaw gateway."""
    
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.message_callback = None
        
    async def connect(self) -> bool:
        """Connect to the gateway."""
        try:
            uri = f"ws://{self.host}:{self.port}/ws"
            self.ws = await websockets.connect(uri)
            self.connected = True
            Logger.info(f"NovaVoice: Connected to gateway at {uri}")
            
            # Start message handler
            asyncio.create_task(self._message_handler())
            return True
        except Exception as e:
            Logger.error(f"NovaVoice: Failed to connect to gateway: {e}")
            self.connected = False
            return False
    
    async def _message_handler(self):
        """Handle incoming messages."""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    if self.message_callback:
                        self.message_callback(data)
                except json.JSONDecodeError:
                    Logger.warning(f"NovaVoice: Invalid JSON message: {message[:100]}")
        except websockets.exceptions.ConnectionClosed:
            Logger.info("NovaVoice: Gateway connection closed")
            self.connected = False
        except Exception as e:
            Logger.error(f"NovaVoice: Message handler error: {e}")
            self.connected = False
    
    async def send(self, text: str, session: str = "main") -> bool:
        """Send a message to the gateway."""
        if not self.connected or not self.ws:
            Logger.warning("NovaVoice: Not connected to gateway")
            return False
            
        try:
            message = json.dumps({
                "type": "chat.send",
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
        if self.ws:
            await self.ws.close()
            self.connected = False


class TTSEngine:
    """Text-to-speech using Edge TTS (Natasha voice)."""
    
    def __init__(self, voice: str = "en-US-AvaNeural"):
        self.voice = voice
        self.speaking = False
        
    async def speak(self, text: str) -> bool:
        """Speak text using Edge TTS."""
        if self.speaking:
            return False
            
        self.speaking = True
        try:
            import edge_tts
            
            communicate = edge_tts.Communicate(text, self.voice)
            
            # Generate audio file
            audio_path = Path(__file__).parent / "temp_audio.mp3"
            await communicate.save(str(audio_path))
            
            # Play audio
            sound = SoundLoader.load(str(audio_path))
            if sound:
                sound.play()
                # Wait for audio to finish
                await asyncio.sleep(sound.length)
                sound.unload()
            
            # Cleanup
            if audio_path.exists():
                audio_path.unlink()
                
            self.speaking = False
            return True
        except Exception as e:
            Logger.error(f"NovaVoice: TTS error: {e}")
            self.speaking = False
            return False


class ConversationScreen(MDScreen):
    """Main conversation screen."""
    
    status_text = StringProperty("Disconnected")
    is_listening = BooleanProperty(False)
    wake_word_status = StringProperty("Wake word: inactive")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.gateway = None
        self.wake_detector = None
        self.audio_capture = None
        self.tts = None
        self.loop = None
        self.event_loop_thread = None
        
        # Build UI
        self._build_ui()
        
        # Initialize components
        Clock.schedule_once(self._initialize, 0.5)
    
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
            text="Say 'Hey Nova' to start...",
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
            on_release=self._on_connect,
        )
        button_layout.add_widget(self.connect_btn)
        
        self.listen_btn = MDRaisedButton(
            text="Start Listening",
            on_release=self._toggle_listening,
            disabled=True,
        )
        button_layout.add_widget(self.listen_btn)
        
        content.add_widget(button_layout)
        
        # Settings button
        settings_btn = MDRaisedButton(
            text="Settings",
            on_release=self._show_settings,
        )
        content.add_widget(settings_btn)
        
        self.add_widget(content)
    
    def _initialize(self, dt):
        """Initialize components."""
        # Initialize TTS
        self.tts = TTSEngine(self.config.get("edge_voice"))
        
        # Initialize wake word detector
        self.wake_detector = WakeWordDetector(self.config.get("wake_word"))
        if self.wake_detector.initialize():
            self.wake_word_status = f"Wake word: ready ({self.config.get('wake_word')})"
        else:
            self.wake_word_status = "Wake word: unavailable"
        
        # Initialize audio capture
        self.audio_capture = AudioCapture()
        
        # Start async event loop
        self._start_event_loop()
        
        self.status_text = "Ready - Press Connect"
        self._update_ui()
    
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
            asyncio.run_coroutine_threadsafe(
                self.gateway.close(),
                self.loop
            )
            self.status_text = "Disconnected"
            self.connect_btn.text = "Connect"
            self.listen_btn.disabled = True
        else:
            # Connect
            self.status_text = "Connecting..."
            self._update_ui()
            
            self.gateway = GatewayClient(
                self.config.get("gateway_host"),
                self.config.get("gateway_port")
            )
            self.gateway.message_callback = self._on_gateway_message
            
            async def connect_async():
                if await self.gateway.connect():
                    Clock.schedule_once(lambda dt: self._on_connected())
                else:
                    Clock.schedule_once(lambda dt: self._on_connect_failed())
            
            asyncio.run_coroutine_threadsafe(connect_async(), self.loop)
    
    def _on_connected(self):
        """Called when connected to gateway."""
        self.status_text = f"Connected to {self.config.get('gateway_host')}:{self.config.get('gateway_port')}"
        self.connect_btn.text = "Disconnect"
        self.listen_btn.disabled = False
        self._update_ui()
        
        # Speak greeting
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
            
            if msg_type == "chat.message":
                text = data.get("message", "")
                sender = data.get("sender", "assistant")
                
                if sender == "assistant" and text:
                    Clock.schedule_once(lambda dt: self._on_assistant_message(text))
            elif msg_type == "error":
                error = data.get("message", "Unknown error")
                Logger.error(f"NovaVoice: Gateway error: {error}")
        except Exception as e:
            Logger.error(f"NovaVoice: Message handling error: {e}")
    
    def _on_assistant_message(self, text: str):
        """Handle assistant response."""
        self.message_label.text = f"Nova: {text}"
        
        # Speak the response
        asyncio.run_coroutine_threadsafe(
            self.tts.speak(text),
            self.loop
        )
    
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
            self.wake_word_status = f"Listening for 'Hey {self.config.get('wake_word').title()}'..."
            
            # Start audio capture
            if not self.audio_capture.stream:
                self.audio_capture.initialize()
            
            self.audio_capture.audio_callback = self._on_audio
            self.audio_capture.start()
        
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
        asyncio.run_coroutine_threadsafe(
            self.tts.speak("Yes?"),
            self.loop
        )
    
    def _update_ui(self):
        """Update UI elements."""
        self.status_label.text = self.status_text
        self.wake_label.text = self.wake_word_status
    
    def _show_settings(self, instance):
        """Show settings dialog."""
        # TODO: Implement settings dialog
        pass


class SettingsScreen(MDScreen):
    """Settings screen."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        
        # Build UI
        content = BoxLayout(orientation='vertical', padding='16dp', spacing='16dp')
        
        # Gateway settings
        content.add_widget(MDLabel(text="Gateway Settings", font_style="H6"))
        
        self.host_field = MDTextField(
            hint_text="Gateway Host",
            text=self.config.get("gateway_host"),
        )
        content.add_widget(self.host_field)
        
        self.port_field = MDTextField(
            hint_text="Gateway Port",
            text=str(self.config.get("gateway_port")),
            input_filter="int",
        )
        content.add_widget(self.port_field)
        
        # Wake word settings
        content.add_widget(MDLabel(text="Wake Word Settings", font_style="H6"))
        
        self.wake_word_field = MDTextField(
            hint_text="Wake Word",
            text=self.config.get("wake_word"),
        )
        content.add_widget(self.wake_word_field)
        
        # Save button
        save_btn = MDRaisedButton(
            text="Save Settings",
            on_release=self._save_settings,
        )
        content.add_widget(save_btn)
        
        self.add_widget(content)
    
    def _save_settings(self, instance):
        """Save settings."""
        self.config.data["gateway_host"] = self.host_field.text
        self.config.data["gateway_port"] = int(self.port_field.text)
        self.config.data["wake_word"] = self.wake_word_field.text.lower()
        self.config.save()


class NovaVoiceApp(MDApp):
    """Nova Voice Application."""
    
    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "DeepPurple"
        self.theme_cls.accent_palette = "Teal"
        
        # Create screen manager
        sm = MDScreenManager()
        
        # Add screens
        sm.add_widget(ConversationScreen(name="conversation"))
        sm.add_widget(SettingsScreen(name="settings"))
        
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