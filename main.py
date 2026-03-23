#!/usr/bin/env python3
"""
Nova Voice - OpenClaw Node Client
A futuristic mission control interface for hands-free voice interaction.
Implements the full OpenClaw gateway protocol with device authentication.
"""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, Callable

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.audio import SoundLoader
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle, PushMatrix, PopMatrix
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty, NumericProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.animation import Animation
from kivy.lang import Builder

from kivymd.app import MDApp
from kivymd.uix.button import MDRaisedButton, MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.textfield import MDTextField
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.boxlayout import MDBoxLayout

import websockets

try:
    from jnius import autoclass
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    AudioRecord = autoclass('android.media.AudioRecord')
    MediaRecorder = autoclass('android.media.MediaRecorder')
    AudioSource = autoclass('android.media.MediaRecorder$AudioSource')
    AudioFormat = autoclass('android.media.AudioFormat')
    ANDROID_AVAILABLE = True
except ImportError:
    ANDROID_AVAILABLE = False

try:
    from vosk import Model, KaldiRecognizer, SetLogLevel
    SetLogLevel(-1)
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.encoding import Base64Encoder
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False


# KivyMD KV Language for futuristic UI
KV = '''
<HudPanel@MDCard>
    elevation: 0
    md_bg_color: 0.05, 0.1, 0.15, 0.9
    radius: [dp(8), dp(8), dp(8), dp(8)]

<HudLabel@MDLabel>
    font_name: "RobotoMono"
    theme_text_color: "Custom"
    text_color: 0.4, 0.8, 1, 1

<HudValue@MDLabel>
    font_name: "RobotoMono"
    theme_text_color: "Custom"
    text_color: 0.2, 1, 0.6, 1

<HudButton@MDRaisedButton>
    font_name: "RobotoMono"
    md_bg_color: 0.1, 0.3, 0.4, 1
    theme_text_color: "Custom"
    text_color: 0.4, 0.8, 1, 1
    elevation: 0
    radius: [dp(4), dp(4), dp(4), dp(4)]

<StatusIndicator@BoxLayout>:
    status: "offline"
    size_hint_x: None
    width: dp(120)
    
    canvas.before:
        Color:
            rgba: (1, 0.3, 0.3, 0.3) if self.status == "offline" else (1, 0.8, 0.2, 0.3) if self.status == "connecting" else (0.2, 1, 0.6, 0.3)
        RoundedRectangle:
            size: self.size
            radius: [dp(4), dp(4), dp(4), dp(4)]
    
    MDLabel:
        text: "OFFLINE" if root.status == "offline" else "CONNECTING..." if root.status == "connecting" else "ONLINE"
        font_name: "RobotoMono"
        font_size: sp(12)
        halign: "center"
        theme_text_color: "Custom"
        text_color: (1, 0.3, 0.3, 1) if root.status == "offline" else (1, 0.8, 0.2, 1) if root.status == "connecting" else (0.2, 1, 0.6, 1)

<AudioVisualizer@BoxLayout>:
    amplitude: 0.0
    bars: 16
    
    canvas.before:
        Color:
            rgba: 0.1, 0.2, 0.3, 1
        RoundedRectangle:
            size: self.size
            radius: [dp(8), dp(8), dp(8), dp(8)]
    
    canvas.after:
        PushMatrix
        Color:
            rgba: 0.2, 0.8, 1, 0.8
        # Visual bars will be drawn dynamically
        PopMatrix
'''


