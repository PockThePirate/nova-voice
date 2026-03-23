#!/usr/bin/env python3
"""
Nova Voice - OpenClaw Node Client
A complete mission control interface with voice, chat, and device capabilities.
Implements full OpenClaw gateway protocol with device authentication.
"""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import io
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.audio import SoundLoader
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty, NumericProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.animation import Animation
from kivy.lang import Builder
from kivy.core.window import Window

from kivymd.app import MDApp
from kivymd.uix.button import MDRaisedButton, MDIconButton, MDFlatButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.textfield import MDTextField
from kivymd.uix.list import MDList, OneLineAvatarIconListItem, TwoLineAvatarIconListItem
from kivymd.uix.boxlayout import MDBoxLayout

import websockets

# Android-specific imports
try:
    from jnius import autoclass, PythonJavaClass, java_method
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    AudioRecord = autoclass('android.media.AudioRecord')
    MediaRecorder = autoclass('android.media.MediaRecorder')
    AudioSource = autoclass('android.media.MediaRecorder$AudioSource')
    AudioFormat = autoclass('android.media.AudioFormat')
    Context = autoclass('android.content.Context')
    Intent = autoclass('android.content.Intent')
    Notification = autoclass('android.app.Notification')
    NotificationChannel = autoclass('android.app.NotificationChannel')
    NotificationManager = autoclass('android.app.NotificationManager')
    PendingIntent = autoclass('android.app.PendingIntent')
    BuildVersion = autoclass('android.os.Build$VERSION')
    PowerManager = autoclass('android.os.PowerManager')
    LocationManager = autoclass('android.location.LocationManager')
    Location = autoclass('android.location.Location')
    Criteria = autoclass('android.location.Criteria')
    Looper = autoclass('android.os.Looper')
    Handler = autoclass('android.os.Handler')
    BitmapFactory = autoclass('android.graphics.BitmapFactory')
    ByteArrayOutputStream = autoclass('java.io.ByteArrayOutputStream')
    ANDROID_AVAILABLE = True
except ImportError:
    ANDROID_AVAILABLE = False

# Vosk for speech recognition
try:
    from vosk import Model, KaldiRecognizer, SetLogLevel
    SetLogLevel(-1)
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

# NaCl for device authentication
try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.encoding import Base64Encoder
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False


class Config:
    """Configuration management."""
    
    def __init__(self):
        self.config_path = self._get_config_path()
        self.device_key_path = self.config_path.parent / "device_key.json"
        self.defaults = {
            "gateway_host": "147.93.113.71",
            "gateway_port": 18789,
            "gateway_token": "3cb919b06196e5366f357281542cd3c168c4147946f5e0cd",
            "wake_word": "nova",
            "voice": "en-US-AvaNeural",
            "setup_complete": True,
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
            device_id = hashlib.sha256(bytes(verify_key)).hexdigest()[:16]
            
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
        except:
            pass
    
    def get(self, key: str, default=None):
        return self.data.get(key, default if default else self.defaults.get(key))
    
    def is_configured(self) -> bool:
        return bool(self.data.get("gateway_host")) and bool(self.data.get("gateway_token"))


class ForegroundService:
    """Android foreground service to keep app running when screen is locked."""
    
    CHANNEL_ID = "nova_voice_channel"
    NOTIFICATION_ID = 1001
    
    def __init__(self):
        self.service_started = False
        
    def start(self):
        """Start foreground service."""
        if not ANDROID_AVAILABLE:
            return False
        
        try:
            activity = PythonActivity.mActivity
            context = activity.getApplicationContext()
            
            # Create notification channel for Android O+
            if BuildVersion.SDK_INT >= 26:
                channel = NotificationChannel(
                    self.CHANNEL_ID,
                    "Nova Voice Service",
                    NotificationManager.IMPORTANCE_LOW
                )
                channel.setDescription("Keeps Nova Voice running in background")
                channel.setShowBadge(False)
                
                notification_manager = context.getSystemService(Context.NOTIFICATION_SERVICE)
                notification_manager.createNotificationChannel(channel)
            
            # Create notification
            if BuildVersion.SDK_INT >= 31:
                notification_builder = Notification.Builder(context, self.CHANNEL_ID)
            elif BuildVersion.SDK_INT >= 26:
                notification_builder = Notification.Builder(context, self.CHANNEL_ID)
            else:
                notification_builder = Notification.Builder(context)
            
            notification_builder.setContentTitle("Nova Voice")
            notification_builder.setContentText("Listening for wake word...")
            notification_builder.setSmallIcon(activity.getApplicationInfo().icon)
            notification_builder.setOngoing(True)
            
            notification = notification_builder.build()
            notification.flags = Notification.FLAG_ONGOING_EVENT | Notification.FLAG_NO_CLEAR
            
            # Start foreground service
            activity.startForegroundService(self.NOTIFICATION_ID, notification)
            self.service_started = True
            return True
            
        except Exception as e:
            print(f"Foreground service error: {e}")
            return False
    
    def stop(self):
        """Stop foreground service."""
        if not ANDROID_AVAILABLE or not self.service_started:
            return
        
        try:
            activity = PythonActivity.mActivity
            activity.stopService(Intent(activity, PythonActivity))
            self.service_started = False
        except:
            pass


class AudioCapture:
    """Android audio capture with continuous recording."""
    
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
                max(min_buffer * 2, self.chunk_size * 2)
            )
            
            if self.audio_record.getState() != AudioRecord.STATE_INITIALIZED:
                return False
            
            return True
        except Exception as e:
            print(f"Audio init error: {e}")
            return False
    
    def start(self):
        if not self.audio_record:
            return
        
        self.running = True
        self.audio_record.startRecording()
        
        def capture_loop():
            buffer = bytearray(self.chunk_size * 2)
            
            while self.running:
                try:
                    bytes_read = self.audio_record.read(buffer, 0, len(buffer))
                    if bytes_read > 0 and self.audio_callback:
                        self.audio_callback(bytes(buffer[:bytes_read]))
                except Exception as e:
                    print(f"Audio capture error: {e}")
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


