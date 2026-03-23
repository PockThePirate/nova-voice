#!/usr/bin/env python3
"""
Nova Voice - Minimal Test Build
Strips all heavy dependencies to isolate crash cause.
"""

import sys
print("=== NOVA VOICE MINIMAL ===")
print(f"Python: {sys.version}")

# Test each import one by one
imports_ok = True

# Test 1: Kivy
try:
    from kivy.app import App
    from kivy.uix.label import Label
    print("✓ Kivy imported")
except Exception as e:
    print(f"✗ Kivy FAILED: {e}")
    imports_ok = False

# Test 2: KivyMD
try:
    from kivymd.app import MDApp
    from kivymd.uix.screen import MDScreen
    from kivymd.uix.screenmanager import MDScreenManager
    print("✓ KivyMD imported")
except Exception as e:
    print(f"✗ KivyMD FAILED: {e}")
    imports_ok = False

if not imports_ok:
    print("FATAL: Core imports failed, cannot continue")
    sys.exit(1)


class MainScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from kivy.uix.boxlayout import BoxLayout
        from kivymd.uix.label import MDLabel
        from kivymd.uix.button import MDRaisedButton
        from kivy.metrics import dp
        
        layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(10))
        
        layout.add_widget(MDLabel(
            text="NOVA VOICE",
            halign="center",
            font_style="H4",
        ))
        
        layout.add_widget(MDLabel(
            text="Minimal test build - no heavy deps",
            halign="center",
        ))
        
        self.status = MDLabel(
            text="App loaded successfully!",
            halign="center",
            theme_text_color="Custom",
            text_color=(0, 1, 0, 1),
        )
        layout.add_widget(self.status)
        
        btn = MDRaisedButton(
            text="TEST BUTTON",
            size_hint_y=None,
            height=dp(50),
        )
        btn.bind(on_release=lambda x: setattr(self.status, 'text', 'Button works!'))
        layout.add_widget(btn)
        
        self.add_widget(layout)


class TestApp(MDApp):
    def build(self):
        print("Building app...")
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Cyan"
        
        sm = MDScreenManager()
        sm.add_widget(MainScreen(name="main"))
        print("App built successfully!")
        return sm


if __name__ == "__main__":
    print("Starting app...")
    TestApp().run()