class Config:
    """Configuration management."""
    
    def __init__(self):
        self.config_path = self._get_config_path()
        self.device_key_path = self.config_path.parent / "device_key.json"
        self.defaults = {
            "gateway_host": "147.93.113.71",
            "gateway_port": 18789,
            "gateway_token": "",
            "wake_word": "nova",
            "voice": "en-US-AvaNeural",
            "setup_complete": False,
        }
        self.data = self.load()
        self.device_key = self._load_device_key()
    
    def _get_config_path(self) -> Path:
        try:
            if ANDROID_AVAILABLE:
                activity = PythonActivity.mActivity
                files_dir = activity.getFilesDir().getAbsolutePath()
                return Path(files_dir) / "config.json"
        except:
            pass
        return Path(__file__).parent / "config.json"
    
    def _load_device_key(self) -> Optional[Dict]:
        """Load or generate device keypair for authentication."""
        if NACL_AVAILABLE:
            try:
                if self.device_key_path.exists():
                    with open(self.device_key_path) as f:
                        return json.load(f)
            except:
                pass
            
            # Generate new keypair
            signing_key = SigningKey.generate()
            verify_key = signing_key.verify_key
            
            device_id = hashlib.sha256(verify_key.encode()).hexdigest()[:16]
            
            key_data = {
                "device_id": f"nova_voice_{device_id}",
                "private_key": base64.b64encode(bytes(signing_key)).decode(),
                "public_key": base64.b64encode(bytes(verify_key)).decode(),
            }
            
            try:
                self.device_key_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.device_key_path, 'w') as f:
                    json.dump(key_data, f)
            except:
                pass
            
            return key_data
        return None
    
    def load(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    loaded = json.load(f)
                    return {**self.defaults, **loaded}
            except:
                pass
        return self.defaults.copy()
    
    def save(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            pass
    
    def get(self, key: str, default=None):
        return self.data.get(key, default if default else self.defaults.get(key))
    
    def is_configured(self) -> bool:
        return bool(self.data.get("gateway_host")) and bool(self.data.get("gateway_token"))


class GatewayProtocol:
    """Implements the OpenClaw gateway WebSocket protocol."""
    
    PROTOCOL_VERSION = 3
    
    def __init__(self, host: str, port: int, token: str, device_key: Dict = None):
        self.host = host
        self.port = port
        self.token = token
        self.device_key = device_key
        self.ws = None
        self.connected = False
        self.authenticated = False
        self.challenge_nonce = None
        self.challenge_ts = None
        self.device_token = None
        self.message_callback = None
        self._receive_task = None
        _request_id_counter = 0
    
    def _next_request_id(self) -> str:
        self._request_id_counter = getattr(self, '_request_id_counter', 0) + 1
        return f"req_{int(time.time() * 1000)}_{self._request_id_counter}"
    
    def _sign_challenge(self, nonce: str, ts: int) -> Dict[str, Any]:
        """Sign the challenge nonce with device key."""
        if not NACL_AVAILABLE or not self.device_key:
            return {}
        
        try:
            private_key_bytes = base64.b64decode(self.device_key["private_key"])
            signing_key = SigningKey(private_key_bytes)
            
            # Create signature payload (v3 format)
            payload = json.dumps({
                "device_id": self.device_key["device_id"],
                "platform": "android",
                "nonce": nonce,
                "ts": ts
            }, sort_keys=True, separators=(',', ':'))
            
            signed = signing_key.sign(payload.encode())
            signature = base64.b64encode(signed.signature).decode()
            
            return {
                "id": self.device_key["device_id"],
                "publicKey": self.device_key["public_key"],
                "signature": signature,
                "signedAt": int(time.time() * 1000),
                "nonce": nonce
            }
        except Exception as e:
            return {}
    
    async def connect(self) -> tuple[bool, str]:
        """Connect to gateway and perform handshake."""
        try:
            uri = f"ws://{self.host}:{self.port}/ws"
            self.ws = await websockets.connect(uri, ping_interval=30, ping_timeout=10)
            
            # Wait for challenge
            try:
                challenge = await asyncio.wait_for(self.ws.recv(), timeout=10)
                challenge_data = json.loads(challenge)
                
                if challenge_data.get("event") == "connect.challenge":
                    payload = challenge_data.get("payload", {})
                    self.challenge_nonce = payload.get("nonce")
                    self.challenge_ts = payload.get("ts")
                else:
                    # Try direct connect if no challenge
                    self.challenge_nonce = secrets.token_hex(16)
                    self.challenge_ts = int(time.time() * 1000)
            except asyncio.TimeoutError:
                # No challenge, generate our own
                self.challenge_nonce = secrets.token_hex(16)
                self.challenge_ts = int(time.time() * 1000)
            
            # Build connect frame
            device_auth = self._sign_challenge(self.challenge_nonce, self.challenge_ts)
            
            connect_frame = {
                "type": "req",
                "id": self._next_request_id(),
                "method": "connect",
                "params": {
                    "minProtocol": self.PROTOCOL_VERSION,
                    "maxProtocol": self.PROTOCOL_VERSION,
                    "client": {
                        "id": "nova-voice",
                        "version": "1.0.0",
                        "platform": "android",
                        "mode": "node"
                    },
                    "role": "node",
                    "scopes": [],
                    "caps": ["voice", "audio"],
                    "commands": ["voice.listen", "audio.capture"],
                    "permissions": {
                        "audio.capture": True,
                        "voice.listen": True
                    },
                    "auth": {"token": self.token},
                    "locale": "en-US",
                    "userAgent": "NovaVoice/1.0.0",
                }
            }
            
            # Add device auth if available
            if device_auth:
                connect_frame["params"]["device"] = device_auth
            
            # Send connect request
            await self.ws.send(json.dumps(connect_frame))
            
            # Wait for response
            try:
                response = await asyncio.wait_for(self.ws.recv(), timeout=10)
                response_data = json.loads(response)
                
                if response_data.get("type") == "res" and response_data.get("ok"):
                    payload = response_data.get("payload", {})
                    if payload.get("type") == "hello-ok":
                        self.authenticated = True
                        self.device_token = payload.get("auth", {}).get("deviceToken")
                        
                        # Start message handler
                        self._receive_task = asyncio.create_task(self._receive_loop())
                        self.connected = True
                        
                        return True, "Connected successfully"
                    else:
                        return False, f"Unexpected response: {payload}"
                else:
                    error = response_data.get("error", {})
                    code = error.get("details", {}).get("code", error.get("message", "Unknown error"))
                    return False, f"Auth failed: {code}"
                    
            except asyncio.TimeoutError:
                return False, "Connection timeout - no response from gateway"
                
        except websockets.exceptions.ConnectionClosed as e:
            return False, f"Connection closed: {e}"
        except Exception as e:
            return False, f"Connection error: {e}"
    
    async def _receive_loop(self):
        """Receive messages from gateway."""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    if self.message_callback:
                        self.message_callback(data)
                except json.JSONDecodeError:
                    pass
                except Exception:
                    pass
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception:
            pass
        finally:
            self.connected = False
            self.authenticated = False
    
    async def send_message(self, text: str, session_key: str = "main") -> bool:
        """Send a chat message to the gateway."""
        if not self.connected or not self.ws:
            return False
        
        try:
            message = {
                "type": "req",
                "id": self._next_request_id(),
                "method": "chat.send",
                "params": {
                    "sessionKey": session_key,
                    "message": text
                }
            }
            await self.ws.send(json.dumps(message))
            return True
        except:
            return False
    
    async def close(self):
        """Close the connection."""
        if self._receive_task:
            self._receive_task.cancel()
        if self.ws:
            await self.ws.close()
        self.connected = False
        self.authenticated = False


class AudioCapture:
    """Android audio capture using AudioRecord API."""
    
    def __init__(self, sample_rate: int = 16000, chunk_size: int = 4096):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.audio_record = None
        self.running = False
        self.audio_callback = None
        self._thread = None
    
    def initialize(self) -> bool:
        if not ANDROID_AVAILABLE:
            return False
        
        try:
            channel_config = AudioFormat.CHANNEL_IN_MONO
            audio_format = AudioFormat.ENCODING_PCM_16BIT
            min_buffer = AudioRecord.getMinBufferSize(self.sample_rate, channel_config, audio_format)
            
            self.audio_record = AudioRecord(
                AudioSource.MIC,
                self.sample_rate,
                channel_config,
                audio_format,
                max(min_buffer, self.chunk_size * 2)
            )
            
            if self.audio_record.getState() != AudioRecord.STATE_INITIALIZED:
                return False
            
            return True
        except:
            return False
    
    def start(self):
        if not self.audio_record:
            return
        
        self.running = True
        self.audio_record.startRecording()
        
        def capture_loop():
            buffer_size = self.chunk_size * 2
            buffer = bytearray(buffer_size)
            
            while self.running:
                try:
                    bytes_read = self.audio_record.read(buffer, 0, buffer_size)
                    if bytes_read > 0 and self.audio_callback:
                        audio_data = bytes(buffer[:bytes_read])
                        self.audio_callback(audio_data)
                except:
                    break
        
        self._thread = threading.Thread(target=capture_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        self.running = False
        if self.audio_record:
            try:
                self.audio_record.stop()
            except:
                pass
    
    def close(self):
        if self.audio_record:
            try:
                self.audio_record.release()
            except:
                pass
            self.audio_record = None


class WakeWordDetector:
    """Wake word detection using Vosk."""
    
    def __init__(self, wake_word: str = "nova"):
        self.wake_word = wake_word.lower()
        self.model = None
        self.recognizer = None
        self.model_path = self._get_model_path()
    
    def _get_model_path(self) -> Path:
        bundled = Path(__file__).parent / "assets" / "vosk-model-small-en-us-0.15"
        if bundled.exists():
            return bundled
        
        if ANDROID_AVAILABLE:
            try:
                activity = PythonActivity.mActivity
                files_dir = activity.getFilesDir().getAbsolutePath()
                app_model = Path(files_dir) / "vosk-model-small-en-us-0.15"
                if app_model.exists():
                    return app_model
            except:
                pass
        
        return Path(__file__).parent / "vosk-model-small-en-us-0.15"
    
    def initialize(self) -> bool:
        if not VOSK_AVAILABLE:
            return False
        
        if not self.model_path.exists():
            return False
        
        try:
            self.model = Model(str(self.model_path))
            self.recognizer = KaldiRecognizer(self.model, 16000)
            return True
        except:
            return False
    
    def process_audio(self, audio_data: bytes) -> bool:
        if not self.recognizer:
            return False
        
        try:
            if self.recognizer.AcceptWaveform(audio_data):
                result = json.loads(self.recognizer.Result())
                text = result.get("text", "").lower()
                if self.wake_word in text:
                    return True
        except:
            pass
        
        return False
    
    def reset(self):
        if self.model:
            self.recognizer = KaldiRecognizer(self.model, 16000)


class TTSEngine:
    """Text-to-speech using Edge TTS."""
    
    def __init__(self, voice: str = "en-US-AvaNeural"):
        self.voice = voice
        self.speaking = False
        self._cache_dir = Path(__file__).parent / "tts_cache"
    
    async def speak(self, text: str) -> bool:
        if self.speaking or not text:
            return False
        
        self.speaking = True
        try:
            import edge_tts
            
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            audio_path = self._cache_dir / "temp_audio.mp3"
            
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(str(audio_path))
            
            sound = SoundLoader.load(str(audio_path))
            if sound:
                sound.play()
                import time
                start = time.time()
                while sound.state == 'play' and time.time() - start < 60:
                    await asyncio.sleep(0.1)
                sound.unload()
            
            try:
                audio_path.unlink()
            except:
                pass
            
            self.speaking = False
            return True
        except:
            self.speaking = False
            return False


class MissionControlScreen(MDScreen):
    """Futuristic mission control interface."""
    
    connection_status = StringProperty("offline")
    status_message = StringProperty("Ready")
    is_listening = BooleanProperty(False)
    wake_word_status = StringProperty("Wake word: inactive")
    last_response = StringProperty("")
    amplitude = NumericProperty(0.0)
    log_messages = ListProperty([])
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = None
        self.gateway = None
        self.audio_capture = None
        self.wake_detector = None
        self.tts = None
        self.loop = None
        self.event_loop_thread = None
        
        Clock.schedule_once(self._build_ui)
    
    def _build_ui(self, dt):
        """Build the futuristic UI."""
        # Main container with dark background
        root = FloatLayout()
        
        with root.canvas.before:
            Color(0.02, 0.05, 0.08, 1)
            self._bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._update_bg, size=self._update_bg)
        
        # Main content
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))
        
        # Header: Status bar
        header = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(8))
        
        # Title
        title = MDLabel(
            text="[b]NOVA VOICE[/b]",
            font_name="RobotoMono",
            font_size=sp(20),
            markup=True,
            theme_text_color="Custom",
            text_color=(0.4, 0.8, 1, 1),
            size_hint_x=0.6,
        )
        header.add_widget(title)
        
        # Status indicator
        self.status_indicator = BoxLayout(size_hint_x=0.4)
        self._status_label = MDLabel(
            text="● OFFLINE",
            font_name="RobotoMono",
            font_size=sp(14),
            halign="right",
            theme_text_color="Custom",
            text_color=(1, 0.3, 0.3, 1),
        )
        self.status_indicator.add_widget(self._status_label)
        header.add_widget(self.status_indicator)
        
        content.add_widget(header)
        
        # Main HUD panel
        hud_panel = MDCard(
            elevation=0,
            md_bg_color=(0.05, 0.1, 0.15, 0.9),
            radius=[dp(12), dp(12), dp(12), dp(12)],
            size_hint_y=0.35,
        )
        
        hud_content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))
        
        # Status message
        self.status_label = MDLabel(
            text="Awaiting connection...",
            font_name="RobotoMono",
            font_size=sp(16),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.2, 1, 0.6, 1),
        )
        hud_content.add_widget(self.status_label)
        
        # Response display
        self.response_label = MDLabel(
            text="",
            font_name="RobotoMono",
            font_size=sp(14),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.6, 0.8, 0.9, 1),
        )
        hud_content.add_widget(self.response_label)
        
        # Wake word status
        self.wake_label = MDLabel(
            text="Wake word: initializing...",
            font_name="RobotoMono",
            font_size=sp(12),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.5, 0.5, 0.6, 1),
        )
        hud_content.add_widget(self.wake_label)
        
        hud_panel.add_widget(hud_content)
        content.add_widget(hud_panel)
        
        # Audio visualizer placeholder
        self.visualizer_panel = MDCard(
            elevation=0,
            md_bg_color=(0.05, 0.08, 0.12, 0.9),
            radius=[dp(8), dp(8), dp(8), dp(8)],
            size_hint_y=0.2,
        )
        
        visualizer_content = BoxLayout(orientation='vertical', padding=dp(8))
        self.visualizer_label = MDLabel(
            text="[ Listening ]" if self.is_listening else "[ Idle ]",
            font_name="RobotoMono",
            font_size=sp(14),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.3, 0.6, 0.8, 1),
        )
        visualizer_content.add_widget(self.visualizer_label)
        self.visualizer_panel.add_widget(visualizer_content)
        content.add_widget(self.visualizer_panel)
        
        # Control buttons
        buttons = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(12))
        
        self.connect_btn = MDRaisedButton(
            text="CONNECT",
            font_name="RobotoMono",
            md_bg_color=(0.1, 0.3, 0.4, 1),
            theme_text_color="Custom",
            text_color=(0.4, 0.8, 1, 1),
            elevation=0,
            radius=[dp(4), dp(4), dp(4), dp(4)],
        )
        self.connect_btn.bind(on_release=self._on_connect)
        buttons.add_widget(self.connect_btn)
        
        self.listen_btn = MDRaisedButton(
            text="LISTEN",
            font_name="RobotoMono",
            md_bg_color=(0.1, 0.3, 0.4, 1),
            theme_text_color="Custom",
            text_color=(0.4, 0.8, 1, 1),
            elevation=0,
            radius=[dp(4), dp(4), dp(4), dp(4)],
            disabled=True,
        )
        self.listen_btn.bind(on_release=self._toggle_listening)
        buttons.add_widget(self.listen_btn)
        
        content.add_widget(buttons)
        
        # Settings button
        settings_btn = MDRaisedButton(
            text="SETTINGS",
            font_name="RobotoMono",
            md_bg_color=(0.15, 0.15, 0.2, 1),
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.7, 1),
            elevation=0,
            radius=[dp(4), dp(4), dp(4), dp(4)],
            size_hint_y=None,
            height=dp(50),
        )
        settings_btn.bind(on_release=self._show_settings)
        content.add_widget(settings_btn)
        
        root.add_widget(content)
        self.add_widget(root)
    
    def _update_bg(self, instance, value):
        self._bg_rect.pos = instance.pos
        self._bg_rect.size = instance.size
    
    def _initialize(self, dt):
        """Initialize components."""
        self.config = Config()
        self.tts = TTSEngine(self.config.get("voice"))
        self.wake_detector = WakeWordDetector(self.config.get("wake_word"))
        
        if self.wake_detector.initialize():
            self.wake_word_status = f"Wake word: ready ({self.config.get('wake_word')})"
        else:
            self.wake_word_status = "Wake word: unavailable"
        
        if ANDROID_AVAILABLE:
            self.audio_capture = AudioCapture()
        
        self._start_event_loop()
        
        self.status_message = "Ready - Press Connect"
        self._update_ui()
        
        # Auto-connect if configured
        if self.config.is_configured():
            Clock.schedule_once(lambda dt: self._on_connect(None), 1.0)
    
    def _start_event_loop(self):
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        
        self.event_loop_thread = threading.Thread(target=run_loop, daemon=True)
        self.event_loop_thread.start()
    
    def _on_connect(self, instance):
        if self.gateway and self.gateway.connected:
            asyncio.run_coroutine_threadsafe(self.gateway.close(), self.loop)
            self.connection_status = "offline"
            self.connect_btn.text = "CONNECT"
            self.listen_btn.disabled = True
            self._update_status("Disconnected")
        else:
            self._update_status("Connecting...")
            self.connection_status = "connecting"
            
            self.gateway = GatewayProtocol(
                self.config.get("gateway_host"),
                self.config.get("gateway_port"),
                self.config.get("gateway_token"),
                self.config.device_key
            )
            self.gateway.message_callback = self._on_gateway_message
            
            async def do_connect():
                success, message = await self.gateway.connect()
                Clock.schedule_once(lambda dt: self._on_connected(success, message))
            
            asyncio.run_coroutine_threadsafe(do_connect(), self.loop)
    
    def _on_connected(self, success: bool, message: str):
        if success:
            self.connection_status = "online"
            self.connect_btn.text = "DISCONNECT"
            self.listen_btn.disabled = False
            self._update_status(f"Connected to {self.config.get('gateway_host')}")
            
            if self.loop and self.tts:
                asyncio.run_coroutine_threadsafe(
                    self.tts.speak("Nova online. How can I help you?"),
                    self.loop
                )
        else:
            self.connection_status = "offline"
            self._update_status(f"Connection failed: {message}")
    
    def _on_gateway_message(self, data: dict):
        msg_type = data.get("type", "")
        
        if msg_type == "res":
            # Response to our request
            pass
        elif msg_type == "event":
            event = data.get("event", "")
            if event == "chat.message":
                text = data.get("payload", {}).get("message", "")
                if text:
                    Clock.schedule_once(lambda dt: self._on_response(text))
    
    def _on_response(self, text: str):
        self.last_response = text[:200]
        self.response_label.text = f"Nova: {self.last_response}"
        
        if self.loop and self.tts:
            asyncio.run_coroutine_threadsafe(self.tts.speak(text), self.loop)
    
    def _toggle_listening(self, instance):
        if self.is_listening:
            self.is_listening = False
            self.listen_btn.text = "LISTEN"
            self.visualizer_label.text = "[ Idle ]"
            self.wake_word_status = "Wake word: inactive"
            
            if self.audio_capture:
                self.audio_capture.stop()
        else:
            self.is_listening = True
            self.listen_btn.text = "STOP"
            self.visualizer_label.text = "[ Listening ]"
            self.wake_word_status = f"Listening for '{self.config.get('wake_word')}'..."
            
            if not self.audio_capture:
                if ANDROID_AVAILABLE:
                    self.audio_capture = AudioCapture()
            
            if self.audio_capture and self.audio_capture.initialize():
                self.audio_capture.audio_callback = self._on_audio
                self.audio_capture.start()
            else:
                self.wake_word_status = "Audio capture unavailable"
                self.is_listening = False
                self.listen_btn.text = "LISTEN"
        
        self._update_ui()
    
    def _on_audio(self, audio_data: bytes):
        if not self.is_listening:
            return
        
        if self.wake_detector and self.wake_detector.process_audio(audio_data):
            Clock.schedule_once(lambda dt: self._on_wake_word())
    
    def _on_wake_word(self):
        self.response_label.text = "Wake word detected!"
        self.visualizer_label.text = "[ Wake! ]"
        
        if self.wake_detector:
            self.wake_detector.reset()
        
        if self.loop and self.tts:
            asyncio.run_coroutine_threadsafe(self.tts.speak("Yes?"), self.loop)
    
    def _update_status(self, message: str):
        self.status_message = message
        self.status_label.text = message
        
        status_colors = {
            "offline": (1, 0.3, 0.3, 1),
            "connecting": (1, 0.8, 0.2, 1),
            "online": (0.2, 1, 0.6, 1),
        }
        color = status_colors.get(self.connection_status, (0.5, 0.5, 0.5, 1))
        self._status_label.text = f"● {self.connection_status.upper()}"
        self._status_label.text_color = color
    
    def _update_ui(self):
        self.wake_label.text = self.wake_word_status
    
    def _show_settings(self, instance):
        app = MDApp.get_running_app()
        app.root.current = "setup"
    
    def on_enter(self):
        if not hasattr(self, 'config'):
            Clock.schedule_once(self._initialize, 0.5)


