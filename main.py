#!/usr/bin/env python3
"""
Nova Voice - OpenClaw Node Client
Hands-free voice assistant with wake word detection.
"""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Debug file logging
DEBUG_PATH = None
DEBUG_FILE = None

def get_debug_path():
    global DEBUG_PATH
    if DEBUG_PATH is None:
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            DEBUG_PATH = str(activity.getFilesDir().getAbsolutePath()) + "/debug.log"
        except:
            DEBUG_PATH = "/tmp/nova_debug.log"
    return DEBUG_PATH

def debug_log(msg):
    global DEBUG_FILE
    try:
        if DEBUG_FILE is None:
            DEBUG_FILE = open(get_debug_path(), "a")
        DEBUG_FILE.write(f"[{datetime.now().isoformat()}] {msg}\n")
        DEBUG_FILE.flush()
    except:
        pass
    print(f"[DEBUG] {msg}", flush=True)

debug_log("=== NOVA VOICE STARTING ===")
debug_log(f"Python: {sys.version}")

# Imports with error handling
try:
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.floatlayout import FloatLayout
    from kivy.uix.scrollview import ScrollView
    from kivy.properties import StringProperty, BooleanProperty
    from kivy.metrics import dp
    debug_log("Kivy imports OK")
except Exception as e:
    debug_log(f"Kivy import FAILED: {e}")
    raise

try:
    from kivymd.app import MDApp
    from kivymd.uix.button import MDRaisedButton
    from kivymd.uix.card import MDCard
    from kivymd.uix.label import MDLabel
    from kivymd.uix.screen import MDScreen
    from kivymd.uix.screenmanager import MDScreenManager
    from kivymd.uix.textfield import MDTextField
    from kivymd.uix.list import MDList, OneLineListItem
    debug_log("KivyMD imports OK")
except Exception as e:
    debug_log(f"KivyMD import FAILED: {e}")
    raise

# WebSocket with fallback
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
    debug_log("websockets OK")
except Exception as e:
    WEBSOCKETS_AVAILABLE = False
    debug_log(f"websockets FAILED: {e}")

# Android imports
try:
    from jnius import autoclass
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    ANDROID = True
    debug_log("Android APIs OK")
except:
    ANDROID = False
    debug_log("Android APIs not available (running on desktop)")

# PyNaCl for Ed25519 signing
try:
    from nacl.signing import SigningKey
    from nacl.encoding import Base64Encoder
    NACL_AVAILABLE = True
    debug_log("PyNaCl OK")
except Exception as e:
    NACL_AVAILABLE = False
    debug_log(f"PyNaCl FAILED: {e} - device auth will be skipped")

# Vosk for wake word
try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
    debug_log("Vosk OK")
except:
    VOSK_AVAILABLE = False
    debug_log("Vosk not available")

