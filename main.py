#!/usr/bin/env python3
"""
Nova Voice - Minimal Test Build
"""

import sys
print("[DEBUG] Starting app...", flush=True)

try:
    from kivy.app import App
    from kivy.uix.label import Label
    from kivymd.app import MDApp
    from kivymd.uix.screen import MDScreen
    from kivymd.uix.screenmanager import MDScreenManager
    from kivymd.uix.button import MDRaisedButton
    from kivymd.uix.label import MDLabel
    from kivymd.uix.card import MDCard
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.floatlayout import FloatLayout
    from kivy.metrics import dp
    print("[DEBUG] Kivy imports OK", flush=True)
except Exception as e:
    print(f"[DEBUG] Kivy import FAILED: {e}", flush=True)
    raise

print("[DEBUG] All imports successful", flush=True)


class MainScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print("[DEBUG] MainScreen init", flush=True)
        
        root = FloatLayout()
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(16))
        
        # Title
        content.add_widget(MDLabel(
            text="[b]NOVA VOICE[/b]\nMinimal Test",
            font_size=dp(24),
            markup=True,
            halign="center",
            theme_text_color="Custom",
            text_color=(0.4, 0.8, 1, 1),
            size_hint_y=None,
            height=dp(80),
        ))
        
        # Status
        self.status = MDLabel(
            text="App loaded successfully!",
            font_size=dp(16),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.3, 0.8, 0.5, 1),
        )
        content.add_widget(self.status)
        
        # Test button
        btn = MDRaisedButton(
            text="TEST BUTTON",
            font_size=dp(14),
            md_bg_color=(0.1, 0.4, 0.3, 1),
            theme_text_color="Custom",
            text_color=(0.2, 1, 0.6, 1),
            size_hint_y=None,
            height=dp(50),
        )
        btn.bind(on_release=self._on_button)
        content.add_widget(btn)
        
        root.add_widget(content)
        self.add_widget(root)
        print("[DEBUG] MainScreen built", flush=True)
    
    def _on_button(self, instance):
        print("[DEBUG] Button pressed!", flush=True)
        self.status.text = "Button works!"


class TestApp(MDApp):
    def build(self):
        print("[DEBUG] TestApp.build()", flush=True)
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Cyan"
        
        sm = MDScreenManager()
        sm.add_widget(MainScreen(name="main"))
        print("[DEBUG] ScreenManager ready", flush=True)
        return sm


if __name__ == "__main__":
    print("[DEBUG] __main__ starting", flush=True)
    TestApp().run()
    print("[DEBUG] App exited", flush=True)
