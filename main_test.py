#!/usr/bin/env python3
"""
Nova Voice - Minimal Test Version
This is a stripped-down version to verify basic KivyMD functionality.
"""

# Ultra-simple test: just show a screen with a button
# No vosk, no websockets, no pynacl - just Kivy + KivyMD

from kivy.app import App
from kivy.uix.label import Label
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.label import MDLabel

class TestScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.md_bg_color = (0.1, 0.1, 0.15, 1)
        
        # Simple label
        self.label = MDLabel(
            text="Nova Voice - Test Build",
            halign="center",
            font_style="H4",
            pos_hint={"center_x": 0.5, "center_y": 0.6}
        )
        self.add_widget(self.label)
        
        # Button
        self.btn = MDRaisedButton(
            text="Tap to Confirm Working",
            pos_hint={"center_x": 0.5, "center_y": 0.4},
            on_release=self.on_tap
        )
        self.add_widget(self.btn)
    
    def on_tap(self, instance):
        self.label.text = "✓ App is working!"
        self.label.theme_text_color = "Custom"
        self.label.text_color = (0, 1, 0.5, 1)


class TestApp(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"
        return TestScreen()


if __name__ == '__main__':
    TestApp().run()