debug_log(f"Imports complete: ws={WEBSOCKETS_AVAILABLE}, android={ANDROID}, nacl={NACL_AVAILABLE}, vosk={VOSK_AVAILABLE}")


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
        self.device_key = self._load_or_generate_device_key()
        debug_log(f"Config initialized, device_key={self.device_key is not None}")
    
    def _get_config_path(self) -> Path:
        if ANDROID:
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                files_dir = PythonActivity.mActivity.getFilesDir().getAbsolutePath()
                return Path(files_dir) / "config.json"
            except:
                pass
        return Path(__file__).parent / "config.json"
    
    def _load_or_generate_device_key(self) -> Optional[Dict]:
        """Load existing key or generate new one."""
        if not NACL_AVAILABLE:
            debug_log("NaCl not available, skipping device key")
            return None
        
        # Try to load existing
        if self.device_key_path.exists():
            try:
                with open(self.device_key_path, 'r') as f:
                    key_data = json.load(f)
                    if all(k in key_data for k in ['device_id', 'private_key', 'public_key']):
                        debug_log(f"Loaded existing device key: {key_data['device_id']}")
                        return key_data
            except Exception as e:
                debug_log(f"Error loading device key: {e}")
        
        # Generate new
        try:
            debug_log("Generating new device key...")
            signing_key = SigningKey.generate()
            verify_key = signing_key.verify_key
            
            device_id = hashlib.sha256(bytes(verify_key)).hexdigest()[:16]
            
            key_data = {
                "device_id": f"nova_voice_{device_id}",
                "private_key": base64.b64encode(bytes(signing_key)).decode('utf-8'),
                "public_key": base64.b64encode(bytes(verify_key)).decode('utf-8'),
            }
            
            try:
                self.device_key_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.device_key_path, 'w') as f:
                    json.dump(key_data, f, indent=2)
                debug_log(f"Saved device key: {key_data['device_id']}")
            except Exception as e:
                debug_log(f"Could not save device key (non-fatal): {e}")
            
            return key_data
        except Exception as e:
            debug_log(f"Error generating device key: {e}")
            debug_log(traceback.format_exc())
            return None
    
    def load(self) -> dict:
        try:
            if self.config_path.exists():
                with open(self.config_path) as f:
                    return {**self.defaults, **json.load(f)}
        except:
            pass
        return self.defaults.copy()
    
    def save(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            debug_log(f"Error saving config: {e}")
    
    def get(self, key: str, default=None):
        return self.data.get(key, default or self.defaults.get(key))
    
    def is_configured(self) -> bool:
        return bool(self.data.get("gateway_host")) and bool(self.data.get("gateway_token"))


config = Config()
debug_log("Config loaded")


class GatewayClient:
    """Async WebSocket client for OpenClaw gateway."""
    
    PROTOCOL_VERSION = 3
    
    def __init__(self, host: str, port: int, token: str, device_key: Optional[Dict] = None):
        self.host = host
        self.port = port
        self.token = token
        self.device_key = device_key
        self.ws = None
        self.connected = False
        self.authenticated = False
        self.session_key = "main"
        self.message_callback = None
        self._loop = None
        self._request_id = 0
        debug_log(f"GatewayClient created: {host}:{port}")
    
    def _next_request_id(self) -> str:
        self._request_id += 1
        return f"req_{int(time.time() * 1000)}_{self._request_id}"
    
    def _sign_challenge(self, nonce: str, ts: int) -> Optional[Dict]:
        """Sign challenge with device key."""
        if not self.device_key:
            debug_log("No device key available")
            return None
        
        if not NACL_AVAILABLE:
            debug_log("NaCl not available")
            return None
        
        try:
            from nacl.signing import SigningKey
            
            private_key_bytes = base64.b64decode(self.device_key['private_key'])
            signing_key = SigningKey(private_key_bytes)
            
            # v3 payload format
            payload = json.dumps({
                "device_id": self.device_key['device_id'],
                "platform": "android",
                "nonce": nonce,
                "ts": ts
            }, sort_keys=True, separators=(',', ':'))
            
            signed = signing_key.sign(payload.encode('utf-8'))
            
            return {
                "id": self.device_key['device_id'],
                "publicKey": self.device_key['public_key'],
                "signature": base64.b64encode(signed.signature).decode('utf-8'),
                "signedAt": int(time.time() * 1000),
                "nonce": nonce
            }
        except Exception as e:
            debug_log(f"Error signing challenge: {e}")
            debug_log(traceback.format_exc())
            return None
    
    async def connect(self) -> tuple:
        """Connect to gateway. Returns (success, message)."""
        if not WEBSOCKETS_AVAILABLE:
            return False, "websockets not available"
        
        uri = f"ws://{self.host}:{self.port}/ws"
        debug_log(f"Connecting to {uri}")
        
        try:
            self.ws = await websockets.connect(uri, ping_interval=30, ping_timeout=10)
            debug_log("WebSocket connected, waiting for challenge...")
            
            # Wait for challenge
            nonce = None
            ts = None
            
            try:
                challenge_raw = await asyncio.wait_for(self.ws.recv(), timeout=10)
                debug_log(f"Received: {challenge_raw[:200]}")
                challenge = json.loads(challenge_raw)
                
                if challenge.get("event") == "connect.challenge":
                    payload = challenge.get("payload", {})
                    nonce = payload.get("nonce")
                    ts = payload.get("ts")
                    debug_log(f"Challenge nonce: {nonce[:20] if nonce else 'none'}...")
            except asyncio.TimeoutError:
                debug_log("Challenge timeout, generating nonce")
            
            if not nonce:
                nonce = secrets.token_hex(16)
                ts = int(time.time() * 1000)
            
            # Build connect frame
            params = {
                "minProtocol": self.PROTOCOL_VERSION,
                "maxProtocol": self.PROTOCOL_VERSION,
                "client": {
                    "id": "nova-voice",
                    "version": "1.0.0",
                    "platform": "android" if ANDROID else "desktop",
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
            
            # Add device auth if available
            device_auth = self._sign_challenge(nonce, ts)
            if device_auth:
                params["device"] = device_auth
                debug_log("Added device auth")
            else:
                debug_log("No device auth, using token-only")
            
            connect_frame = {
                "type": "req",
                "id": self._next_request_id(),
                "method": "connect",
                "params": params
            }
            
            await self.ws.send(json.dumps(connect_frame))
            debug_log("Connect frame sent")
            
            # Wait for response
            response_raw = await asyncio.wait_for(self.ws.recv(), timeout=10)
            debug_log(f"Response: {response_raw[:500]}")
            response = json.loads(response_raw)
            
            if response.get("type") == "res" and response.get("ok"):
                payload = response.get("payload", {})
                if payload.get("type") == "hello-ok":
                    self.authenticated = True
                    self.connected = True
                    debug_log("CONNECTED!")
                    return True, "Connected"
                
                # Device token issued
                if payload.get("auth", {}).get("deviceToken"):
                    debug_log("Device token received")
                    self.authenticated = True
                    self.connected = True
                    return True, "Connected (paired)"
            
            # Error
            error = response.get("error", {})
            code = error.get("details", {}).get("code", error.get("message", "Unknown"))
            debug_log(f"Connection rejected: {code}")
            return False, f"Rejected: {code}"
            
        except asyncio.TimeoutError:
            return False, "Connection timeout"
        except Exception as e:
            debug_log(f"Connection error: {type(e).__name__}: {e}")
            debug_log(traceback.format_exc())
            return False, f"Error: {type(e).__name__}"
    
    async def receive_loop(self):
        """Receive messages from gateway."""
        try:
            async for msg in self.ws:
                try:
                    data = json.loads(msg)
                    if data.get("type") == "event":
                        event = data.get("event")
                        payload = data.get("payload", {})
                        if event == "chat.message" and self.message_callback:
                            text = payload.get("message", "") or payload.get("text", "")
                            if text:
                                self.message_callback(text, "assistant")
                except:
                    pass
        except Exception as e:
            debug_log(f"Receive loop ended: {e}")
        finally:
            self.connected = False
            self.authenticated = False
    
    async def send_message(self, text: str) -> bool:
        """Send a message to the gateway."""
        if not self.connected:
            return False
        try:
            msg = {
                "type": "req",
                "id": self._next_request_id(),
                "method": "session.send",
                "params": {"sessionKey": self.session_key, "message": text}
            }
            await self.ws.send(json.dumps(msg))
            return True
        except:
            return False
    
    async def close(self):
        """Close the connection."""
        self.connected = False
        self.authenticated = False
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass


class MainScreen(MDScreen):
    """Main chat screen."""
    
    status_text = StringProperty("Ready")
    connection_status = StringProperty("offline")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.gateway = None
        self.messages = []
        self._loop = None
        self._thread = None
        Clock.schedule_once(self._build_ui)
        debug_log("MainScreen init complete")
    
    def _build_ui(self, dt):
        """Build the UI."""
        root = FloatLayout()
        
        # Background
        from kivy.graphics import Color, Rectangle
        with root.canvas.before:
            Color(0.05, 0.05, 0.08, 1)
            self._bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._update_bg, size=self._update_bg)
        
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))
        
        # Header
        header = BoxLayout(size_hint_y=None, height=dp(60))
        
        title = MDLabel(
            text="[b]NOVA VOICE[/b]",
            font_name="RobotoMono",
            font_size=sp(22),
            markup=True,
            theme_text_color="Custom",
            text_color=(0.4, 0.8, 1, 1),
        )
        header.add_widget(title)
        
        self.status_indicator = MDLabel(
            text="● OFFLINE",
            font_name="RobotoMono",
            font_size=sp(14),
            halign="right",
            theme_text_color="Custom",
            text_color=(1, 0.3, 0.3, 1),
        )
        header.add_widget(self.status_indicator)
        content.add_widget(header)
        
        # Status bar
        self.status_label = MDLabel(
            text="Ready to connect",
            font_name="RobotoMono",
            font_size=sp(12),
            theme_text_color="Custom",
            text_color=(0.5, 0.7, 0.5, 1),
            size_hint_y=None,
            height=dp(30),
        )
        content.add_widget(self.status_label)
        
        # Chat area
        chat_card = MDCard(
            elevation=0,
            md_bg_color=(0.08, 0.08, 0.12, 1),
            radius=[dp(12)],
        )
        chat_layout = BoxLayout(orientation='vertical', padding=dp(8))
        
        self.chat_scroll = ScrollView()
        self.chat_list = MDList()
        self.chat_scroll.add_widget(self.chat_list)
        chat_layout.add_widget(self.chat_scroll)
        
        # Input
        input_row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        
        self.input_field = MDTextField(
            hint_text="Type a message...",
            font_name="RobotoMono",
            mode="fill",
            fill_color=(0.1, 0.1, 0.15, 1),
            size_hint_x=0.7,
        )
        input_row.add_widget(self.input_field)
        
        send_btn = MDRaisedButton(
            text="SEND",
            font_name="RobotoMono",
            font_size=sp(11),
            md_bg_color=(0.1, 0.4, 0.3, 1),
            theme_text_color="Custom",
            text_color=(0.2, 1, 0.6, 1),
            elevation=0,
            size_hint_x=0.3,
        )
        send_btn.bind(on_release=self._on_send)
        input_row.add_widget(send_btn)
        chat_layout.add_widget(input_row)
        
        chat_card.add_widget(chat_layout)
        content.add_widget(chat_card)
        
        # Buttons
        btn_row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        
        self.connect_btn = MDRaisedButton(
            text="CONNECT",
            font_name="RobotoMono",
            font_size=sp(12),
            md_bg_color=(0.1, 0.3, 0.4, 1),
            theme_text_color="Custom",
            text_color=(0.4, 0.8, 1, 1),
            elevation=0,
        )
        self.connect_btn.bind(on_release=self._on_connect)
        btn_row.add_widget(self.connect_btn)
        
        self.voice_btn = MDRaisedButton(
            text="🎤 VOICE",
            font_name="RobotoMono",
            font_size=sp(12),
            md_bg_color=(0.15, 0.15, 0.2, 1),
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.7, 1),
            elevation=0,
            disabled=True,
        )
        self.voice_btn.bind(on_release=self._on_voice)
        btn_row.add_widget(self.voice_btn)
        
        content.add_widget(btn_row)
        
        # Settings button
        settings_btn = MDRaisedButton(
            text="SETTINGS",
            font_name="RobotoMono",
            font_size=sp(11),
            md_bg_color=(0.1, 0.1, 0.15, 1),
            theme_text_color="Custom",
            text_color=(0.5, 0.5, 0.6, 1),
            elevation=0,
            size_hint_y=None,
            height=dp(40),
        )
        settings_btn.bind(on_release=lambda x: setattr(self.parent, 'current', 'setup'))
        content.add_widget(settings_btn)
        
        root.add_widget(content)
        self.add_widget(root)
        debug_log("UI built")
    
    def _update_bg(self, instance, value):
        self._bg_rect.pos = instance.pos
        self._bg_rect.size = instance.size
    
    def _add_message(self, text: str, sender: str):
        """Add a message to the chat list."""
        timestamp = datetime.now().strftime("%H:%M")
        item = OneLineListItem(
            text=f"[{timestamp}] {sender}: {text[:100]}",
            font_name="RobotoMono",
            font_size=sp(10),
        )
        self.chat_list.add_widget(item)
        self.chat_scroll.scroll_y = 0
    
    def _on_connect(self, instance):
        """Handle connect button."""
        if self.gateway and self.gateway.connected:
            # Disconnect
            self._update_status("Disconnecting...")
            if self._loop:
                asyncio.run_coroutine_threadsafe(self.gateway.close(), self._loop).result(timeout=5)
            self.connection_status = "offline"
            self.connect_btn.text = "CONNECT"
            self.voice_btn.disabled = True
            self._update_status("Disconnected")
            self._add_message("Disconnected", "system")
        else:
            # Connect
            self._update_status("Connecting...")
            self.connection_status = "connecting"
            self._start_connection()
    
    def _start_connection(self):
        """Start connection in background thread."""
        import threading
        
        def run():
            debug_log("Connection thread started")
            try:
                # Create new event loop for this thread
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                
                self.gateway = GatewayClient(
                    self.config.get("gateway_host"),
                    self.config.get("gateway_port"),
                    self.config.get("gateway_token"),
                    self.config.device_key
                )
                self.gateway.message_callback = self._on_gateway_message
                
                success, message = self._loop.run_until_complete(self.gateway.connect())
                debug_log(f"Connection result: {success}, {message}")
                
                if success:
                    self._loop.create_task(self.gateway.receive_loop())
                    Clock.schedule_once(lambda dt: self._on_connected(True, message))
                else:
                    Clock.schedule_once(lambda dt: self._on_connected(False, message))
                    
            except Exception as e:
                debug_log(f"Connection thread error: {e}")
                debug_log(traceback.format_exc())
                Clock.schedule_once(lambda dt: self._on_connected(False, str(e)))
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        debug_log("Connection thread started")
    
    def _on_connected(self, success: bool, message: str):
        """Handle connection result."""
        if success:
            self.connection_status = "online"
            self.connect_btn.text = "DISCONNECT"
            self.voice_btn.disabled = False
            self._update_status("Connected!")
            self._add_message("Connected to Nova", "system")
        else:
            self.connection_status = "offline"
            self._update_status(f"Failed: {message}")
            self._add_message(f"Connection failed: {message}", "system")
        
        # Update status indicator
        colors = {"offline": (1, 0.3, 0.3, 1), "connecting": (1, 0.8, 0.2, 1), "online": (0.2, 1, 0.6, 1)}
        self.status_indicator.text = f"● {self.connection_status.upper()}"
        self.status_indicator.text_color = colors.get(self.connection_status, (0.5, 0.5, 0.5, 1))
    
    def _on_gateway_message(self, text: str, sender: str):
        """Handle message from gateway."""
        Clock.schedule_once(lambda dt: self._add_message(text, sender))
    
    def _on_send(self, instance):
        """Handle send button."""
        text = self.input_field.text.strip()
        if not text:
            return
        
        self.input_field.text = ""
        self._add_message(text, "user")
        
        if self.gateway and self.gateway.connected and self._loop:
            asyncio.run_coroutine_threadsafe(self.gateway.send_message(text), self._loop)
        else:
            self._add_message("Not connected", "system")
    
    def _on_voice(self, instance):
        """Handle voice button."""
        self._add_message("Voice not implemented yet", "system")
    
    def _update_status(self, text: str):
        """Update status label."""
        self.status_label.text = text