class SpeechRecognition:
    """Continuous speech recognition using Vosk."""
    
    def __init__(self, model_path: Path):
        self.model = None
        self.recognizer = None
        self.model_path = model_path
        self.partial_callback = None
        self.final_callback = None
    
    def initialize(self) -> bool:
        if not VOSK_AVAILABLE:
            print("Vosk not available")
            return False
        
        if not self.model_path.exists():
            print(f"Vosk model not found at {self.model_path}")
            return False
        
        try:
            self.model = Model(str(self.model_path))
            self.recognizer = KaldiRecognizer(self.model, 16000)
            print("Speech recognition initialized")
            return True
        except Exception as e:
            print(f"Vosk init error: {e}")
            return False
    
    def process_audio(self, audio_data: bytes) -> tuple[bool, str]:
        """Process audio, returns (is_final, text)."""
        if not self.recognizer:
            return False, ""
        
        try:
            # Check for partial result
            self.recognizer.AcceptWaveform(audio_data)
            
            # Check for final result
            result = json.loads(self.recognizer.Result())
            text = result.get("text", "")
            if text:
                return True, text
            
            # Get partial result
            partial = json.loads(self.recognizer.PartialResult())
            partial_text = partial.get("partial", "")
            if partial_text and self.partial_callback:
                self.partial_callback(partial_text)
            
            return False, ""
        except Exception as e:
            print(f"Recognition error: {e}")
            return False, ""
    
    def get_partial(self) -> str:
        """Get current partial transcription."""
        if not self.recognizer:
            return ""
        try:
            result = json.loads(self.recognizer.PartialResult())
            return result.get("partial", "")
        except:
            return ""
    
    def reset(self):
        if self.model:
            self.recognizer = KaldiRecognizer(self.model, 16000)


class TTSEngine:
    """Text-to-speech using Edge TTS."""
    
    def __init__(self, voice: str = "en-US-AvaNeural"):
        self.voice = voice
        self.speaking = False
        self._cache_dir = Path(__file__).parent / "tts_cache"
        self.speech_queue = []
        self._speaking_lock = threading.Lock()
    
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
                while sound.state == 'play' and time.time() - start < 120:
                    await asyncio.sleep(0.1)
                sound.unload()
            
            try:
                audio_path.unlink()
            except:
                pass
            
            self.speaking = False
            return True
        except Exception as e:
            print(f"TTS error: {e}")
            self.speaking = False
            return False
    
    def speak_sync(self, text: str):
        """Synchronous TTS for use in callbacks."""
        if self.speaking:
            return
        
        def run_tts():
            try:
                import edge_tts
                asyncio.run(self.speak(text))
            except:
                pass
        
        threading.Thread(target=run_tts, daemon=True).start()


