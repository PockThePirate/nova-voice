#!/usr/bin/env python3
"""
Nova Voice - OpenClaw Node Client (Simplified)
Mission control interface with voice and chat.
"""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView

from kivymd.app import MDApp
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.textfield import MDTextField
from kivymd.uix.list import MDList, OneLineListItem

# Try imports with fallbacks
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

# Android imports
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

# Vosk for speech
try:
    from vosk import Model, KaldiRecognizer, SetLogLevel
    SetLogLevel(-1)
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

# NaCl for auth
try:
    from nacl.signing import SigningKey
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
        if not NACL_AVAILABLE:
            return None
        
        try:
            if self.device_key_path.exists():
                with open(self.device_key_path) as f:
                    return json.load(f)
        except:
            pass
        
        # Generate new keypair
        try:
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
        except:
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


config = Config()


class GatewayClient:
    """WebSocket client for OpenClaw gateway."""
    
    PROTOCOL_VERSION = 3
    
    def __init__(self, host: str, port: int, token: str, device_key: Dict = None):
        self.host = host
        self.port = port
        self.token = token
        self.device_key = device_key
        self.ws = None
        self.connected = False
        self.authenticated = False
        self.session_key = "main"
        self.message_callback = None
        self._receive_task = None
        self._request_id = 0
    
    def _next_request_id(self) -> str:
        self._request_id += 1
        return f"req_{int(time.time() * 1000)}_{self._request_id}"
    
    def _sign_challenge(self, nonce: str, ts: int) -> Dict[str, Any]:
        if not self.device_key:
            return {}
        
        try:
            import nacl.signing
            private_key_bytes = base64.b64decode(self.device_key["private_key"])
            signing_key = nacl.signing.SigningKey(private_key_bytes)
            
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
        except:
            return {}
    
    async def connect(self) -> tuple:
        if not WEBSOCKETS_AVAILABLE:
            return False, "websockets library not available"
        
        try:
            uri = f"ws://{self.host}:{self.port}/ws"
            self.ws = await websockets.connect(uri, ping_interval=30, ping_timeout=10)
            
            # Wait for challenge
            try:
                challenge = await asyncio.wait_for(self.ws.recv(), timeout=10)
                challenge_data = json.loads(challenge)
                
                if challenge_data.get("event") == "connect.challenge":
                    payload = challenge_data.get("payload", {})
                    nonce = payload.get("nonce", secrets.token_hex(16))
                    ts = payload.get("ts", int(time.time() * 1000))
                else:
                    nonce = secrets.token_hex(16)
                    ts = int(time.time() * 1000)
            except asyncio.TimeoutError:
                nonce = secrets.token_hex(16)
                ts = int(time.time() * 1000)
            
            # Build connect frame
            device_auth = self._sign_challenge(nonce, ts)
            
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
                    "caps": ["voice", "audio"],
                    "commands": ["voice.listen", "audio.capture"],
                    "permissions": {"audio.capture": True, "voice.listen": True},
                    "auth": {"token": self.token},
                    "locale": "en-US",
                    "userAgent": "NovaVoice/1.0.0",
                }
            }
            
            if device_auth:
                connect_frame["params"]["device"] = device_auth
            
            await self.ws.send(json.dumps(connect_frame))
            
            # Wait for response
            response = await asyncio.wait_for(self.ws.recv(), timeout=10)
            response_data = json.loads(response)
            
            if response_data.get("type") == "res" and response_data.get("ok"):
                payload = response_data.get("payload", {})
                if payload.get("type") == "hello-ok":
                    self.authenticated = True
                    self.connected = True
                    self._receive_task = asyncio.create_task(self._receive_loop())
                    return True, "Connected"
            
            error = response_data.get("error", {})
            code = error.get("details", {}).get("code", error.get("message", "Auth failed"))
            return False, f"Auth failed: {code}"
            
        except asyncio.TimeoutError:
            return False, "Connection timeout"
        except Exception as e:
            return False, f"Error: {e}"
    
    async def _receive_loop(self):
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")
                    
                    if msg_type == "event":
                        event = data.get("event")
                        payload = data.get("payload", {})
                        
                        if event == "chat.message":
                            text = payload.get("message", "") or payload.get("text", "")
                            sender = payload.get("sender", "") or payload.get("role", "")
                            if text and self.message_callback:
                                Clock.schedule_once(lambda dt, t=text, s=sender: self.message_callback(t, s))
                except:
                    pass
        except:
            pass
        finally:
            self.connected = False
            self.authenticated = False
    
    async def send_message(self, text: str) -> bool:
        if not self.connected or not self.ws:
            return False
        
        try:
            message = {
                "type": "req",
                "id": self._next_request_id(),
                "method": "session.send",
                "params": {"sessionKey": self.session_key, "message": text}
            }
            await self.ws.send(json.dumps(message))
            return True
        except:
            return False
    
    async def close(self):
        if self._receive_task:
            self._receive_task.cancel()
        if self.ws:
            await self.ws.close()
        self.connected = False
        self.authenticated = False