class SetupScreen(MDScreen):
    """Setup/config screen."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._build_ui)
    
    def _build_ui(self, dt):
        root = FloatLayout()
        content = BoxLayout(orientation='vertical', padding=dp(24), spacing=dp(16))
        
        content.add_widget(MDLabel(
            text="[b]NOVA VOICE[/b]\nSetup",
            font_name="RobotoMono",
            font_size=sp(24),
            markup=True,
            halign="center",
            theme_text_color="Custom",
            text_color=(0.4, 0.8, 1, 1),
            size_hint_y=None,
            height=dp(80),
        ))
        
        self.host_field = MDTextField(
            hint_text="Gateway Host",
            text=config.get("gateway_host", ""),
            font_name="RobotoMono",
            size_hint_y=None,
            height=dp(60),
        )
        content.add_widget(self.host_field)
        
        self.port_field = MDTextField(
            hint_text="Port",
            text=str(config.get("gateway_port", 18789)),
            font_name="RobotoMono",
            input_filter="int",
            size_hint_y=None,
            height=dp(60),
        )
        content.add_widget(self.port_field)
        
        self.token_field = MDTextField(
            hint_text="Token",
            text=config.get("gateway_token", ""),
            font_name="RobotoMono",
            password=True,
            size_hint_y=None,
            height=dp(60),
        )
        content.add_widget(self.token_field)
        
        save_btn = MDRaisedButton(
            text="SAVE",
            font_name="RobotoMono",
            font_size=sp(14),
            md_bg_color=(0.1, 0.4, 0.3, 1),
            theme_text_color="Custom",
            text_color=(0.2, 1, 0.6, 1),
            size_hint_y=None,
            height=dp(50),
        )
        save_btn.bind(on_release=self._on_save)
        content.add_widget(save_btn)
        
        root.add_widget(content)
        self.add_widget(root)
    
    def _on_save(self, instance):
        config.data["gateway_host"] = self.host_field.text.strip()
        config.data["gateway_port"] = int(self.port_field.text.strip() or 18789)
        config.data["gateway_token"] = self.token_field.text.strip()
        config.save()
        MDApp.get_running_app().root.current = "main"


class NovaVoiceApp(MDApp):
    """Main app."""
    
    def build(self):
        debug_log("NovaVoiceApp.build()")
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Cyan"
        
        sm = MDScreenManager()
        sm.add_widget(SetupScreen(name="setup"))
        sm.add_widget(MainScreen(name="main"))
        
        sm.current = "main" if config.is_configured() else "setup"
        debug_log(f"Screen: {sm.current}")
        return sm
    
    def on_start(self):
        debug_log("App started")


def main():
    debug_log("main() called")
    try:
        NovaVoiceApp().run()
    except Exception as e:
        debug_log(f"App crashed: {e}")
        debug_log(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
