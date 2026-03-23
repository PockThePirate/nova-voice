#!/usr/bin/env python3
"""
Nova Voice - Minimal Test v2
Ultra-minimal test for Samsung S25 Ultra / Android 16
"""

# NO imports except Kivy basics
from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout


class MinimalApp(App):
    def build(self):
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        
        # Plain Kivy Label - NO KivyMD, NO custom fonts
        self.label = Label(
            text='Nova Voice\nMinimal Test v2\n\nIf you see this, the app works!',
            font_size='20sp',
            halign='center',
            color=(0, 1, 0.5, 1)  # Green text
        )
        layout.add_widget(self.label)
        
        self.btn = Button(
            text='TAP ME',
            font_size='18sp',
            size_hint_y=0.3
        )
        self.btn.bind(on_press=self.on_tap)
        layout.add_widget(self.btn)
        
        return layout
    
    def on_tap(self, instance):
        self.label.text = 'SUCCESS!\n\nButton works!\nApp is functional.'
        self.label.color = (0, 1, 0, 1)


if __name__ == '__main__':
    MinimalApp().run()