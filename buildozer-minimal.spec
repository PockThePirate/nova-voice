[app]

# Minimal test build - just Kivy + KivyMD
title = Nova Voice Test
package.name = novavoice
package.domain = org.openclaw
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.exclude_exts = spec,pyc,md
version = 1.0.0

# MINIMAL: Just python3, kivy, kivymd - no vosk, websockets, pynacl
requirements = python3,kivy==2.3.0,kivymd==1.1.1,pyjnius

android.icon = icon.png
orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.archs = arm64-v8a, armeabi-v7a
android.minapi = 24
android.api = 33
android.ndk = 25b
android.sdk_path = /usr/local/lib/android/sdk
android.entry_point = org.kivy.android.PythonActivity
android.app_theme = @android:style/Theme.NoTitleBar
android.copy_libs = 1
android.logcat_filters = *:S python:D
android.debuggable = 1

[buildozer]
log_level = 2
warn_on_root = 1