class SetupScreen(MDScreen):
    """Setup screen for gateway configuration."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = None
        Clock.schedule_once(self._build_ui)
    
    def _build_ui(self, dt):
        root = FloatLayout()
        
        with root.canvas.before:
            Color(0.02, 0.05, 0.08, 1)
            bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda i, v: setattr(bg, 'pos', v), size=lambda i, v: setattr(bg, 'size', v))
        
        content = BoxLayout(orientation='vertical', padding=dp(24), spacing=dp(16))
        
        # Title
        content.add_widget(MDLabel(
            text="[b]NOVA VOICE[/b]\nSETUP",
            font_name="RobotoMono",
            font_size=sp(24),
            markup=True,
            halign="center",
            theme_text_color="Custom",
            text_color=(0.4, 0.8, 1, 1),
            size_hint_y=None,
            height=dp(80),
        ))
        
        # Instructions
        content.add_widget(MDLabel(
            text="Enter your OpenClaw gateway settings.",
            font_name="RobotoMono",
            font_size=sp(14),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.7, 1),
            size_hint_y=None,
            height=dp(40),
        ))
        
        # Form
        form = BoxLayout(orientation='vertical', spacing=dp(12))
        
        self.host_field = MDTextField(
            hint_text="Gateway Host (e.g., 192.168.1.100)",
            font_name="RobotoMono",
            size_hint_y=None,
            height=dp(60),
        )
        form.add_widget(self.host_field)
        
        self.port_field = MDTextField(
            hint_text="Gateway Port",
            text="18789",
            font_name="RobotoMono",
            size_hint_y=None,
            height=dp(60),
            input_filter="int",
        )
        form.add_widget(self.port_field)
        
        self.token_field = MDTextField(
            hint_text="Gateway Token",
            password=True,
            font_name="RobotoMono",
            size_hint_y=None,
            height=dp(60),
        )
        form.add_widget(self.token_field)
        
        self.wake_field = MDTextField(
            hint_text="Wake Word (default: nova)",
            text="nova",
            font_name="RobotoMono",
            size_hint_y=None,
            height=dp(60),
        )
        form.add_widget(self.wake_field)
        
        content.add_widget(form)
        
        # Save button
        save_btn = MDRaisedButton(
            text="SAVE AND CONNECT",
            font_name="RobotoMono",
            md_bg_color=(0.1, 0.4, 0.3, 1),
            theme_text_color="Custom",
            text_color=(0.2, 1, 0.6, 1),
            elevation=0,
            radius=[dp(4), dp(4), dp(4), dp(4)],
            size_hint_y=None,
            height=dp(50),
        )
        save_btn.bind(on_release=self._save_settings)
        content.add_widget(save_btn)
        
        # Help text
        content.add_widget(MDLabel(
            text="Find your token in ~/.openclaw/openclaw.json on your server",
            font_name="RobotoMono",
            font_size=sp(11),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.4, 0.4, 0.5, 1),
            size_hint_y=None,
            height=dp(30),
        ))
        
        root.add_widget(content)
        self.add_widget(root)
        
        # Load config
        self.config = Config()
        self.host_field.text = self.config.get("gateway_host", "")
        self.port_field.text = str(self.config.get("gateway_port", 18789))
        self.token_field.text = self.config.get("gateway_token", "")
        self.wake_field.text = self.config.get("wake_word", "nova")
    
    def _save_settings(self, instance):
        host = self.host_field.text.strip()
        port_text = self.port_field.text.strip()
        token = self.token_field.text.strip()
        wake_word = self.wake_field.text.strip().lower() or "nova"
        
        if not host:
            self._show_error("Enter gateway host")
            return
        if not token:
            self._show_error("Enter gateway token")
            return
        
        try:
            port = int(port_text) if port_text else 18789
        except ValueError:
            self._show_error("Invalid port")
            return
        
        self.config.data["gateway_host"] = host
        self.config.data["gateway_port"] = port
        self.config.data["gateway_token"] = token
        self.config.data["wake_word"] = wake_word
        self.config.data["setup_complete"] = True
        self.config.save()
        
        app = MDApp.get_running_app()
        app.root.current = "mission_control"
    
    def _show_error(self, message: str):
        dialog = MDDialog(
            title="Error",
            text=message,
            buttons=[MDRaisedButton(text="OK", on_release=lambda x: dialog.dismiss())],
        )
        dialog.open()


class NovaVoiceApp(MDApp):
    """Nova Voice - Futuristic Mission Control Interface."""
    
    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Cyan"
        self.theme_cls.accent_palette = "Teal"
        
        sm = MDScreenManager()
        sm.add_widget(SetupScreen(name="setup"))
        sm.add_widget(MissionControlScreen(name="mission_control"))
        
        config = Config()
        if config.is_configured():
            sm.current = "mission_control"
        else:
            sm.current = "setup"
        
        return sm
    
    def on_start(self):
        pass
    
    def on_stop(self):
        pass


def main():
    NovaVoiceApp().run()


if __name__ == "__main__":
    main()
