[app]

# Ultra-minimal build for Samsung S25 Ultra / Android 16
title = Nova Voice Test
package.name = novavoice
package.domain = org.openclaw
source.dir = .
source.include_exts = py,png,jpg,kv,json
source.exclude_exts = spec,pyc,md
version = 2.0.0

# MINIMAL: Just Kivy - NO KivyMD, NO vosk, NO websockets, NO pynacl
# This is a baseline test to prove the app can open at all
requirements = python3,kivy,pyjnius

# Android 14+ compatibility
android.api = 34
android.minapi = 24
android.ndk = 25b
android.sdk_path = /usr/local/lib/android/sdk

# Minimal permissions
android.permissions = INTERNET

# Single arch for faster build
android.archs = arm64-v8a

android.icon = icon.png
orientation = portrait
fullscreen = 0
android.allow_backup = True
android.entry_point = org.kivy.android.PythonActivity
android.app_theme = @android:style/Theme.NoTitleBar
android.copy_libs = 1
android.logcat_filters = *:S python:D
android.debuggable = 1

[buildozer]
log_level = 2
warn_on_root = 1