class GatewayProtocol:
    """Full OpenClaw gateway WebSocket protocol implementation."""
    
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
        self.session_key = "main"
        
        # Callbacks
        self.message_callback = None
        self.state_callback = None
        self.error_callback = None
        
        self._receive_task = None
        self._request_id = 0
        self._pending_requests = {}
    
    def _next_request_id(self) -> str:
        self._request_id += 1
        return f"req_{int(time.time() * 1000)}_{self._request_id}"
    
    def _sign_challenge(self, nonce: str, ts: int) -> Dict[str, Any]:
        if not NACL_AVAILABLE or not self.device_key:
            return {}
        
        try:
            private_key_bytes = base64.b64decode(self.device_key["private_key"])
            signing_key = SigningKey(private_key_bytes)
            
            # Sign v3 payload
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
            print(f"Sign error: {e}")
            return {}
    
    async def connect(self) -> tuple[bool, str]:
        """Connect and authenticate."""
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
                    self.challenge_nonce = secrets.token_hex(16)
                    self.challenge_ts = int(time.time() * 1000)
            except asyncio.TimeoutError:
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
                    "scopes": ["operator.read", "operator.write"],
                    "caps": ["voice", "audio", "camera", "screen", "location"],
                    "commands": [
                        "voice.listen",
                        "audio.capture",
                        "camera.snap",
                        "screen.record",
                        "location.get"
                    ],
                    "permissions": {
                        "audio.capture": True,
                        "voice.listen": True,
                        "camera.capture": True,
                        "screen.record": True
                    },
                    "auth": {"token": self.token},
                    "locale": "en-US",
                    "userAgent": "NovaVoice/1.0.0",
                }
            }
            
            if device_auth:
                connect_frame["params"]["device"] = device_auth
            
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
                        self.session_key = payload.get("sessionKey", "main")
                        
                        # Start message handler
                        self._receive_task = asyncio.create_task(self._receive_loop())
                        self.connected = True
                        
                        if self.state_callback:
                            Clock.schedule_once(lambda dt: self.state_callback("connected"))
                        
                        return True, "Connected successfully"
                    else:
                        return False, f"Unexpected response: {payload}"
                else:
                    error = response_data.get("error", {})
                    code = error.get("details", {}).get("code", error.get("message", "Auth failed"))
                    return False, f"Auth failed: {code}"
                    
            except asyncio.TimeoutError:
                return False, "Connection timeout"
                
        except websockets.exceptions.ConnectionClosed as e:
            return False, f"Connection closed: {e}"
        except Exception as e:
            return False, f"Error: {e}"
    
    async def _receive_loop(self):
        """Receive messages from gateway."""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    
                    # Handle different message types
                    msg_type = data.get("type")
                    
                    if msg_type == "event":
                        event = data.get("event")
                        payload = data.get("payload", {})
                        
                        if event == "chat.message":
                            text = payload.get("message", "") or payload.get("text", "")
                            sender = payload.get("sender", "") or payload.get("role", "")
                            if text and self.message_callback:
                                Clock.schedule_once(lambda dt, t=text, s=sender: self.message_callback(t, s))
                        
                        elif event == "chat.transcript":
                            # Partial transcript
                            text = payload.get("text", "")
                            is_final = payload.get("final", False)
                            if text and self.message_callback:
                                Clock.schedule_once(lambda dt, t=text, f=is_final: self.message_callback(t, "transcript"))
                        
                        elif event == "session.event":
                            # Session events
                            pass
                    
                    elif msg_type == "res":
                        # Response to request
                        request_id = data.get("id")
                        if request_id in self._pending_requests:
                            self._pending_requests[request_id].set_result(data)
                            del self._pending_requests[request_id]
                    
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    print(f"Message handling error: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception:
            pass
        finally:
            self.connected = False
            self.authenticated = False
            if self.state_callback:
                Clock.schedule_once(lambda dt: self.state_callback("disconnected"))
    
    async def send_message(self, text: str) -> bool:
        """Send a chat message."""
        if not self.connected or not self.ws:
            return False
        
        try:
            message = {
                "type": "req",
                "id": self._next_request_id(),
                "method": "session.send",
                "params": {
                    "sessionKey": self.session_key,
                    "message": text
                }
            }
            await self.ws.send(json.dumps(message))
            return True
        except Exception as e:
            print(f"Send error: {e}")
            return False
    
    async def send_audio(self, audio_data: bytes) -> bool:
        """Send audio for transcription."""
        if not self.connected or not self.ws:
            return False
        
        try:
            # Encode audio as base64
            audio_b64 = base64.b64encode(audio_data).decode()
            
            message = {
                "type": "req",
                "id": self._next_request_id(),
                "method": "audio.transcribe",
                "params": {
                    "sessionKey": self.session_key,
                    "audio": audio_b64,
                    "format": "pcm16",
                    "sampleRate": 16000
                }
            }
            await self.ws.send(json.dumps(message))
            return True
        except Exception as e:
            print(f"Audio send error: {e}")
            return False
    
    async def close(self):
        if self._receive_task:
            self._receive_task.cancel()
        if self.ws:
            await self.ws.close()
        self.connected = False
        self.authenticated = False


class ChatMessage:
    """Represents a chat message."""
    def __init__(self, text: str, sender: str, timestamp: datetime = None):
        self.text = text
        self.sender = sender  # "user", "assistant", "system"
        self.timestamp = timestamp or datetime.now()


class ChatListItem(BoxLayout):
    """Custom list item for chat messages."""
    def __init__(self, message: ChatMessage, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self.size_hint_y = None
        self.height = dp(60)
        self.orientation = 'horizontal'
        self.padding = dp(8)
        
        # Background color based on sender
        if message.sender == "user":
            bg_color = (0.1, 0.3, 0.4, 0.8)
            align = "right"
        elif message.sender == "assistant":
            bg_color = (0.15, 0.15, 0.2, 0.8)
            align = "left"
        else:
            bg_color = (0.05, 0.1, 0.15, 0.8)
            align = "center"
        
        with self.canvas.before:
            Color(*bg_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
        
        # Message content
        content = BoxLayout(orientation='vertical', padding=dp(8))
        
        # Timestamp
        time_label = MDLabel(
            text=message.timestamp.strftime("%H:%M"),
            font_size=sp(10),
            theme_text_color="Custom",
            text_color=(0.5, 0.5, 0.6, 1),
            size_hint_y=None,
            height=dp(16),
            halign=align,
        )
        content.add_widget(time_label)
        
        # Text
        text_label = MDLabel(
            text=message.text[:500],  # Limit text length
            font_name="RobotoMono",
            font_size=sp(12),
            theme_text_color="Custom",
            text_color=(0.8, 0.9, 1, 1),
            halign=align,
            valign="top",
        )
        text_label.bind(texture_size=lambda instance, value: setattr(text_label, 'height', value[1]))
        content.add_widget(text_label)
        
        self.add_widget(content)


class MissionControlScreen(MDScreen):
    """Main mission control interface."""
    
    connection_status = StringProperty("offline")
    status_message = StringProperty("Ready")
    is_listening = BooleanProperty(False)
    is_recording = BooleanProperty(False)
    last_transcript = StringProperty("")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = None
        self.gateway = None
        self.audio_capture = None
        self.speech_rec = None
        self.tts = None
        self.foreground_service = None
        self.loop = None
        self.event_loop_thread = None
        
        self.messages: List[ChatMessage] = []
        self.is_speaking = False
        self.wake_word_detected = False
        self.recording_buffer = []
        
        Clock.schedule_once(self._build_ui)
    
    def _build_ui(self, dt):
        """Build the futuristic UI."""
        root = FloatLayout()
        
        # Dark background
        with root.canvas.before:
            Color(0.02, 0.05, 0.08, 1)
            self._bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._update_bg, size=self._update_bg)
        
        content = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(8))
        
        # Header with status
        header = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        
        title = MDLabel(
            text="[b]NOVA[/b]",
            font_name="RobotoMono",
            font_size=sp(18),
            markup=True,
            theme_text_color="Custom",
            text_color=(0.4, 0.8, 1, 1),
            size_hint_x=0.3,
        )
        header.add_widget(title)
        
        # Connection status indicator
        self.status_label = MDLabel(
            text="● OFFLINE",
            font_name="RobotoMono",
            font_size=sp(14),
            halign="right",
            theme_text_color="Custom",
            text_color=(1, 0.3, 0.3, 1),
            size_hint_x=0.7,
        )
        header.add_widget(self.status_label)
        
        content.add_widget(header)
        
        # Status bar
        status_bar = MDCard(
            elevation=0,
            md_bg_color=(0.05, 0.1, 0.15, 0.9),
            radius=[dp(8)],
            size_hint_y=None,
            height=dp(40),
        )
        status_content = BoxLayout(padding=dp(12))
        self.status_text = MDLabel(
            text="Ready to connect",
            font_name="RobotoMono",
            font_size=sp(12),
            theme_text_color="Custom",
            text_color=(0.3, 0.8, 0.5, 1),
        )
        status_content.add_widget(self.status_text)
        status_bar.add_widget(status_content)
        content.add_widget(status_bar)
        
        # Chat history
        chat_card = MDCard(
            elevation=0,
            md_bg_color=(0.03, 0.06, 0.1, 0.95),
            radius=[dp(8)],
        )
        
        chat_layout = BoxLayout(orientation='vertical', padding=dp(8))
        
        # Chat list with scroll
        self.chat_scroll = ScrollView()
        self.chat_list = MDList()
        self.chat_scroll.add_widget(self.chat_list)
        chat_layout.add_widget(self.chat_scroll)
        
        # Input area
        input_layout = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        
        self.message_input = MDTextField(
            hint_text="Type a message...",
            font_name="RobotoMono",
            size_hint_x=0.7,
            mode="fill",
            fill_color=(0.1, 0.15, 0.2, 1),
        )
        input_layout.add_widget(self.message_input)
        
        send_btn = MDRaisedButton(
            text="SEND",
            font_name="RobotoMono",
            font_size=sp(12),
            md_bg_color=(0.1, 0.4, 0.3, 1),
            theme_text_color="Custom",
            text_color=(0.2, 1, 0.6, 1),
            size_hint_x=0.3,
            elevation=0,
        )
        send_btn.bind(on_release=self._send_message)
        input_layout.add_widget(send_btn)
        
        chat_layout.add_widget(input_layout)
        chat_card.add_widget(chat_layout)
        content.add_widget(chat_card)
        
        # Transcript display (for voice)
        self.transcript_label = MDLabel(
            text="",
            font_name="RobotoMono",
            font_size=sp(14),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.4, 0.6, 0.8, 1),
            size_hint_y=None,
            height=dp(40),
        )
        content.add_widget(self.transcript_label)
        
        # Control buttons
        controls = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        
        self.connect_btn = MDRaisedButton(
            text="CONNECT",
            font_name="RobotoMono",
            md_bg_color=(0.1, 0.3, 0.4, 1),
            theme_text_color="Custom",
            text_color=(0.4, 0.8, 1, 1),
            elevation=0,
        )
        self.connect_btn.bind(on_release=self._on_connect)
        controls.add_widget(self.connect_btn)
        
        self.voice_btn = MDRaisedButton(
            text="🎤 VOICE",
            font_name="RobotoMono",
            md_bg_color=(0.15, 0.15, 0.2, 1),
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.7, 1),
            elevation=0,
            disabled=True,
        )
        self.voice_btn.bind(on_release=self._toggle_voice)
        controls.add_widget(self.voice_btn)
        
        content.add_widget(controls)
        
        # Settings button
        settings_btn = MDRaisedButton(
            text="SETTINGS",
            font_name="RobotoMono",
            md_bg_color=(0.1, 0.1, 0.15, 1),
            theme_text_color="Custom",
            text_color=(0.5, 0.5, 0.6, 1),
            elevation=0,
            size_hint_y=None,
            height=dp(40),
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
        self.foreground_service = ForegroundService()
        
        # Initialize speech recognition
        model_path = Path(__file__).parent / "assets" / "vosk-model-small-en-us-0.15"
        if not model_path.exists():
            model_path = Path(__file__).parent / "vosk-model-small-en-us-0.15"
        
        self.speech_rec = SpeechRecognition(model_path)
        if self.speech_rec.initialize():
            self._add_message("Voice ready. Say 'Hey Nova' to start.", "system")
        else:
            self._add_message("Voice unavailable - Vosk model not found.", "system")
        
        # Initialize audio capture
        if ANDROID_AVAILABLE:
            self.audio_capture = AudioCapture()
        
        # Start event loop
        self._start_event_loop()
        
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
    
    def _add_message(self, text: str, sender: str):
        """Add message to chat."""
        msg = ChatMessage(text, sender)
        self.messages.append(msg)
        
        # Add to UI
        item = OneLineAvatarIconListItem(
            text=f"[{msg.timestamp.strftime('%H:%M')}] {text[:100]}",
            font_name="RobotoMono",
            font_size=sp(11),
        )
        self.chat_list.add_widget(item)
        
        # Scroll to bottom
        self.chat_scroll.scroll_y = 0
    
    def _on_connect(self, instance):
        if self.gateway and self.gateway.connected:
            # Disconnect
            asyncio.run_coroutine_threadsafe(self.gateway.close(), self.loop)
            self.connection_status = "offline"
            self.connect_btn.text = "CONNECT"
            self.voice_btn.disabled = True
            self._update_status("Disconnected")
            if self.foreground_service:
                self.foreground_service.stop()
        else:
            # Connect
            self._update_status("Connecting...")
            self.connection_status = "connecting"
            
            self.gateway = GatewayProtocol(
                self.config.get("gateway_host"),
                self.config.get("gateway_port"),
                self.config.get("gateway_token"),
                self.config.device_key
            )
            self.gateway.message_callback = self._on_gateway_message
            self.gateway.state_callback = self._on_connection_state
            
            async def do_connect():
                success, message = await self.gateway.connect()
                Clock.schedule_once(lambda dt: self._on_connected(success, message))
            
            asyncio.run_coroutine_threadsafe(do_connect(), self.loop)
    
    def _on_connected(self, success: bool, message: str):
        if success:
            self.connection_status = "online"
            self.connect_btn.text = "DISCONNECT"
            self.voice_btn.disabled = False
            self._update_status(f"Connected to {self.config.get('gateway_host')}")
            self._add_message("Connected to Nova.", "system")
            
            # Start foreground service
            if self.foreground_service:
                self.foreground_service.start()
            
            # Welcome message
            if self.loop and self.tts:
                asyncio.run_coroutine_threadsafe(
                    self.tts.speak("Nova online. How can I help you?"),
                    self.loop
                )
        else:
            self.connection_status = "offline"
            self._update_status(f"Connection failed: {message}")
            self._add_message(f"Connection failed: {message}", "system")
    
    def _on_connection_state(self, state: str):
        """Handle connection state changes."""
        if state == "connected":
            self.connection_status = "online"
        elif state == "disconnected":
            self.connection_status = "offline"
            self.connect_btn.text = "CONNECT"
            self.voice_btn.disabled = True
    
    def _on_gateway_message(self, text: str, sender: str):
        """Handle messages from gateway."""
        if sender == "transcript":
            # Partial transcript - update display
            self.transcript_label.text = f"🎤 {text}"
        elif sender == "assistant":
            self._add_message(text, "assistant")
            
            # Speak response
            if self.loop and self.tts and not self.is_speaking:
                self.is_speaking = True
                asyncio.run_coroutine_threadsafe(self.tts.speak(text), self.loop)
                # Reset after speaking
                Clock.schedule_once(lambda dt: setattr(self, 'is_speaking', False), 5)
    
    def _send_message(self, instance):
        """Send text message."""
        text = self.message_input.text.strip()
        if not text:
            return
        
        self.message_input.text = ""
        self._add_message(text, "user")
        
        if self.gateway and self.gateway.connected:
            async def send():
                await self.gateway.send_message(text)
            asyncio.run_coroutine_threadsafe(send(), self.loop)
        else:
            self._add_message("Not connected to gateway.", "system")
    
    def _toggle_voice(self, instance):
        """Toggle voice listening mode."""
        if self.is_listening:
            self.is_listening = False
            self.is_recording = False
            self.voice_btn.text = "🎤 VOICE"
            self.voice_btn.md_bg_color = (0.15, 0.15, 0.2, 1)
            self.transcript_label.text = ""
            
            if self.audio_capture:
                self.audio_capture.stop()
        else:
            self.is_listening = True
            self.voice_btn.text = "⏹ STOP"
            self.voice_btn.md_bg_color = (0.6, 0.2, 0.2, 1)
            self.transcript_label.text = "🎤 Listening..."
            
            # Initialize and start audio capture
            if not self.audio_capture:
                if ANDROID_AVAILABLE:
                    self.audio_capture = AudioCapture()
            
            if self.audio_capture and self.audio_capture.initialize():
                self.audio_capture.audio_callback = self._on_audio
                self.audio_capture.start()
            else:
                self._add_message("Audio capture unavailable.", "system")
                self.is_listening = False
                self.voice_btn.text = "🎤 VOICE"
    
    def _on_audio(self, audio_data: bytes):
        """Process audio data."""
        if not self.is_listening:
            return
        
        # Check for wake word
        if self.speech_rec:
            is_final, text = self.speech_rec.process_audio(audio_data)
            
            if is_final and text:
                wake_word = self.config.get("wake_word", "nova").lower()
                
                if not self.is_recording and wake_word in text.lower():
                    # Wake word detected - start recording
                    self.is_recording = True
                    self.recording_buffer = []
                    Clock.schedule_once(lambda dt: setattr(self.transcript_label, 'text', "🎤 Wake word detected! Listening..."))
                    
                    # Reset recognizer for command
                    self.speech_rec.reset()
                    
                    # Play chime or speak
                    if self.loop and self.tts:
                        asyncio.run_coroutine_threadsafe(self.tts.speak("Yes?"), self.loop)
                
                elif self.is_recording:
                    # We're recording - accumulate text
                    self.recording_buffer.append(text)
                    
                    # Check if user said "stop" or long pause
                    if len(text) > 0 and (text.lower() in ["stop", "cancel", "nevermind", "never mind"]):
                        self.is_recording = False
                        self.recording_buffer = []
                        Clock.schedule_once(lambda dt: setattr(self.transcript_label, 'text', ""))
                        self.speech_rec.reset()
                    else:
                        # Update display
                        full_text = " ".join(self.recording_buffer)
                        Clock.schedule_once(lambda dt: setattr(self.transcript_label, 'text', f"🎤 {full_text}"))
                        
                        # Send after accumulating some text and a pause
                        # For simplicity, send when we have something substantial
                        if len(full_text) > 10:
                            # Small delay to let user finish
                            Clock.schedule_once(lambda dt: self._send_voice_command(full_text), 1.5)
                            self.is_recording = False
                            self.speech_rec.reset()
    
    def _send_voice_command(self, text: str):
        """Send voice command to gateway."""
        if not text.strip():
            return
        
        self._add_message(text, "user")
        
        if self.gateway and self.gateway.connected:
            async def send():
                await self.gateway.send_message(text)
            asyncio.run_coroutine_threadsafe(send(), self.loop)
        
        self.recording_buffer = []
        Clock.schedule_once(lambda dt: setattr(self.transcript_label, 'text', "🎤 Listening..."))
    
    def _update_status(self, message: str):
        self.status_text.text = message
        
        status_colors = {
            "offline": (1, 0.3, 0.3, 1),
            "connecting": (1, 0.8, 0.2, 1),
            "online": (0.2, 1, 0.6, 1),
        }
        color = status_colors.get(self.connection_status, (0.5, 0.5, 0.5, 1))
        self.status_label.text = f"● {self.connection_status.upper()}"
        self.status_label.text_color = color
    
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
            text="[b]NOVA[/b]\nSETUP",
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
            size_hint_y=None,
            height=dp(50),
        )
        save_btn.bind(on_release=self._save_settings)
        content.add_widget(save_btn)
        
        # Help text
        content.add_widget(MDLabel(
            text="Find your token in ~/.openclaw/openclaw.json",
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
    """Nova Voice - Mission Control Interface."""
    
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