class AudioCapture:
    """Android audio capture."""
    
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
        except:
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


class SpeechRecognition:
    """Vosk speech recognition."""
    
    def __init__(self, model_path: Path):
        self.model = None
        self.recognizer = None
        self.model_path = model_path
    
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
    
    def process_audio(self, audio_data: bytes) -> tuple:
        if not self.recognizer:
            return False, ""
        
        try:
            self.recognizer.AcceptWaveform(audio_data)
            result = json.loads(self.recognizer.Result())
            text = result.get("text", "")
            if text:
                return True, text
            return False, ""
        except:
            return False, ""
    
    def reset(self):
        if self.model:
            self.recognizer = KaldiRecognizer(self.model, 16000)


class TTSEngine:
    """Edge TTS."""
    
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
                while sound.state == 'play' and time.time() - start < 120:
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


class MainScreen(MDScreen):
    """Main chat screen."""
    
    connection_status = StringProperty("offline")
    is_listening = BooleanProperty(False)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.gateway = None
        self.audio_capture = None
        self.speech_rec = None
        self.tts = None
        self.loop = None
        self.event_loop_thread = None
        self.messages = []
        self.is_recording = False
        self.recording_buffer = []
        
        Clock.schedule_once(self._build_ui)
    
    def _build_ui(self, dt):
        # Dark background
        root = FloatLayout()
        
        # Main content
        content = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(8))
        
        # Header
        header = BoxLayout(size_hint_y=None, height=dp(50))
        
        title = MDLabel(
            text="[b]NOVA VOICE[/b]",
            font_name="RobotoMono",
            font_size=sp(18),
            markup=True,
            theme_text_color="Custom",
            text_color=(0.4, 0.8, 1, 1),
            size_hint_x=0.5,
        )
        header.add_widget(title)
        
        self.status_label = MDLabel(
            text="● OFFLINE",
            font_name="RobotoMono",
            font_size=sp(14),
            halign="right",
            theme_text_color="Custom",
            text_color=(1, 0.3, 0.3, 1),
            size_hint_x=0.5,
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
        self.status_text = MDLabel(
            text="Ready to connect",
            font_name="RobotoMono",
            font_size=sp(12),
            theme_text_color="Custom",
            text_color=(0.3, 0.8, 0.5, 1),
        )
        status_bar.add_widget(self.status_text)
        content.add_widget(status_bar)
        
        # Chat area
        chat_card = MDCard(
            elevation=0,
            md_bg_color=(0.03, 0.06, 0.1, 0.95),
            radius=[dp(8)],
        )
        chat_layout = BoxLayout(orientation='vertical', padding=dp(8))
        
        self.chat_scroll = ScrollView()
        self.chat_list = MDList()
        self.chat_scroll.add_widget(self.chat_list)
        chat_layout.add_widget(self.chat_scroll)
        
        # Transcript
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
        chat_layout.add_widget(self.transcript_label)
        
        # Input
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
        
        # Buttons
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
        
        # Settings
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
    
    def _initialize(self, dt):
        self.tts = TTSEngine(self.config.get("voice"))
        
        # Initialize speech recognition
        model_path = Path(__file__).parent / "assets" / "vosk-model-small-en-us-0.15"
        if not model_path.exists():
            model_path = Path(__file__).parent / "vosk-model-small-en-us-0.15"
        
        self.speech_rec = SpeechRecognition(model_path)
        if self.speech_rec.initialize():
            self._add_message("Voice ready. Say 'Hey Nova' to start.", "system")
        else:
            self._add_message("Voice unavailable - model not found.", "system")
        
        # Initialize audio
        if ANDROID_AVAILABLE:
            self.audio_capture = AudioCapture()
        
        # Start event loop
        self._start_event_loop()
        
        # Auto-connect
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
        msg = ChatMessage(text, sender)
        self.messages.append(msg)
        
        item = OneLineListItem(
            text=f"[{msg.timestamp.strftime('%H:%M')}] {text[:80]}",
            font_name="RobotoMono",
            font_size=sp(11),
        )
        self.chat_list.add_widget(item)
        self.chat_scroll.scroll_y = 0
    
    def _on_connect(self, instance):
        if self.gateway and self.gateway.connected:
            asyncio.run_coroutine_threadsafe(self.gateway.close(), self.loop)
            self.connection_status = "offline"
            self.connect_btn.text = "CONNECT"
            self.voice_btn.disabled = True
            self._update_status("Disconnected")
        else:
            self._update_status("Connecting...")
            self.connection_status = "connecting"
            
            self.gateway = GatewayClient(
                self.config.get("gateway_host"),
                self.config.get("gateway_port"),
                self.config.get("gateway_token"),
                self.config.device_key
            )
            self.gateway.message_callback = self._on_message
            
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
            
            if self.loop and self.tts:
                asyncio.run_coroutine_threadsafe(self.tts.speak("Nova online."), self.loop)
        else:
            self.connection_status = "offline"
            self._update_status(f"Failed: {message}")
            self._add_message(f"Connection failed: {message}", "system")
    
    def _on_message(self, text: str, sender: str):
        if sender == "assistant":
            self._add_message(text, "assistant")
            if self.loop and self.tts:
                asyncio.run_coroutine_threadsafe(self.tts.speak(text), self.loop)
    
    def _send_message(self, instance):
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
            self._add_message("Not connected.", "system")
    
    def _toggle_voice(self, instance):
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
            
            if not self.audio_capture and ANDROID_AVAILABLE:
                self.audio_capture = AudioCapture()
            
            if self.audio_capture and self.audio_capture.initialize():
                self.audio_capture.audio_callback = self._on_audio
                self.audio_capture.start()
            else:
                self._add_message("Audio unavailable.", "system")
                self.is_listening = False
                self.voice_btn.text = "🎤 VOICE"
    
    def _on_audio(self, audio_data: bytes):
        if not self.is_listening:
            return
        
        if self.speech_rec:
            is_final, text = self.speech_rec.process_audio(audio_data)
            
            if is_final and text:
                wake_word = self.config.get("wake_word", "nova").lower()
                
                if not self.is_recording and wake_word in text.lower():
                    self.is_recording = True
                    self.recording_buffer = []
                    Clock.schedule_once(lambda dt: setattr(self.transcript_label, 'text', "🎤 Wake word! Listening..."))
                    self.speech_rec.reset()
                    
                    if self.loop and self.tts:
                        asyncio.run_coroutine_threadsafe(self.tts.speak("Yes?"), self.loop)
                
                elif self.is_recording:
                    self.recording_buffer.append(text)
                    full_text = " ".join(self.recording_buffer)
                    Clock.schedule_once(lambda dt: setattr(self.transcript_label, 'text', f"🎤 {full_text}"))
                    
                    if len(full_text) > 5:
                        Clock.schedule_once(lambda dt: self._send_voice(full_text), 1.0)
                        self.is_recording = False
                        self.speech_rec.reset()
    
    def _send_voice(self, text: str):
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
        
        colors = {"offline": (1, 0.3, 0.3, 1), "connecting": (1, 0.8, 0.2, 1), "online": (0.2, 1, 0.6, 1)}
        color = colors.get(self.connection_status, (0.5, 0.5, 0.5, 1))
        self.status_label.text = f"● {self.connection_status.upper()}"
        self.status_label.text_color = color
    
    def _show_settings(self, instance):
        MDApp.get_running_app().root.current = "setup"
    
    def on_enter(self):
        if not hasattr(self, 'loop'):
            Clock.schedule_once(self._initialize, 0.5)


class ChatMessage:
    def __init__(self, text: str, sender: str):
        self.text = text
        self.sender = sender
        self.timestamp = datetime.now()


class SetupScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._build_ui)
    
    def _build_ui(self, dt):
        root = FloatLayout()
        
        content = BoxLayout(orientation='vertical', padding=dp(24), spacing=dp(16))
        
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
        
        self.host_field = MDTextField(hint_text="Gateway Host", size_hint_y=None, height=dp(60))
        self.host_field.text = config.get("gateway_host", "")
        content.add_widget(self.host_field)
        
        self.port_field = MDTextField(hint_text="Port", size_hint_y=None, height=dp(60), input_filter="int")
        self.port_field.text = str(config.get("gateway_port", 18789))
        content.add_widget(self.port_field)
        
        self.token_field = MDTextField(hint_text="Token", password=True, size_hint_y=None, height=dp(60))
        self.token_field.text = config.get("gateway_token", "")
        content.add_widget(self.token_field)
        
        save_btn = MDRaisedButton(
            text="SAVE",
            font_name="RobotoMono",
            md_bg_color=(0.1, 0.4, 0.3, 1),
            theme_text_color="Custom",
            text_color=(0.2, 1, 0.6, 1),
            size_hint_y=None,
            height=dp(50),
        )
        save_btn.bind(on_release=self._save)
        content.add_widget(save_btn)
        
        root.add_widget(content)
        self.add_widget(root)
    
    def _save(self, instance):
        config.data["gateway_host"] = self.host_field.text.strip()
        config.data["gateway_port"] = int(self.port_field.text.strip() or 18789)
        config.data["gateway_token"] = self.token_field.text.strip()
        config.data["setup_complete"] = True
        config.save()
        MDApp.get_running_app().root.current = "main"


class NovaVoiceApp(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Cyan"
        
        sm = MDScreenManager()
        sm.add_widget(SetupScreen(name="setup"))
        sm.add_widget(MainScreen(name="main"))
        
        sm.current = "main" if config.is_configured() else "setup"
        return sm


def main():
    NovaVoiceApp().run()


if __name__ == "__main__":
    main()
